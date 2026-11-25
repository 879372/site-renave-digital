"""Cobranças por checkout InfinitePay, com e-mails transacionais pelo Resend."""

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from core.email import send
from integrations.infinitepay import InfinitePayClient

from .models import Checkout, Invoice

PROVIDER = "infinitepay"


def enabled():
    # A handle também é necessária para conferir a conta recebedora no payment_check.
    return bool(settings.INFINITEPAY["HANDLE"])


def _notify(checkout, *, paid=False):
    org = checkout.organization
    recipients = (
        [org.email]
        if org.email
        else list(org.memberships.filter(role="owner", is_active=True, user__is_active=True).values_list("user__email", flat=True))
    )
    recipients = [email for email in recipients if email and not email.endswith(".invalid")]
    field = "receipt_emailed_at" if paid else "link_emailed_at"
    if getattr(checkout, field) or not recipients:
        return
    amount = f"R$ {checkout.amount_cents / 100:.2f}".replace(".", ",")
    if paid:
        subject = "Pagamento confirmado — Revenda Digital"
        body = f"Olá, {org}!\n\nConfirmamos o pagamento de {amount}.\nReferência: {checkout.reference}.\nAcompanhe sua assinatura na plataforma."
    else:
        invoice = checkout.invoice
        subject = "Sua fatura está disponível — Revenda Digital"
        body = (
            f"Olá, {org}!\n\nSua fatura de {amount} vence em {invoice.due_date:%d/%m/%Y}.\n"
            f"Pague por Pix ou cartão no checkout InfinitePay:\n{checkout.url}\n\n"
            "O plano é liberado após a confirmação do pagamento. A renovação não debita seu cartão automaticamente."
        )
    send(subject, body, list(dict.fromkeys(recipients)))
    setattr(checkout, field, timezone.now())
    checkout.save(update_fields=[field, "updated_at"])


@transaction.atomic
def push_invoice(invoice):
    invoice = Invoice.objects.select_for_update().get(pk=invoice.pk)
    if not enabled() or invoice.status not in (Invoice.Status.OPEN, Invoice.Status.OVERDUE) or invoice.total_cents <= 0:
        return invoice
    checkout, _ = Checkout.objects.get_or_create(
        invoice=invoice, defaults={"amount_cents": invoice.total_cents, "handle": settings.INFINITEPAY["HANDLE"]}
    )
    if not checkout.url:
        checkout.url = InfinitePayClient(invoice.organization).create_link(checkout, "Revenda Digital — assinatura e consumo")
        checkout.save(update_fields=["url", "updated_at"])
    invoice.provider = PROVIDER
    invoice.provider_payment_id = checkout.reference
    invoice.payment_url = checkout.url
    invoice.save(update_fields=["provider", "provider_payment_id", "payment_url", "updated_at"])
    _notify(checkout)
    return invoice


def cancel_payment(invoice):
    # A InfinitePay não oferece cancelamento de links. Pagamentos tardios ficam
    # registrados e não reativam planos de faturas canceladas (billing.service).
    return None
