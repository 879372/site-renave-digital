"""Backend Django para o Resend por HTTPS, sem depender de portas SMTP."""

import uuid

import httpx
from django.conf import settings
from django.core.mail.backends.base import BaseEmailBackend

DELIVERY_HEADER = "X-Revenda-Delivery-ID"


class ResendDeliveryError(Exception):
    """Erro seguro para logs: nunca contém destinatário, corpo ou chave da API."""

    def __init__(self, message: str, *, retryable: bool = True):
        super().__init__(message)
        self.retryable = retryable


class ResendEmailBackend(BaseEmailBackend):
    def send_messages(self, email_messages):
        if not email_messages:
            return 0
        sent = 0
        with httpx.Client(timeout=settings.EMAIL_TIMEOUT) as client:
            for message in email_messages:
                if not message.recipients():
                    continue
                try:
                    self._send(client, message)
                except ResendDeliveryError:
                    if not self.fail_silently:
                        raise
                else:
                    sent += 1
        return sent

    def _send(self, client, message):
        if not settings.RESEND_API_KEY:
            raise ResendDeliveryError("RESEND_API_KEY ausente: envio não configurado.", retryable=False)
        # Validação do próprio Django, inclusive contra injeção de cabeçalhos.
        message.message()
        delivery_id = message.extra_headers.setdefault(DELIVERY_HEADER, str(uuid.uuid4()))
        payload = {
            "from": message.from_email,
            "to": message.to,
            "subject": message.subject,
            "html" if message.content_subtype == "html" else "text": message.body,
        }
        for name in ("cc", "bcc", "reply_to"):
            if value := getattr(message, name, None):
                payload[name] = value
        if headers := {k: v for k, v in message.extra_headers.items() if k != DELIVERY_HEADER}:
            payload["headers"] = headers
        for alternative in getattr(message, "alternatives", ()):
            if alternative.mimetype == "text/html":
                payload["html"] = alternative.content
        if message.attachments:
            # Os fluxos atuais enviam somente texto/HTML. Não omitir anexos silenciosamente.
            raise ResendDeliveryError("Anexos não são suportados neste envio transacional.", retryable=False)
        try:
            response = client.post(
                "https://api.resend.com/emails",
                headers={"Authorization": f"Bearer {settings.RESEND_API_KEY}", "Idempotency-Key": f"revenda/{delivery_id}"},
                json=payload,
            )
        except httpx.RequestError as exc:
            raise ResendDeliveryError("Falha de conexão com o Resend por HTTPS.", retryable=True) from exc
        if not response.is_success:
            raise ResendDeliveryError(
                f"Resend recusou o envio (HTTP {response.status_code}).",
                retryable=response.status_code in (408, 429) or response.status_code >= 500,
            )
        try:
            message.resend_message_id = response.json()["id"]
            if not isinstance(message.resend_message_id, str) or not message.resend_message_id:
                raise ValueError
        except (ValueError, KeyError, TypeError) as exc:
            raise ResendDeliveryError("Resposta inesperada do Resend; confirmação de envio ausente.", retryable=True) from exc
