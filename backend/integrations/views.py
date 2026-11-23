import hmac
import json
import logging

from django.conf import settings
from django.db import IntegrityError, transaction
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .buscars import verify_webhook
from .models import WebhookDelivery

logger = logging.getLogger(__name__)


@csrf_exempt
@require_POST
def buscars_webhook(request):
    """Verifica a assinatura, deduplica e enfileira. O resultado é buscado pelo statusUrl."""
    raw = request.body
    if not verify_webhook(raw, request.headers.get("x-buscars-timestamp", ""), request.headers.get("x-buscars-signature", "")):
        logger.warning("Webhook BusCars com assinatura inválida")
        return HttpResponse(status=401)
    try:
        payload = json.loads(raw)
    except ValueError:
        return HttpResponse(status=400)

    delivery_id = request.headers.get("x-buscars-delivery") or payload.get("deliveryId", "")
    try:
        WebhookDelivery.objects.create(
            provider="buscars", delivery_id=delivery_id[:120], event=payload.get("evento", "")[:60], payload=payload
        )
    except IntegrityError:
        return HttpResponse(status=200)  # já processado

    if consulta_id := payload.get("consultaId"):
        from consultas.tasks import refresh_consulta

        refresh_consulta.delay(consulta_id)
    return HttpResponse(status=200)


@csrf_exempt
@require_POST
def carven_webhook(request, token: str):
    """Notificação da comunicação de venda (url_notificacao). Token secreto por comunicação."""
    from comunicacao.tasks import refresh_by_token

    refresh_by_token.delay(token)
    return HttpResponse(status=200)


@csrf_exempt
@require_POST
def asaas_webhook(request):
    """Eventos de cobrança do Asaas. Autenticado pelo token configurado no painel (cabeçalho asaas-access-token)."""
    expected = settings.ASAAS.get("WEBHOOK_TOKEN", "")
    received = request.headers.get("asaas-access-token", "")
    if not expected or not hmac.compare_digest(expected.encode(), received.encode()):
        logger.warning("Webhook Asaas com token inválido")
        return HttpResponse(status=401)
    try:
        payload = json.loads(request.body)
    except ValueError:
        return HttpResponse(status=400)
    event = str(payload.get("event", ""))[:60]
    payment = payload.get("payment") if isinstance(payload.get("payment"), dict) else {}
    delivery_id = str(payload.get("id") or f"{event}:{payment.get('id', '')}")[:120]
    try:
        with transaction.atomic():
            WebhookDelivery.objects.create(provider="asaas", delivery_id=delivery_id, event=event, payload=payload)
    except IntegrityError:
        return HttpResponse(status=200)  # já processado

    from billing.tasks import handle_asaas_event

    handle_asaas_event.delay(event, payment)
    return HttpResponse(status=200)


@csrf_exempt
@require_POST
def zapsign_webhook(request, token: str):
    """Assinatura concluída ou recusada na ZapSign (token secreto na URL)."""
    expected = settings.ZAPSIGN.get("WEBHOOK_TOKEN", "")
    if not expected or not hmac.compare_digest(expected.encode(), token.encode()):
        return HttpResponse(status=401)
    try:
        payload = json.loads(request.body)
    except ValueError:
        return HttpResponse(status=400)
    from contratos.models import Documento

    doc_token = str(payload.get("token") or payload.get("doc_token") or "")[:80]
    event = str(payload.get("event_type", ""))
    doc = Documento.objects.filter(signature_provider_id=doc_token).first() if doc_token else None
    if doc is None:
        return HttpResponse(status=200)
    status = payload.get("status", "")
    if event == "doc_signed" or status == "signed":
        doc.signature_status = Documento.Signature.SIGNED
        doc.signed_file_url = str(payload.get("signed_file") or "")[:500]
    elif event == "doc_refused" or status == "refused":
        doc.signature_status = Documento.Signature.REFUSED
    doc.save(update_fields=["signature_status", "signed_file_url", "updated_at"])
    return HttpResponse(status=200)
