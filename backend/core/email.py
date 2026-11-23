"""Envio de e-mails transacionais em segundo plano (Celery), com reply-to para o suporte."""

import logging

from celery import shared_task
from django.conf import settings
from django.core.mail import EmailMessage
from django.db import transaction

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=5, default_retry_delay=60, acks_late=True)
def _deliver(self, subject: str, body: str, to: list[str]):
    message = EmailMessage(subject=subject, body=body, to=to, reply_to=[settings.SUPPORT_EMAIL])
    try:
        message.send(fail_silently=False)
    except Exception as exc:
        logger.warning("Falha ao enviar e-mail; nova tentativa agendada")
        raise self.retry(exc=exc)


def send(subject: str, body: str, to: list[str]) -> None:
    """Agenda o envio após o commit da transação (não envia e-mail de operação desfeita)."""
    footer = "\n\n—\nREVENDA DIGITAL\nEste é um e-mail automático. Para falar com a gente, responda esta mensagem."
    transaction.on_commit(lambda: _deliver.delay(subject, body + footer, to))
