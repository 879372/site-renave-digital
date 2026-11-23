"""Ciclo de vida da assinatura: teste, contratação, troca de plano, fechamento mensal e inadimplência.

Regras:
- Conta nova de revenda começa com 14 dias do Profissional; sem assinar, cai no Grátis.
- Contratar ou subir de plano gera uma fatura; o plano só muda quando ela é paga.
  Subir no meio do período desconta, proporcionalmente, o que falta do plano atual.
- Descer de plano (ou voltar ao Grátis) fica agendado para o fim do período pago.
- Todo mês, no `next_billing_date`, o consumo pós-pago (RENAVE etc.) vai para a fatura,
  junto com a mensalidade quando o período pago acaba.
- Fatura vencida deixa a assinatura em atraso; depois de GRACE_DAYS, suspende
  (recursos do Grátis, sem limite pós-pago) até o pagamento.
"""

import calendar
from datetime import date, timedelta

from django.db import transaction
from django.utils import timezone

from audit.service import record
from core.exceptions import BusinessError
from wallet import service as wallet

from .catalog import DUE_DAYS, FREE_PLAN, GRACE_DAYS, TRIAL_DAYS, TRIAL_PLAN
from .entitlements import applies
from .models import Invoice, InvoiceItem, Plan, Subscription

Status = Subscription.Status
Cycle = Subscription.Cycle


def add_months(d: date, months: int) -> date:
    month = d.month - 1 + months
    year = d.year + month // 12
    month = month % 12 + 1
    return date(year, month, min(d.day, calendar.monthrange(year, month)[1]))


def cycle_months(cycle: str) -> int:
    return 12 if cycle == Cycle.ANNUAL else 1


def today() -> date:
    return timezone.localdate()


# --- criação -----------------------------------------------------------------------------


def start_trial(organization) -> Subscription:
    sub, _ = Subscription.objects.select_related("plan").get_or_create(
        organization=organization,
        defaults={
            "plan": Plan.objects.get(code=TRIAL_PLAN),
            "status": Status.TRIALING,
            "trial_ends_at": timezone.now() + timedelta(days=TRIAL_DAYS),
        },
    )
    return sub


def on_organization_created(organization) -> None:
    if applies(organization):
        start_trial(organization)


# --- limite pós-pago -----------------------------------------------------------------------


def sync_credit_limit(sub: Subscription) -> None:
    """Pós-pago só para plano pago ativo (ou em atraso dentro da tolerância). Teste e Grátis são pré-pagos."""
    allowed = sub.plan.postpaid and sub.status in (Status.ACTIVE, Status.PAST_DUE)
    wallet.set_credit_limit(sub.organization, sub.plan.credit_limit_cents if allowed else 0)


# --- contratação e troca de plano --------------------------------------------------------


def _is_paid_period(sub: Subscription, on: date) -> bool:
    return sub.status in (Status.ACTIVE, Status.PAST_DUE) and not sub.plan.is_free and bool(sub.paid_through) and sub.paid_through > on


def _is_downgrade(sub: Subscription, plan: Plan, cycle: str) -> bool:
    if plan.sort_order != sub.plan.sort_order:
        return plan.sort_order < sub.plan.sort_order
    return sub.cycle == Cycle.ANNUAL and cycle == Cycle.MONTHLY


def _proration_credit(sub: Subscription, on: date) -> int:
    """Valor não usado do período pago atual."""
    start = add_months(sub.paid_through, -cycle_months(sub.cycle))
    total_days = (sub.paid_through - start).days or 1
    remaining = max((sub.paid_through - on).days, 0)
    return sub.plan.price_for(sub.cycle) * remaining // total_days


