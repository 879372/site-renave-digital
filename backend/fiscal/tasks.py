from celery import shared_task

from integrations.http import ProviderError

from . import service
from .models import NotaFiscal


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def emitir_nfe(self, nota_id: int):
    nota = NotaFiscal.objects.select_related("organization", "vehicle", "reservation").filter(pk=nota_id).first()
    if nota is None:
        return
    try:
        service.emitir(nota)
    except ProviderError as exc:
        if exc.retryable and self.request.retries < self.max_retries:
            raise self.retry(exc=exc)
        if nota.reservation:
            from wallet import service as wallet

            wallet.release(nota.reservation, "falha de comunicação")
            nota.reservation = None
            nota.save(update_fields=["reservation", "updated_at"])
