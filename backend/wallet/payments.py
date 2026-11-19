"""Provedores de pagamento para recarga.

`ManualProvider` é o padrão até o gateway Pix ser contratado: a recarga fica
pendente e o time financeiro confirma pelo admin (com auditoria). Para plugar um
gateway, implemente `create_charge` e um webhook que chame `service.confirm_topup`.
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


def get_provider():
    return ManualProvider()