def change_plan(organization, plan: Plan, cycle: str, *, user=None, request=None) -> Invoice | None:
    """Contrata, sobe ou agenda a descida de plano. Retorna a fatura a pagar (ou None se só agendou)."""
    if not plan.is_active:
        raise BusinessError("Este plano não está disponível.")
    if cycle not in Cycle.values:
        raise BusinessError("Ciclo de cobrança inválido.")

    with transaction.atomic():
        from .entitlements import get_subscription

        get_subscription(organization)
        sub = Subscription.objects.select_for_update().select_related("plan", "organization").get(organization=organization)
        now = today()
        paid_period = _is_paid_period(sub, now)

        if sub.status in (Status.ACTIVE, Status.PAST_DUE) and plan.pk == sub.plan_id and (plan.is_free or cycle == sub.cycle):
            if sub.scheduled_plan_id:
                sub.scheduled_plan = None
                sub.scheduled_cycle = ""
                sub.save(update_fields=["scheduled_plan", "scheduled_cycle", "updated_at"])
                record("billing.change_canceled", request=request, actor=user, organization=organization, target=sub)
                return None
            raise BusinessError("Este já é o seu plano atual.")

        if plan.is_free or (paid_period and _is_downgrade(sub, plan, cycle)):
            if not paid_period:  # teste, suspensa ou já no Grátis: muda na hora
                _apply_plan(sub, plan, Cycle.MONTHLY, now)
                record("billing.plan_changed", request=request, actor=user, organization=organization, target=sub, plan=plan.code)
                return None
            sub.scheduled_plan = plan
            sub.scheduled_cycle = cycle
            sub.save(update_fields=["scheduled_plan", "scheduled_cycle", "updated_at"])
            record("billing.change_scheduled", request=request, actor=user, organization=organization, target=sub, plan=plan.code)
            return None

        _cancel_open_plan_invoices(sub)
        items = [
            (
                InvoiceItem.Kind.PLAN,
                f"Plano {plan.name} — {Cycle(cycle).label.lower()}",
                plan.price_for(cycle),
            )
        ]
        if paid_period:
            credit = min(_proration_credit(sub, now), plan.price_for(cycle))
            if credit:
                items.append((InvoiceItem.Kind.PRORATION, f"Crédito do plano {sub.plan.name} (dias não usados)", -credit))
        invoice = _create_invoice(sub, Invoice.Kind.PLAN_CHANGE, items, target_plan=plan, target_cycle=cycle)
        record(
            "billing.checkout",
            request=request,
            actor=user,
            organization=organization,
            target=invoice,
            plan=plan.code,
            cycle=cycle,
            amount_cents=invoice.total_cents,
        )
    if invoice.total_cents == 0:
        mark_paid(invoice)
    return invoice


def _cancel_open_plan_invoices(sub: Subscription) -> None:
    for inv in sub.invoices.filter(kind=Invoice.Kind.PLAN_CHANGE, status=Invoice.Status.OPEN):
        cancel_invoice(inv)


def _apply_plan(sub: Subscription, plan: Plan, cycle: str, on: date) -> None:
    sub.plan = plan
    sub.cycle = cycle
    sub.status = Status.ACTIVE
    sub.trial_ends_at = None
    sub.scheduled_plan = None
    sub.scheduled_cycle = ""
    if plan.is_free:
        sub.paid_through = None
        # Se houver consumo pós-pago pendente, o próximo fechamento (mantido) ainda o fatura.
    else:
        sub.paid_through = add_months(on, cycle_months(cycle))
        sub.next_billing_date = add_months(on, 1)
    sub.save()
    sync_credit_limit(sub)


def _create_invoice(sub: Subscription, kind: str, items, *, target_plan=None, target_cycle="", due: date | None = None) -> Invoice:
    total = max(sum(amount for _, _, amount in items), 0)
    invoice = Invoice.objects.create(
        organization=sub.organization,
        subscription=sub,
        kind=kind,
        total_cents=total,
        due_date=due or today() + timedelta(days=DUE_DAYS),
        target_plan=target_plan,
        target_cycle=target_cycle,
    )
    InvoiceItem.objects.bulk_create(
        [InvoiceItem(invoice=invoice, kind=k, description=desc[:200], total_cents=amount) for k, desc, amount in items]
    )
    if total:
        from .tasks import push_invoice

        transaction.on_commit(lambda: push_invoice.delay(invoice.pk))
    return invoice


# --- pagamento e cancelamento --------------------------------------------------------------


