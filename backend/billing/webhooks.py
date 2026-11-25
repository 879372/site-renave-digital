"""Confirmação segura, compartilhada entre webhook e retorno autenticado."""

import logging
import uuid

from django.db import IntegrityError, transaction
from django.utils import timezone

from audit.service import record
from integrations.http import ProviderError
from integrations.infinitepay import InfinitePayClient
from wallet.models import TopUp
from wallet.service import confirm_topup

from . import service
from .gateway import PROVIDER, _notify
from .models import Checkout, Invoice

logger = logging.getLogger(__name__)


def find_checkout(reference):
    if not isinstance(reference, str) or not reference.startswith("revenda-"):
        return None
    try:
        public_id = uuid.UUID(reference[8:])
    except (ValueError, TypeError):
        return None
    return Checkout.objects.select_related("invoice__organization", "topup__organization").filter(public_id=public_id).first()


def confirm_checkout(reference, transaction_nsu, slug):
    checkout = find_checkout(reference)
    if checkout is None or not transaction_nsu or not slug:
        return False
    if checkout.paid_at:
        return True
    data = InfinitePayClient(checkout.organization).payment_check(checkout, transaction_nsu, slug)
    if data.get("success") is not True or data.get("paid") is not True:
        return False
    if type(data.get("amount")) is not int or data["amount"] != checkout.amount_cents:
        logger.warning("Checkout %s: valor divergente", checkout.public_id)
        return False
    paid_amount = data.get("paid_amount")
    if type(paid_amount) is not int or paid_amount < checkout.amount_cents:
        return False
    try:
        with transaction.atomic():
            # Mesma ordem do gerador do link: alvo antes do checkout, evitando
            # deadlock entre abrir a fatura e confirmar o pagamento simultaneamente.
            if checkout.invoice_id:
                Invoice.objects.select_for_update().get(pk=checkout.invoice_id)
            else:
                TopUp.objects.select_for_update().get(pk=checkout.topup_id)
            checkout = Checkout.objects.select_for_update().get(pk=checkout.pk)
            if checkout.paid_at:
                return True
            checkout.transaction_nsu = transaction_nsu
            checkout.slug = slug
            checkout.paid_at = timezone.now()
            checkout.save(update_fields=["transaction_nsu", "slug", "paid_at", "updated_at"])
            obj = checkout.invoice if checkout.invoice_id else checkout.topup
            expected = obj.total_cents if checkout.invoice_id else obj.amount_cents
            if expected != checkout.amount_cents or obj.provider != PROVIDER:
                raise ProviderError("Pedido alterado; confirmação exige revisão manual.")
            if checkout.invoice_id:
                service.mark_paid(obj)
            elif obj.status == "pending":
                confirm_topup(obj)
            elif obj.status != "paid":
                record("billing.paid_canceled_topup", organization=obj.organization, target=obj)
            _notify(checkout, paid=True)
    except IntegrityError:
        # Identificador da transação já vinculado a outro checkout: nunca creditar de novo.
        logger.warning("Checkout %s: transação já vinculada", checkout.public_id)
        return False
    return True
