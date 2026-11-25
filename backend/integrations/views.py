import hmac
import json
import logging

from django.conf import settings
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


@csrf_exempt
@require_POST
def infinitepay_webhook(request):
    """Aviso não assinado: jamais confiar em status ou valor enviados no webhook."""
    from billing.tasks import confirm_checkout_payment
    from billing.webhooks import find_checkout

    if len(request.body) > 16384:
        return HttpResponse(status=413)
    try:
        payload = json.loads(request.body)
    except ValueError:
        return HttpResponse(status=400)
    if not isinstance(payload, dict):
        return HttpResponse(status=400)
    reference = payload.get("order_nsu", "")
    checkout = find_checkout(reference)
    if checkout is None or checkout.paid_at:
        return HttpResponse(status=200)
    tx = payload.get("transaction_nsu")
    slug = payload.get("invoice_slug") or payload.get("slug")
    if not all(isinstance(value, str) and 0 < len(value) <= 120 for value in (tx, slug)):
        return HttpResponse(status=400)
    confirm_checkout_payment.apply_async(args=(reference, tx, slug), argsrepr="(<confirmação de checkout>)", kwargsrepr="{}")
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