def mark_paid(invoice: Invoice, *, user=None, request=None) -> Invoice:
    with transaction.atomic():
        invoice = Invoice.objects.select_for_update().get(pk=invoice.pk)
        if invoice.status == Invoice.Status.PAID:
            return invoice
        if invoice.status == Invoice.Status.CANCELED and invoice.kind == Invoice.Kind.PLAN_CHANGE:
            # Pagou uma fatura de troca já substituída: registra para o financeiro tratar (crédito ou estorno).
            record("billing.paid_canceled_invoice", request=request, actor=user, organization=invoice.organization, target=invoice)
        invoice.status = Invoice.Status.PAID
        invoice.paid_at = timezone.now()
        invoice.save(update_fields=["status", "paid_at", "updated_at"])

        sub = Subscription.objects.select_for_update().select_related("plan", "organization").get(pk=invoice.subscription_id)
        if invoice.kind == Invoice.Kind.PLAN_CHANGE and invoice.target_plan_id and invoice.canceled_at is None:
            _apply_plan(sub, invoice.target_plan, invoice.target_cycle or Cycle.MONTHLY, today())
        elif sub.status in (Status.PAST_DUE, Status.SUSPENDED) and not _has_overdue(sub):
            sub.status = Status.ACTIVE
            sub.save(update_fields=["status", "updated_at"])
            sync_credit_limit(sub)
        record(
            "billing.invoice_paid",
            request=request,
            actor=user,
            organization=invoice.organization,
            target=invoice,
            amount_cents=invoice.total_cents,
        )
    return invoice


def cancel_invoice(invoice: Invoice, *, user=None, request=None) -> Invoice:
    with transaction.atomic():
        invoice = Invoice.objects.select_for_update().get(pk=invoice.pk)
        if invoice.status in (Invoice.Status.PAID, Invoice.Status.CANCELED):
            return invoice
        invoice.status = Invoice.Status.CANCELED
        invoice.canceled_at = timezone.now()
        invoice.save(update_fields=["status", "canceled_at", "updated_at"])
        if invoice.provider_payment_id:
            from .tasks import cancel_gateway_payment

            transaction.on_commit(lambda: cancel_gateway_payment.delay(invoice.pk))
        if user or request:
            record("billing.invoice_canceled", request=request, actor=user, organization=invoice.organization, target=invoice)
    return invoice


def mark_overdue(invoice: Invoice) -> Invoice:
    with transaction.atomic():
        invoice = Invoice.objects.select_for_update().get(pk=invoice.pk)
        if invoice.status != Invoice.Status.OPEN:
            return invoice
        invoice.status = Invoice.Status.OVERDUE
        invoice.save(update_fields=["status", "updated_at"])
        if invoice.kind == Invoice.Kind.RENEWAL:
            sub = Subscription.objects.select_for_update().select_related("plan", "organization").get(pk=invoice.subscription_id)
            if sub.status == Status.ACTIVE:
                sub.status = Status.PAST_DUE
                sub.save(update_fields=["status", "updated_at"])
    return invoice


def _has_overdue(sub: Subscription) -> bool:
    return sub.invoices.filter(kind=Invoice.Kind.RENEWAL, status=Invoice.Status.OVERDUE).exists()


# --- rotina diária -------------------------------------------------------------------------


def expire_trials(now=None) -> int:
    now = now or timezone.now()
    free = Plan.objects.get(code=FREE_PLAN)
    count = 0
    for sub in Subscription.objects.filter(status=Status.TRIALING, trial_ends_at__lte=now).select_related("organization", "plan"):
        with transaction.atomic():
            sub = Subscription.objects.select_for_update().select_related("plan", "organization").get(pk=sub.pk)
            if sub.status != Status.TRIALING:
                continue
            _apply_plan(sub, free, Cycle.MONTHLY, today())
            record("billing.trial_ended", organization=sub.organization, target=sub)
            count += 1
    return count


