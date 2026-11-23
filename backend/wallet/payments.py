"""Provedores de pagamento para recarga.

Com `ASAAS_API_KEY` configurada, a recarga gera uma cobrança Pix no Asaas e o
webhook (`/api/hooks/asaas`) confirma o crédito. Sem a chave, `ManualProvider`
deixa a recarga pendente e o financeiro confirma pelo admin (com auditoria).
"""

from dataclasses import dataclass
from datetime import timedelta

from django.utils import timezone


@dataclass
class Charge:
    reference: str
    pix_copy_paste: str = ""
    pix_qr_base64: str = ""
    expires_at = None


class ManualProvider:
    name = "manual"

    def create_charge(self, topup) -> Charge:
        charge = Charge(reference=f"MAN-{topup.public_id.hex[:10].upper()}")
        charge.expires_at = timezone.now() + timedelta(days=2)
        return charge


class AsaasProvider:
    name = "asaas"

    def create_charge(self, topup) -> Charge:
        from datetime import datetime

        from billing.gateway import ensure_customer
        from integrations.asaas import AsaasClient

        client = AsaasClient(topup.organization)
        payment = client.create_payment(
            customer=ensure_customer(topup.organization),
            value_cents=topup.amount_cents,
            due_date=(timezone.localdate() + timedelta(days=1)).isoformat(),
            description="Recarga de créditos — REVENDA DIGITAL",
            external_reference=f"topup:{topup.public_id}",
            billing_type="PIX",
        )
        qr = client.pix_qr_code(payment["id"])
        charge = Charge(reference=payment["id"], pix_copy_paste=qr.get("payload", ""), pix_qr_base64=qr.get("encodedImage", ""))
        expires = qr.get("expirationDate")
        try:
            charge.expires_at = timezone.make_aware(datetime.fromisoformat(expires)) if expires else None
        except ValueError:
            charge.expires_at = None
        return charge


def get_provider():
    from billing.gateway import enabled

    return AsaasProvider() if enabled() else ManualProvider()
