"""Execução de consultas BusCars com reserva e cobrança espelhando o provedor.

Regra: o cliente paga quando a BusCars cobra (sucesso, ou falha com `cobrado: true`).
Nunca segure transação de banco durante a chamada HTTP.
"""

import logging

from django.db import transaction
from django.utils import timezone

from core import documents
from core.exceptions import BusinessError, ProviderUnavailable
from core.masking import scrub_provider
from integrations.buscars import BusCarsClient
from integrations.http import ProviderError
from wallet import service as wallet

from .models import Consulta, InputType, Product

logger = logging.getLogger(__name__)


def normalize_input(input_type: str, value: str) -> str:
    value = (value or "").strip()
    if input_type == InputType.PLACA:
        value = documents.normalize_plate(value)
        if not documents.is_valid_plate(value):
            raise BusinessError("Placa inválida. Use o formato ABC1D23 ou ABC1234.", code="invalid_input")
    elif input_type == InputType.CHASSI:
        value = value.replace(" ", "").upper()
        if not documents.is_valid_vin(value):
            raise BusinessError("Chassi inválido (17 caracteres, sem I, O ou Q).", code="invalid_input")
    elif input_type == InputType.RENAVAM:
        value = documents.only_digits(value).zfill(11)
        if not documents.is_valid_renavam(value):
            raise BusinessError("RENAVAM inválido.", code="invalid_input")
    elif input_type == InputType.CPF:
        value = documents.only_digits(value)
        if not documents.is_valid_cpf(value):
            raise BusinessError("CPF inválido.", code="invalid_input")
    elif input_type == InputType.CNPJ:
        value = documents.normalize_cnpj(value)
        if not documents.is_valid_cnpj(value):
            raise BusinessError("CNPJ inválido.", code="invalid_input")
    else:
        value = value.upper()
        if not 3 <= len(value) <= 30:
            raise BusinessError("Identificador inválido.", code="invalid_input")
    return value


def start(*, organization, user, product: Product, value: str, purpose: str) -> Consulta:
    if not product.is_active:
        raise BusinessError("Produto indisponível.", code="product_unavailable")
    normalized = normalize_input(product.input_type, value)
    with transaction.atomic():  # sem saldo: nada fica gravado
        consulta = Consulta.objects.create(
            organization=organization,
            user=user,
            product=product,
            sku=product.sku,
            input_type=product.input_type,
            input_value=normalized,
            purpose=purpose,
            price_cents=product.price_cents,
        )
        consulta.reservation = wallet.reserve(
            organization,
            product.price_cents,
            f"Consulta {product.name} — {normalized}",
            ref_type="consulta",
            ref_id=consulta.public_id,
            user=user,
        )
        consulta.save(update_fields=["reservation"])

    client = BusCarsClient(organization)
    try:
        if product.is_async:
            resp = client.criar_assincrona(product.input_type, product.sku, normalized, idempotency_key=consulta.idempotency_key)
        else:
            resp = client.consultar(product.sku, normalized, idempotency_key=consulta.idempotency_key)
    except ProviderError as exc:
        _fail(consulta, "Serviço de consultas indisponível no momento. O valor foi estornado.", charged=False)
        raise ProviderUnavailable() from exc

    apply_response(consulta, resp.status_code, resp.data)
    return consulta


def apply_response(consulta: Consulta, status_code: int, payload) -> Consulta:
    payload = payload if isinstance(payload, dict) else {}
    data = payload.get("data") or {}

    if status_code == 202 or (data.get("status") in {"PENDENTE", "PROCESSANDO"}):
        consulta.status = Consulta.Status.PROCESSING
        consulta.provider_consulta_id = data.get("consultaId", consulta.provider_consulta_id)
        consulta.message = scrub_provider(data.get("motivo", "")) or "Em processamento. Avisaremos quando ficar pronto."
        consulta.save(update_fields=["status", "provider_consulta_id", "message", "updated_at"])
        return consulta

    if payload.get("success") and status_code == 200:
        return _finish(consulta, data)

    details = payload.get("details") or {}
    charged = bool(details.get("cobrado") or data.get("cobrado"))
    message = scrub_provider(payload.get("error")) or "Não foi possível concluir a consulta."

    if status_code == 402:
        logger.error("Saldo do provedor de consultas insuficiente", extra={"data": {"consulta": str(consulta.public_id)}})
        _fail(consulta, "Serviço de consultas temporariamente indisponível. O valor foi estornado.", charged=False)
        raise ProviderUnavailable()
    if status_code in (400, 404, 422):
        _fail(consulta, f"{message} O valor foi estornado.", charged=charged)
        raise BusinessError(message, code="invalid_input")
    _fail(consulta, "Consulta indisponível no momento." + ("" if charged else " O valor foi estornado."), charged=charged)
    raise ProviderUnavailable()


def apply_status(consulta: Consulta, payload: dict) -> Consulta:
    """Resultado do GET /v1/consultas/{id}/status (fluxo assíncrono)."""
    data = (payload or {}).get("data") or {}
    status = data.get("status")
    if status in {"PENDENTE", "PROCESSANDO"} or status is None:
        return consulta
    if status == "SUCESSO":
        return _finish(consulta, data)
    charged = bool(data.get("cobrado"))
    return _fail(
        consulta,
        data.get("motivoCobranca") or data.get("mensagem") or "Não foi possível concluir.",
        charged=charged,
        cost=data.get("valorCobradoCentavos"),
    )


def _finish(consulta: Consulta, data: dict) -> Consulta:
    resultado = data.get("resultado") or {}
    cost = int(data.get("valorCobradoCentavos") or 0)
    found = resultado.get("encontrado", True)
    charged = cost > 0 or data.get("cobrado") is True or found
    consulta.provider_consulta_id = data.get("consultaId", consulta.provider_consulta_id)
    consulta.provider_cost_cents = cost
    consulta.set_result(resultado)
    consulta.status = Consulta.Status.SUCCESS if found else Consulta.Status.NOT_FOUND
    consulta.message = (
        "" if found else (scrub_provider(resultado.get("mensagem") or data.get("mensagem")) or "Nada consta para o dado pesquisado.")
    )
    consulta.completed_at = timezone.now()
    _settle(consulta, charged)
    consulta.save()
    return consulta


def _fail(consulta: Consulta, message: str, *, charged: bool, cost=None) -> Consulta:
    consulta.status = Consulta.Status.FAILED
    consulta.message = message[:300]
    consulta.provider_cost_cents = int(cost or 0)
    consulta.completed_at = timezone.now()
    _settle(consulta, charged)
    consulta.save()
    return consulta


def _settle(consulta: Consulta, charged: bool) -> None:
    if consulta.reservation is None:
        return
    if charged:
        res = wallet.capture(consulta.reservation)
        consulta.charged_cents = res.captured_cents
    else:
        wallet.release(consulta.reservation, "consulta não cobrada")
        consulta.charged_cents = 0


def refresh(consulta: Consulta) -> Consulta:
    if consulta.status not in (Consulta.Status.PENDING, Consulta.Status.PROCESSING) or not consulta.provider_consulta_id:
        return consulta
    resp = BusCarsClient(consulta.organization).status(consulta.provider_consulta_id)
    if resp.ok:
        apply_status(consulta, resp.data)
    return consulta
