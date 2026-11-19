from celery import shared_task

from . import service
from .models import ComunicacaoVenda


@shared_task
def refresh_by_token(token: str):
    cv = ComunicacaoVenda.objects.select_related("organization").filter(notify_token=token).first()
    if cv:
        service.refresh(cv)
