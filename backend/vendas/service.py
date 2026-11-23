"""Ciclo da venda: proposta → reserva (sinal) → fechamento → (cancelamento).

No fechamento, tudo acontece numa transação:
- o carro vira "vendido" e o valor fica congelado na venda (custo, repasse, lucro);
- cada forma de pagamento vira conta a receber (à vista já baixada; boleto parcelado; financiamento a receber do banco);
- carro na troca entra no estoque pela avaliação;
- consignado gera o repasse a pagar ao dono;
- comissão do vendedor é calculada (paga no fechamento mensal de comissões);
- garantia legal de 90 dias é registrada.
NF-e e saída do RENAVE são ações separadas (exigem dados que só a loja informa).
"""

from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from audit.service import record
from billing.entitlements import has_feature
from core.exceptions import BusinessError
from estoque.models import Avaliacao, Vehicle
from estoque.service import buy_from_evaluation

from .models import Pagamento, RegraComissao, Venda

M = Pagamento.Method
IMMEDIATE = {M.DINHEIRO, M.PIX, M.TRANSFERENCIA, M.DEBITO}
WARRANTY_DAYS = 90


def _fin():
    from financeiro import service as fin

    return fin


def validate_payments(venda: Venda) -> None:
    pays = list(venda.pagamentos.all())
    if not pays:
        raise BusinessError("Informe as formas de pagamento antes de fechar.")
    total = sum(p.amount_cents for p in pays)
    if total != venda.price_cents:
        diff = venda.price_cents - total
        raise BusinessError(
            f"A soma dos pagamentos ({total / 100:.2f}) não bate com o valor da venda ({venda.price_cents / 100:.2f}).".replace(".", ","),
            code="payments_mismatch",
            extra={"difference_cents": diff},
        )
    for p in pays:
        if p.method == M.TROCA and not p.trade_in_id:
            raise BusinessError("Pagamento com troca precisa de uma avaliação aprovada.")


def set_payments(venda: Venda, items: list[dict]) -> Venda:
    if venda.status in (Venda.Status.FECHADA, Venda.Status.CANCELADA):
        raise BusinessError("Venda fechada ou cancelada não pode mudar os pagamentos.")
    with transaction.atomic():
        keep_sinal = venda.pagamentos.filter(method=M.SINAL)
        venda.pagamentos.exclude(pk__in=keep_sinal).delete()
        for item in items:
            if item["method"] == M.SINAL:
                continue  # sinal só entra pela reserva
            trade = item.get("trade_in")
            if trade is not None:
                if trade.status not in (Avaliacao.Status.APROVADA,):
                    raise BusinessError("A avaliação da troca precisa estar aprovada.")
                if Pagamento.objects.filter(trade_in=trade).exclude(venda=venda).exists():
                    raise BusinessError("Esta avaliação já foi usada em outra venda.")
            Pagamento.objects.create(
                venda=venda,
                method=item["method"],
                amount_cents=item["amount_cents"],
                installments=item.get("installments") or 1,
                first_due=item.get("first_due"),
                bank=item.get("bank", ""),
                trade_in=trade if item["method"] == M.TROCA else None,
            )
    return venda


