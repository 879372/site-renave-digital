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


@shared_task(bind=True, max_retries=8, default_retry_delay=60, acks_late=True)
def confirm_checkout_payment(self, reference, transaction_nsu, slug):
    from .webhooks import confirm_checkout

    try:
        confirmed = confirm_checkout(reference, transaction_nsu, slug)
        if not confirmed:
            # Pode haver atraso entre o aviso e a disponibilidade no payment_check.
            raise self.retry(countdown=60)
        return True
    except ProviderError as exc:
        if exc.retryable:
            raise self.retry(exc=exc)
        logger.warning("Checkout não pôde ser confirmado; revisão necessária")
        return False
