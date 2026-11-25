"""Recarga por checkout InfinitePay ou confirmação manual quando não configurado."""

from dataclasses import dataclass
from datetime import timedelta

from django.conf import settings
from django.utils import timezone


@dataclass
class Charge:
    reference: str
    payment_url: str = ""
    pix_copy_paste: str = ""
    pix_qr_base64: str = ""
    expires_at = None


class ManualProvider:
    name = "manual"

    def create_charge(self, topup):
        charge = Charge(reference=f"MAN-{topup.public_id.hex[:10].upper()}")
        charge.expires_at = timezone.now() + timedelta(days=2)
        return charge


class InfinitePayProvider:
    name = "infinitepay"

    def create_charge(self, topup):
        from billing.models import Checkout
        from integrations.infinitepay import InfinitePayClient

        checkout, _ = Checkout.objects.get_or_create(
            topup=topup, defaults={"amount_cents": topup.amount_cents, "handle": settings.INFINITEPAY["HANDLE"]}
        )
        if not checkout.url:
            checkout.url = InfinitePayClient(topup.organization).create_link(checkout, "Recarga de créditos — Revenda Digital")
            checkout.save(update_fields=["url", "updated_at"])
        return Charge(reference=checkout.reference, payment_url=checkout.url)


def get_provider():
    from billing.gateway import enabled

    return InfinitePayProvider() if enabled() else ManualProvider()