def renew(sub: Subscription, on: date | None = None) -> Invoice | None:
    """Fechamento mensal: aplica troca agendada, fatura o consumo e, se for o caso, a próxima mensalidade."""
    on = on or today()
    with transaction.atomic():
        sub = Subscription.objects.select_for_update().select_related("plan", "organization").get(pk=sub.pk)
        if not sub.next_billing_date or sub.next_billing_date > on or sub.status == Status.TRIALING:
            return None
        billing_date = sub.next_billing_date

        if sub.scheduled_plan_id and (not sub.paid_through or sub.paid_through <= billing_date):
            plan, cycle = sub.scheduled_plan, sub.scheduled_cycle or Cycle.MONTHLY
            sub.plan, sub.cycle = plan, cycle
            sub.scheduled_plan, sub.scheduled_cycle = None, ""
            if plan.is_free:
                sub.paid_through = None
            record("billing.plan_changed", organization=sub.organization, target=sub, plan=plan.code, scheduled=True)

        invoice = Invoice(
            organization=sub.organization,
            subscription=sub,
            kind=Invoice.Kind.RENEWAL,
            due_date=on + timedelta(days=DUE_DAYS),
        )
        items: list[tuple[str, str, int]] = []
        owed = wallet.invoice_usage(sub.organization, invoice_ref=str(invoice.public_id))
        if owed:
            label = (
                f"Consumo de {add_months(billing_date, -1):%d/%m} a {billing_date - timedelta(days=1):%d/%m} (RENAVE e serviços por uso)"
            )
            items.append((InvoiceItem.Kind.USAGE, label, owed))

        if not sub.plan.is_free and (not sub.paid_through or sub.paid_through <= billing_date):
            start = max(sub.paid_through or billing_date, billing_date)
            sub.paid_through = add_months(start, cycle_months(sub.cycle))
            items.append(
                (InvoiceItem.Kind.PLAN, f"Plano {sub.plan.name} — {sub.get_cycle_display().lower()}", sub.plan.price_for(sub.cycle))
            )

        sub.next_billing_date = None if sub.plan.is_free else add_months(billing_date, 1)
        sub.save()
        sync_credit_limit(sub)

        if not items:
            return None
        invoice.total_cents = sum(amount for _, _, amount in items)
        invoice.save()
        InvoiceItem.objects.bulk_create(
            [InvoiceItem(invoice=invoice, kind=k, description=desc[:200], total_cents=amount) for k, desc, amount in items]
        )
        from .tasks import push_invoice

        transaction.on_commit(lambda: push_invoice.delay(invoice.pk))
        record("billing.renewal_invoiced", organization=sub.organization, target=invoice, amount_cents=invoice.total_cents)
        return invoice


def renew_due(on: date | None = None) -> int:
    on = on or today()
    count = 0
    for sub in Subscription.objects.filter(next_billing_date__lte=on).exclude(status=Status.TRIALING):
        if renew(sub, on):
            count += 1
    return count


def enforce_overdue(on: date | None = None) -> None:
    """Vence faturas não pagas e suspende quem passou da tolerância."""
    on = on or today()
    for inv in Invoice.objects.filter(status=Invoice.Status.OPEN, due_date__lt=on):
        if inv.kind == Invoice.Kind.PLAN_CHANGE:
            cancel_invoice(inv)  # proposta de troca não paga simplesmente expira
        else:
            mark_overdue(inv)
    limit = on - timedelta(days=GRACE_DAYS)
    late = Subscription.objects.filter(
        status=Status.PAST_DUE,
        invoices__kind=Invoice.Kind.RENEWAL,
        invoices__status=Invoice.Status.OVERDUE,
        invoices__due_date__lt=limit,
    ).distinct()
    for sub in late:
        with transaction.atomic():
            sub = Subscription.objects.select_for_update().select_related("plan", "organization").get(pk=sub.pk)
            if sub.status != Status.PAST_DUE:
                continue
            sub.status = Status.SUSPENDED
            sub.save(update_fields=["status", "updated_at"])
            sync_credit_limit(sub)
            record("billing.suspended", organization=sub.organization, target=sub)


def run_daily() -> None:
    expire_trials()
    renew_due()
    enforce_overdue()


# --- backoffice ------------------------------------------------------------------------------


def extend_trial(sub: Subscription, days: int, *, user=None, request=None) -> Subscription:
    if not 1 <= days <= 90:
        raise BusinessError("Informe entre 1 e 90 dias.")
    with transaction.atomic():
        sub = Subscription.objects.select_for_update().select_related("plan", "organization").get(pk=sub.pk)
        if sub.status != Status.TRIALING:
            if not sub.plan.is_free:
                raise BusinessError("Só é possível estender o teste de quem está em teste ou no Grátis.")
            sub.plan = Plan.objects.get(code=TRIAL_PLAN)
            sub.status = Status.TRIALING
            sub.trial_ends_at = timezone.now()
        sub.trial_ends_at = max(sub.trial_ends_at, timezone.now()) + timedelta(days=days)
        sub.save()
        sync_credit_limit(sub)
        record("admin.trial_extended", request=request, actor=user, organization=sub.organization, target=sub, days=days)
    return sub


def grant_plan(sub: Subscription, plan: Plan, cycle: str, *, user=None, request=None) -> Subscription:
    """Ativa um plano sem cobrança (cortesia, acerto manual). Fica registrado na auditoria."""
    with transaction.atomic():
        sub = Subscription.objects.select_for_update().select_related("plan", "organization").get(pk=sub.pk)
        _apply_plan(sub, plan, cycle, today())
        record("admin.plan_granted", request=request, actor=user, organization=sub.organization, target=sub, plan=plan.code)
    return sub
