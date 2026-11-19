import json
import logging

from django.db import IntegrityError
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
