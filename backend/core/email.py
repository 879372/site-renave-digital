"""Envio de e-mails transacionais em segundo plano (Celery), com reply-to para o suporte."""

import logging
import uuid

from celery import shared_task
from django.conf import settings
from django.core.mail import EmailMessage
from django.db import transaction

from .email_backend import DELIVERY_HEADER, ResendDeliveryError

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=5, default_retry_delay=60, acks_late=True)
def _deliver(self, subject: str, body: str, to: list[str]):
    message = EmailMessage(
        subject=subject,
        body=body,
        to=to,
        reply_to=[settings.SUPPORT_EMAIL],
        # O Celery mantém o mesmo ID ao tentar de novo ou reenfileirar a tarefa.
        headers={DELIVERY_HEADER: str(self.request.id or uuid.uuid4())},
    )
    try:
        message.send(fail_silently=False)
    except ResendDeliveryError as exc:
        if not exc.retryable:
            logger.error("Envio de e-mail recusado; confira a configuração do Resend")
            raise
        logger.warning("Falha temporária no envio; nova tentativa agendada")
        raise self.retry(exc=exc)
    except Exception as exc:
        logger.warning("Falha ao enviar e-mail; nova tentativa agendada")
        raise self.retry(exc=exc)
    provider_id = getattr(message, "resend_message_id", None)
    logger.info("E-mail aceito pelo provedor", extra={"data": {"provider_id": provider_id}})
    return {"provider_id": provider_id}


def send(subject: str, body: str, to: list[str]) -> None:
    """Agenda o envio após o commit da transação (não envia e-mail de operação desfeita)."""
    footer = "\n\n—\nREVENDA DIGITAL\nEste é um e-mail automático. Para falar com a gente, responda esta mensagem."
    transaction.on_commit(
        lambda: _deliver.apply_async(args=(subject, body + footer, to), argsrepr="(<e-mail transacional>)", kwargsrepr="{}")
    )
