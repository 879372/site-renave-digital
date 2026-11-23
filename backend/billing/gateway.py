"""Ponte entre faturas/recargas e o gateway de pagamento.

Sem `ASAAS_API_KEY`, nada é enviado: a fatura fica sem link e o financeiro
confirma o pagamento pelo backoffice (com auditoria).
"""

from django.conf import settings
from django.db import IntegrityError

from .models import GatewayCustomer, Invoice

ASAAS = "asaas"


def enabled() -> bool:
    return bool(settings.ASAAS.get("API_KEY"))


def ensure_customer(organization) -> str:
    from integrations.asaas import AsaasClient

    existing = GatewayCustomer.objects.filter(organization=organization, provider=ASAAS).first()
    if existing:
        return existing.customer_id
    data = AsaasClient(organization).create_customer(
        name=organization.legal_name,
        cpf_cnpj=organization.cnpj,
        email=organization.email,
        phone=organization.phone,
        external_reference=f"org:{organization.public_id}",
    )
    try:
        GatewayCustomer.objects.create(organization=organization, provider=ASAAS, customer_id=data["id"])
    except IntegrityError:
        return GatewayCustomer.objects.get(organization=organization, provider=ASAAS).customer_id
    return data["id"]


def invoice_description(invoice: Invoice) -> str:
    lines = "; ".join(f"{item.description}: R$ {item.total_cents / 100:.2f}".replace(".", ",") for item in invoice.items.all())
    return f"Revenda Digital — {lines}"


def push_invoice(invoice: Invoice) -> Invoice:
    """Cria a cobrança avulsa no gateway (o cliente escolhe Pix, boleto ou cartão no link)."""
    from integrations.asaas import AsaasClient

    if not enabled() or invoice.provider_payment_id or invoice.status != Invoice.Status.OPEN or invoice.total_cents <= 0:
        return invoice
    customer = ensure_customer(invoice.organization)
    data = AsaasClient(invoice.organization).create_payment(
        customer=customer,
        value_cents=invoice.total_cents,
        due_date=invoice.due_date.isoformat(),
        description=invoice_description(invoice),
        external_reference=f"invoice:{invoice.public_id}",
    )
    invoice.provider = ASAAS
    invoice.provider_payment_id = data["id"]
    invoice.payment_url = data.get("invoiceUrl", "")
    invoice.save(update_fields=["provider", "provider_payment_id", "payment_url", "updated_at"])
    return invoice


def cancel_payment(invoice: Invoice) -> None:
    from integrations.asaas import AsaasClient

    if enabled() and invoice.provider == ASAAS and invoice.provider_payment_id:
        AsaasClient(invoice.organization).delete_payment(invoice.provider_payment_id)