@transaction.atomic
def reserve(venda: Venda, *, amount_cents: int, until, user=None, method=M.PIX) -> Venda:
    venda = Venda.objects.select_for_update().get(pk=venda.pk)
    vehicle = Vehicle.objects.select_for_update().get(pk=venda.vehicle_id)
    if venda.status != Venda.Status.PROPOSTA:
        raise BusinessError("Só propostas podem ser reservadas.")
    if vehicle.status not in (Vehicle.Status.DISPONIVEL, Vehicle.Status.PREPARACAO):
        raise BusinessError("Este veículo não está disponível para reserva.")
    if amount_cents <= 0 or amount_cents > venda.price_cents:
        raise BusinessError("Valor de sinal inválido.")
    Pagamento.objects.create(venda=venda, method=M.SINAL, amount_cents=amount_cents)
    venda.status = Venda.Status.RESERVADA
    venda.reserved_until = until
    venda.save(update_fields=["status", "reserved_until", "updated_at"])
    vehicle.status = Vehicle.Status.RESERVADO
    vehicle.save(update_fields=["status", "updated_at"])
    if has_feature(venda.organization, "financeiro"):
        _fin().create(
            venda.organization,
            kind="receber",
            origin="venda",
            description=f"Sinal — {vehicle.title}",
            amount_cents=amount_cents,
            due_date=timezone.localdate(),
            category_code="venda_veiculo",
            paid=True,
            pessoa=venda.cliente,
            vehicle=vehicle,
            venda=venda,
        )
    record("vendas.reserva", actor=user, organization=venda.organization, target=venda, amount_cents=amount_cents)
    return venda


def _commission(venda: Venda, profit: int) -> int:
    if not venda.seller_id or not has_feature(venda.organization, "comissoes"):
        return 0
    rule = RegraComissao.objects.filter(organization=venda.organization).first()
    if rule is None:
        return 0
    return rule.compute(price_cents=venda.price_cents, profit_cents=profit)


@transaction.atomic
def close(venda: Venda, *, user=None, closed_at=None) -> Venda:
    venda = Venda.objects.select_for_update().get(pk=venda.pk)
    vehicle = Vehicle.objects.select_for_update().get(pk=venda.vehicle_id)
    if venda.status not in (Venda.Status.PROPOSTA, Venda.Status.RESERVADA):
        raise BusinessError("Esta venda já foi fechada ou cancelada.")
    if vehicle.status not in (Vehicle.Status.DISPONIVEL, Vehicle.Status.PREPARACAO, Vehicle.Status.RESERVADO):
        raise BusinessError("Este veículo não está disponível para venda.")
    if vehicle.status == Vehicle.Status.RESERVADO and venda.status != Venda.Status.RESERVADA:
        other = Venda.objects.filter(vehicle=vehicle, status=Venda.Status.RESERVADA).exclude(pk=venda.pk).exists()
        if other:
            raise BusinessError("Este veículo está reservado em outra negociação.")
    validate_payments(venda)

    org = venda.organization
    day = closed_at or timezone.localdate()
    cost = vehicle.total_cost()
    payout = vehicle.consignor_payout(venda.price_cents)
    profit = venda.price_cents - cost - payout
    venda.cost_cents = cost
    venda.consignor_payout_cents = payout
    venda.vehicle_was_published = vehicle.published
    venda.profit_cents = profit
    venda.commission_cents = _commission(venda, profit)
    venda.status = Venda.Status.FECHADA
    venda.closed_at = day
    venda.save()

    vehicle.status = Vehicle.Status.VENDIDO
    vehicle.sold_at = day
    vehicle.published = False
    vehicle.save(update_fields=["status", "sold_at", "published", "updated_at"])

    use_fin = has_feature(org, "financeiro")
    for p in venda.pagamentos.select_related("trade_in"):
        if p.method == M.SINAL:
            continue  # já lançado e baixado na reserva
        if p.method == M.TROCA:
            buy_from_evaluation(p.trade_in, user=user, price_cents=p.amount_cents, purchase_date=day, as_trade_in=True)
            continue
        if not use_fin:
            continue
        label = f"{p.get_method_display()} — {vehicle.title}"
        if p.method in IMMEDIATE:
            _fin().create(
                org,
                kind="receber",
                origin="venda",
                description=label,
                amount_cents=p.amount_cents,
                due_date=day,
                category_code="venda_veiculo",
                paid=True,
                pessoa=venda.cliente,
                vehicle=vehicle,
                venda=venda,
            )
        elif p.method == M.CREDITO:
            # Recebimento da maquininha em parcelas mensais (antecipação fica a cargo da loja).
            _fin().create(
                org,
                kind="receber",
                origin="venda",
                description=label,
                amount_cents=p.amount_cents,
                due_date=p.first_due or day + timedelta(days=30),
                installments=p.installments,
                category_code="venda_veiculo",
                pessoa=venda.cliente,
                vehicle=vehicle,
                venda=venda,
            )
        elif p.method == M.FINANCIAMENTO:
            _fin().create(
                org,
                kind="receber",
                origin="venda",
                description=f"Financiamento {p.bank} — {vehicle.title}".strip(),
                amount_cents=p.amount_cents,
                due_date=p.first_due or day + timedelta(days=7),
                category_code="venda_veiculo",
                pessoa=venda.cliente,
                vehicle=vehicle,
                venda=venda,
            )
        else:  # boleto / promissória
            _fin().create(
                org,
                kind="receber",
                origin="venda",
                description=label,
                amount_cents=p.amount_cents,
                due_date=p.first_due or day + timedelta(days=30),
                installments=p.installments,
                category_code="venda_veiculo",
                pessoa=venda.cliente,
                vehicle=vehicle,
                venda=venda,
            )

    if payout and use_fin:
        _fin().create(
            org,
            kind="pagar",
            origin="consignacao",
            description=f"Repasse do consignado — {vehicle.title}",
            amount_cents=payout,
            due_date=day + timedelta(days=5),
            category_code="consignacao",
            pessoa=vehicle.consignor,
            vehicle=vehicle,
            venda=venda,
        )

    from posvenda.models import Garantia

    Garantia.objects.get_or_create(
        venda=venda, defaults={"organization": org, "starts_on": day, "ends_on": day + timedelta(days=WARRANTY_DAYS)}
    )
    if venda.lead_id:
        from crm.models import Lead

        Lead.objects.filter(pk=venda.lead_id).update(stage=Lead.Stage.GANHO)
    # Outras propostas abertas do mesmo carro deixam de valer.
    Venda.objects.filter(vehicle=vehicle, status__in=[Venda.Status.PROPOSTA]).exclude(pk=venda.pk).update(
        status=Venda.Status.CANCELADA, canceled_at=timezone.now(), cancel_reason="Veículo vendido em outra negociação"
    )
    record("vendas.fechada", actor=user, organization=org, target=venda, price_cents=venda.price_cents, profit_cents=profit)
    return venda


