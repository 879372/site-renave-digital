import logging

from celery import shared_task

from integrations.http import ProviderError

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=5, default_retry_delay=60)
def push_invoice(self, invoice_id: int):
    from . import gateway
    from .models import Invoice

    invoice = Invoice.objects.select_related("organization").filter(pk=invoice_id).first()
    if invoice is None:
        return
    try:
        gateway.push_invoice(invoice)
    except ProviderError as exc:
        if exc.retryable:
            raise self.retry(exc=exc)
        logger.error("Fatura %s recusada pelo gateway: %s", invoice.public_id, exc)


@shared_task(bind=True, max_retries=5, default_retry_delay=60)
def cancel_gateway_payment(self, invoice_id: int):
    from . import gateway
    from .models import Invoice

    invoice = Invoice.objects.select_related("organization").filter(pk=invoice_id).first()
    if invoice is None:
        return
    try:
        gateway.cancel_payment(invoice)
    except ProviderError as exc:
        if exc.retryable:
            raise self.retry(exc=exc)
        logger.warning("Não foi possível cancelar a cobrança da fatura %s: %s", invoice.public_id, exc)


@shared_task
def run_daily():
    from .service import run_daily as run

    run()


@shared_task
def handle_asaas_event(event: str, payment: dict):
    from .webhooks import handle_asaas_event as handle

    handle(event, payment)
