from datetime import timedelta

from celery import shared_task
from django.utils import timezone

from integrations.http import ProviderError

from . import service
from .models import Consulta


@shared_task(bind=True, max_retries=5, default_retry_delay=30)
def refresh_consulta(self, provider_consulta_id: str):
    consulta = Consulta.objects.filter(provider_consulta_id=provider_consulta_id).select_related("organization", "reservation").first()
    if consulta is None:
        return
    try:
        service.refresh(consulta)
    except ProviderError as exc:
        raise self.retry(exc=exc)


@shared_task
def sweep_pending():
    """Contingência do webhook: revisa consultas em processamento há mais de 5 minutos."""
    limit = timezone.now() - timedelta(minutes=5)
    ids = (
        Consulta.objects.filter(status__in=[Consulta.Status.PENDING, Consulta.Status.PROCESSING], updated_at__lt=limit)
        .exclude(provider_consulta_id="")
        .values_list("provider_consulta_id", flat=True)[:200]
    )
    for provider_id in ids:
        refresh_consulta.delay(provider_id)