@transaction.atomic
def cancel(venda: Venda, *, reason: str, user=None) -> dict:
    venda = Venda.objects.select_for_update().get(pk=venda.pk)
    if venda.status == Venda.Status.CANCELADA:
        raise BusinessError("Venda já cancelada.")
    if len(reason.strip()) < 5:
        raise BusinessError("Informe o motivo do cancelamento.")
    vehicle = Vehicle.objects.select_for_update().get(pk=venda.vehicle_id)
    was_closed = venda.status == Venda.Status.FECHADA
    if was_closed:
        traded = [p.trade_in for p in venda.pagamentos.filter(method=M.TROCA).select_related("trade_in__vehicle")]
        for av in traded:
            if av and av.vehicle and av.vehicle.status == Vehicle.Status.VENDIDO:
                raise BusinessError("O carro recebido na troca já foi vendido. Cancele manualmente com o financeiro.")
        if venda.commission_paid:
            raise BusinessError("A comissão desta venda já foi paga. Acerte com o vendedor antes de cancelar.")
    canceled = _fin().cancel_open(venda.lancamentos.all()) if venda.lancamentos.exists() else 0
    paid = venda.lancamentos.filter(paid_at__isnull=False).count()
    if vehicle.status in (Vehicle.Status.VENDIDO, Vehicle.Status.RESERVADO):
        vehicle.status = Vehicle.Status.DISPONIVEL
        vehicle.sold_at = None
        if was_closed:
            vehicle.published = venda.vehicle_was_published
        vehicle.save(update_fields=["status", "sold_at", "published", "updated_at"])
    if was_closed:
        for p in venda.pagamentos.filter(method=M.TROCA).select_related("trade_in__vehicle"):
            av = p.trade_in
            if av and av.vehicle:
                av.vehicle.status = Vehicle.Status.DEVOLVIDO
                av.vehicle.save(update_fields=["status", "updated_at"])
                av.status = Avaliacao.Status.APROVADA
                av.vehicle = None
                av.save(update_fields=["status", "vehicle", "updated_at"])
        if hasattr(venda, "garantia"):
            venda.garantia.delete()
    venda.status = Venda.Status.CANCELADA
    venda.canceled_at = timezone.now()
    venda.cancel_reason = reason.strip()[:200]
    venda.save(update_fields=["status", "canceled_at", "cancel_reason", "updated_at"])
    record("vendas.cancelada", actor=user, organization=venda.organization, target=venda, reason=reason)
    return {"canceled_entries": canceled, "paid_entries_to_refund": paid}


