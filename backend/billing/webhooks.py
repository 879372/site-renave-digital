"""Eventos de pagamento do Asaas. `externalReference` diz o que foi pago:
`invoice:<uuid>` (fatura da assinatura) ou `topup:<uuid>` (recarga da carteira).
"""

import logging
import uuid

from wallet.models import TopUp
from wallet.service import cancel_topup, confirm_topup

from . import service
from .models import Invoice

logger = logging.getLogger(__name__)

PAID = {"PAYMENT_RECEIVED", "PAYMENT_CONFIRMED"}
GONE = {"PAYMENT_DELETED"}
OVERDUE = {"PAYMENT_OVERDUE"}


def _target(reference: str):
    kind, _, raw = (reference or "").partition(":")
    try:
        public_id = uuid.UUID(raw)
    except ValueError:
        return None
    if kind == "invoice":
        return Invoice.objects.filter(public_id=public_id).first()
    if kind == "topup":
        return TopUp.objects.filter(public_id=public_id).first()
    return None


def _same_payment(obj, payment: dict) -> bool:
    ref = getattr(obj, "provider_payment_id", None) or getattr(obj, "provider_reference", "")
    return not ref or ref == payment.get("id")


def handle_asaas_event(event: str, payment: dict) -> None:
    obj = _target(payment.get("externalReference", ""))
    if obj is None:
        logger.info("Evento Asaas %s sem referência conhecida", event)
        return
    if not _same_payment(obj, payment):
        logger.warning("Evento Asaas %s com cobrança diferente da registrada", event)
        return

    if isinstance(obj, Invoice):
        if event in PAID:
            expected = obj.total_cents
            received = round(float(payment.get("value", 0)) * 100)
            if received < expected:
                logger.error("Fatura %s paga com valor menor (%s < %s)", obj.public_id, received, expected)
                return
            service.mark_paid(obj)
        elif event in OVERDUE:
            service.mark_overdue(obj)
        elif event in GONE:
            service.cancel_invoice(obj)
        return

    if event in PAID:
        received = round(float(payment.get("value", 0)) * 100)
        if received < obj.amount_cents:
            logger.error("Recarga %s paga com valor menor", obj.public_id)
            return
        confirm_topup(obj)
    elif event in GONE | OVERDUE:
        cancel_topup(obj)
