from django.conf import settings
from django.db import transaction
from django.utils import timezone

from core.exceptions import BusinessError, ProviderUnavailable
from core.masking import scrub_provider
from integrations.carven import CarvenClient
from integrations.http import ProviderError
from wallet import service as wallet
from wallet.models import ServicePrice

from .models import ComunicacaoVenda


def _call(fn, client):
    try:
        resp = fn(client)
    except ProviderError as exc:
        raise ProviderUnavailable() from exc
    return resp


def build_body(d: dict, notify_url: str | None) -> dict:
    def pessoa(prefix):
        tipo = d[f"{prefix}_tipo"]
        out = {"tipo_pessoa": tipo, "nome": d[f"{prefix}_nome"]}
        out["cpf" if tipo == "F" else "cnpj"] = d[f"{prefix}_documento"]
        return out

    comprador = pessoa("comprador")
    comprador["endereco"] = {
        "cep": d["cep"],
        "logradouro": d["logradouro"],
        "numero": d["numero"],
        "bairro": d["bairro"],
        "complemento": d.get("complemento", ""),
        "cidade": int(d["cidade_comprador"]),
    }
    body = {
        "vendedor": pessoa("vendedor"),
        "comprador": comprador,
        "venda": {
            "cidade": int(d["cidade_venda"]),
            "data": d["data_venda"].strftime("%d/%m/%Y"),
            "valor": round(d["valor_cents"] / 100, 2),
            "comprador_solicitante": "S" if d.get("comprador_solicitante") else "N",
        },
        "veiculo": {
            "placa": d["placa"],
            "renavam": d["renavam"],
            "ano_fabricacao": d["ano_fabricacao"],
            "ano_modelo": d["ano_modelo"],
            "crv": {
                "numero": d["crv_numero"],
                "codigo_seguranca": d["crv_codigo_seguranca"],
                "numero_via": d["crv_via"],
                "data_emissao": d["crv_data_emissao"].strftime("%d/%m/%Y"),
                "uf_emissao": d["crv_uf"],
            },
        },
    }
    if d.get("arquivos"):
        body["arquivos"] = d["arquivos"]
    if notify_url:
        body["url_notificacao"] = notify_url
    return body


def criar(*, organization, user, data: dict, vehicle=None) -> ComunicacaoVenda:
    cv = ComunicacaoVenda(
        organization=organization,
        user=user,
        vehicle=vehicle,
        placa=data["placa"],
        renavam=data["renavam"],
        comprador_nome=data["comprador_nome"][:150],
        valor_cents=data["valor_cents"],
        data_venda=data["data_venda"],
    )
    notify = f"{settings.PUBLIC_API_URL}/api/hooks/comunicacao/{cv.notify_token}" if settings.PUBLIC_API_URL.startswith("https") else None
    body = build_body(data, notify)
    cv.set_payload({k: v for k, v in body.items() if k != "arquivos"})
    client = CarvenClient(organization)
    resp = _call(lambda c: c.comunicacao_inserir(body), client)
    if not resp.ok:
        raise BusinessError(client.error_message(resp.data), code="operation_rejected")
    cv.protocolo = str(resp.data.get("protocolo", ""))
    cv.situacao = ComunicacaoVenda.Situacao.BLOQUEADA if resp.data.get("status") == "alerta" else ComunicacaoVenda.Situacao.CADASTRADA
    cv.message = scrub_provider(resp.data.get("msg", ""))[:500]
    cv.save()
    return cv


def transmitir(cv: ComunicacaoVenda, user) -> ComunicacaoVenda:
    if cv.situacao not in (ComunicacaoVenda.Situacao.CADASTRADA, ComunicacaoVenda.Situacao.ERRO):
        raise BusinessError("Esta comunicação não pode ser transmitida na situação atual.")
    price = wallet.price_for(ServicePrice.Code.COMUNICACAO, cv.organization)
    with transaction.atomic():
        if price and cv.reservation is None:
            cv.price_cents = price
            cv.reservation = wallet.reserve(
                cv.organization, price, f"Comunicação de venda {cv.placa}", ref_type="comunicacao", ref_id=cv.public_id, user=user
            )
            cv.save(update_fields=["price_cents", "reservation"])
    client = CarvenClient(cv.organization)
    try:
        resp = client.comunicacao_transmitir(cv.protocolo)
    except ProviderError as exc:
        if cv.reservation:
            wallet.release(cv.reservation, "falha de comunicação")
            cv.reservation = None
            cv.save(update_fields=["reservation"])
        raise ProviderUnavailable() from exc
    if not resp.ok:
        if cv.reservation:
            wallet.release(cv.reservation, "transmissão recusada")
            cv.reservation = None
        cv.message = client.error_message(resp.data)[:500]
        cv.save(update_fields=["reservation", "message", "updated_at"])
        raise BusinessError(cv.message, code="operation_rejected")
    if cv.reservation:
        wallet.capture(cv.reservation)
    cv.situacao = ComunicacaoVenda.Situacao.COMUNICADA
    cv.transmitted_at = timezone.now()
    cv.message = scrub_provider(resp.data.get("msg", ""))[:500] if isinstance(resp.data, dict) else ""
    cv.save()
    return cv


def refresh(cv: ComunicacaoVenda) -> ComunicacaoVenda:
    if not cv.protocolo:
        return cv
    resp = _call(lambda c: c.comunicacao_detalhes(cv.protocolo), CarvenClient(cv.organization))
    if resp.ok and isinstance(resp.data, dict):
        situacao = resp.data.get("situacao") or {}
        code = situacao.get("codigo") if isinstance(situacao, dict) else None
        erro = resp.data.get("ultimo_erro") or {}
        if code:
            cv.situacao = int(code)
        if isinstance(erro, dict) and erro.get("descricacao"):
            cv.message = scrub_provider(erro["descricacao"])[:500]
        cv.save(update_fields=["situacao", "message", "updated_at"])
    return cv


def motivos_cancelamento(cv: ComunicacaoVenda) -> list[dict]:
    client = CarvenClient(cv.organization)
    resp = _call(lambda c: c.comunicacao_motivos_cancelamento(cv.protocolo), client)
    if not resp.ok:
        raise BusinessError(client.error_message(resp.data))
    return resp.data.get("motivos", []) if isinstance(resp.data, dict) else []


def cancelar(cv: ComunicacaoVenda, id_motivo: str) -> ComunicacaoVenda:
    client = CarvenClient(cv.organization)
    resp = _call(lambda c: c.comunicacao_cancelar(cv.protocolo, {"id_motivo_cancelamento": str(id_motivo)}), client)
    if not resp.ok:
        raise BusinessError(client.error_message(resp.data), code="operation_rejected")
    cv.situacao = ComunicacaoVenda.Situacao.CANCELADA
    cv.save(update_fields=["situacao", "updated_at"])
    return cv


def comprovante(cv: ComunicacaoVenda) -> bytes:
    client = CarvenClient(cv.organization)
    resp = _call(lambda c: c.comunicacao_comprovante(cv.protocolo), client)
    if not resp.ok:
        raise BusinessError(client.error_message(resp.data))
    return resp.data if isinstance(resp.data, bytes) else b""