def commissions_report(organization, month_start, month_end) -> list[dict]:
    from django.db.models import Count, Sum

    rows = (
        Venda.objects.filter(organization=organization, status=Venda.Status.FECHADA, closed_at__range=(month_start, month_end))
        .values("seller__public_id", "seller__full_name")
        .annotate(units=Count("id"), revenue=Sum("price_cents"), profit=Sum("profit_cents"), commission=Sum("commission_cents"))
        .order_by("-revenue")
    )
    from .models import Meta

    metas = {m.seller_id: m for m in Meta.objects.filter(organization=organization, month=month_start)}
    out = []
    for r in rows:
        meta = next((m for m in metas.values() if str(m.seller.public_id) == str(r["seller__public_id"])), None)
        pending = Venda.objects.filter(
            organization=organization,
            status=Venda.Status.FECHADA,
            closed_at__range=(month_start, month_end),
            seller__public_id=r["seller__public_id"],
            commission_paid=False,
        ).aggregate(v=Sum("commission_cents"))["v"]
        out.append(
            {
                "seller_id": str(r["seller__public_id"]) if r["seller__public_id"] else None,
                "seller_name": r["seller__full_name"] or "Sem vendedor",
                "units": r["units"],
                "revenue_cents": r["revenue"] or 0,
                "profit_cents": r["profit"] or 0,
                "commission_cents": r["commission"] or 0,
                "commission_pending_cents": pending or 0,
                "goal_units": meta.units if meta else None,
                "goal_revenue_cents": meta.revenue_cents if meta else None,
            }
        )
    return out


@transaction.atomic
def pay_commissions(organization, month_start, month_end, *, user=None) -> int:
    """Gera uma conta a pagar por vendedor com as comissões ainda não pagas do período."""
    base = Venda.objects.filter(
        organization=organization,
        status=Venda.Status.FECHADA,
        closed_at__range=(month_start, month_end),
        commission_paid=False,
        commission_cents__gt=0,
        seller__isnull=False,
    )
    created = 0
    for seller_id in sorted(set(base.values_list("seller_id", flat=True))):
        group = list(base.filter(seller_id=seller_id).select_for_update().select_related("seller"))
        if not group:
            continue
        total = sum(v.commission_cents for v in group)
        seller = group[0].seller
        if total and has_feature(organization, "financeiro"):
            _fin().create(
                organization,
                kind="pagar",
                origin="comissao",
                description=f"Comissões de {seller.full_name} — {month_start:%m/%Y}",
                amount_cents=total,
                due_date=timezone.localdate() + timedelta(days=5),
                category_code="comissao",
            )
        Venda.objects.filter(pk__in=[v.pk for v in group]).update(commission_paid=True)
        created += 1
    record("vendas.comissoes_fechadas", actor=user, organization=organization, month=month_start.isoformat(), sellers=created)
    return created
