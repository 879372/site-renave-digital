"""Operações RENAVE via integradora (ver docs/integracoes.md). Cada cliente opera com o próprio certificado (cpf_cnpj)."""

import base64
import logging
from datetime import date

from django.db import transaction
from django.utils import timezone

from core.exceptions import BusinessError, InsufficientBalance, ProviderUnavailable
from core.masking import scrub_provider
from integrations.carven import CarvenClient
from integrations.http import ProviderError, ProviderResponse
from vault.models import Certificate
from vault.service import active_certificate, open_certificate
from wallet import service as wallet
from wallet.models import ServicePrice

from .models import RenaveOperation, StockVehicle

logger = logging.getLogger(__name__)

K = RenaveOperation.Kind
PRICED = {
    K.ENTRADA_COMPRA: ServicePrice.Code.RENAVE_ENTRADA,
    K.ENTRADA_PROPRIO: ServicePrice.Code.RENAVE_ENTRADA,
    K.SAIDA_VENDA: ServicePrice.Code.RENAVE_SAIDA,
    K.TRANSF_FILIAIS: ServicePrice.Code.RENAVE_SAIDA,
    K.TRANSF_ESTAB: ServicePrice.Code.RENAVE_SAIDA,
    K.CANCELAR_ENTRADA: ServicePrice.Code.RENAVE_CANCELAR_ENTRADA,
    K.CANCELAR_SAIDA: ServicePrice.Code.RENAVE_CANCELAR_SAIDA,
}


def owner_document(organization, client=None) -> str:
    return client.document if client else organization.cnpj


def sync_certificate(cert: Certificate) -> None:
    pfx, password = open_certificate(cert)
    resp = CarvenClient(cert.organization).renave_salvar_certificado(cert.holder_document, cert.holder_name, pfx, password)
    if resp.ok:
        cert.carven_synced_at = timezone.now()
        cert.carven_sync_error = ""
    else:
        cert.carven_sync_error = CarvenClient().error_message(resp.data)[:300]
    cert.save(update_fields=["carven_synced_at", "carven_sync_error", "updated_at"])
    if not resp.ok:
        raise BusinessError(f"O RENAVE recusou o certificado: {cert.carven_sync_error}", code="certificate_rejected")


def _ensure_ready(organization, client) -> str:
    cert = active_certificate(organization, client)
    if cert.carven_synced_at is None:
        sync_certificate(cert)
    return owner_document(organization, client)


def _raise_for(resp: ProviderResponse, client: CarvenClient):
    if resp.status_code in (502, 503, 504):
        raise ProviderUnavailable("O RENAVE não respondeu. Tente novamente em alguns minutos.")
    raise BusinessError(client.error_message(resp.data), code="renave_rejected", extra={"provider_status": resp.status_code})


def _run(*, organization, user, kind, call, vehicle=None, description=""):
    """Executa uma operação: reserva (se tarifada) → chama → captura/estorna → registra."""
    price = wallet.price_for(PRICED[kind], organization) if kind in PRICED else 0
    with transaction.atomic():
        op = RenaveOperation.objects.create(organization=organization, vehicle=vehicle, user=user, kind=kind, price_cents=price)
        if price:
            op.reservation = wallet.reserve(
                organization, price, description or op.get_kind_display(), ref_type="renave", ref_id=op.public_id, user=user
            )
            op.save(update_fields=["reservation"])

    client = CarvenClient(organization)
    try:
        resp = call(client)
    except ProviderError as exc:
        if op.reservation:
            wallet.release(op.reservation, "falha de comunicação")
        op.message = "Falha de comunicação com o RENAVE."
        op.save(update_fields=["message", "updated_at"])
        raise ProviderUnavailable() from exc

    op.success = resp.ok
    data = resp.data if isinstance(resp.data, dict) else {}
    if resp.ok:
        op.message = scrub_provider(data.get("mensagem", ""))[:500]
    else:
        op.message = scrub_provider(data.get("mensagem") or data.get("msg") or client.error_message(data))[:500]
    op.response = {k: v for k, v in data.items() if k not in ("pdf",)} if data else None
    op.save(update_fields=["success", "message", "response", "updated_at"])
    if op.reservation:
        if resp.ok:
            wallet.capture(op.reservation)
        else:
            wallet.release(op.reservation, "operação recusada")
    if not resp.ok:
        _raise_for(resp, client)
    return op, resp


def aptidao(*, organization, client_company, user, placa, renavam, crv, tipo_crv) -> dict:
    doc = _ensure_ready(organization, client_company)
    body = {"cpf_cnpj": doc, "placa": placa, "renavam": renavam, "crv": crv, "tipo_crv": tipo_crv}
    _, resp = _run(organization=organization, user=user, kind=K.APTIDAO, call=lambda c: c.renave_aptidao(body))
    return resp.data.get("veiculo", {}) if isinstance(resp.data, dict) else {}


def entrada(*, organization, client_company, user, data: dict) -> StockVehicle:
    doc = _ensure_ready(organization, client_company)
    proprio = data["tipo_operacao"] == "entrada_veiculo_proprio"
    body = {
        "cpf_cnpj": doc,
        "placa": data["placa"],
        "renavam": data["renavam"],
        "crv": data["crv"],
        "codigoSegurancaCrv": data["codigo_seguranca_crv"],
        "tipo_crv": data["tipo_crv"],
        "quilometragemHodometro": str(data["km"]),
        "dataHoraMedicaoHodometro": data["data_hora_km"].strftime("%Y-%m-%dT%H:%M"),
        "tipo_operacao": data["tipo_operacao"],
        "dataCompra": data["data_compra"].isoformat(),
    }
    if not proprio:
        pf = data["vendedor_tipo"] == "fisica"
        body.update(
            tipo_proprietario=data["vendedor_tipo"],
            cpf=data["vendedor_documento"] if pf else None,
            cnpj=None if pf else data["vendedor_documento"],
            emailEstabelecimento=organization.email or user.email,
            valorCompra=str(data["valor_compra_cents"]),
        )
    vehicle = StockVehicle.objects.create(
        organization=organization,
        client=client_company,
        owner_document=doc,
        placa=data["placa"],
        renavam=data["renavam"],
        crv=data["crv"],
        tipo_crv=data["tipo_crv"],
        entry_date=data["data_compra"],
        entry_value_cents=data.get("valor_compra_cents"),
        entry_km=data["km"],
    )
    kind = K.ENTRADA_PROPRIO if proprio else K.ENTRADA_COMPRA
    try:
        _run(
            organization=organization,
            user=user,
            kind=kind,
            vehicle=vehicle,
            call=lambda c: c.renave_entrada(body),
            description=f"Entrada RENAVE {vehicle.placa}",
        )
    except InsufficientBalance:
        vehicle.delete()
        raise
    except Exception:
        vehicle.state = StockVehicle.State.NEGADO
        vehicle.save(update_fields=["state", "updated_at"])
        raise
    from .tasks import resolve_stock_id

    resolve_stock_id.apply_async(args=[vehicle.pk], countdown=10)
    return vehicle


def _require_id(vehicle: StockVehicle) -> int:
    if not vehicle.id_estoque:
        raise BusinessError("O RENAVE ainda não confirmou este veículo. Atualize o estoque em instantes.", code="stock_pending")
    return vehicle.id_estoque


def saida(*, vehicle: StockVehicle, user, data: dict) -> StockVehicle:
    id_estoque = _require_id(vehicle)
    doc = _ensure_ready(vehicle.organization, vehicle.client)
    tipo = str(data["tipo_transferencia"])
    body = {
        "cpf_cnpj": doc,
        "tipo_transferencia": tipo,
        "data_venda": data["data_venda"].isoformat(),
        "cod_seguranca_crv": data["cod_seguranca_crv"],
    }
    if tipo == "1":
        body.update(
            nome=data["comprador_nome"][:40],
            cpf=data["comprador_documento"],
            valor_venda=str(data["valor_venda_cents"]),
            municipio=data["municipio"],
            email=data.get("email") or None,
            cep=data.get("cep") or None,
            longadouro=data.get("logradouro") or None,
            numero=data.get("numero") or None,
            complemento=data.get("complemento") or None,
            bairro=data.get("bairro") or None,
        )
    else:
        body.update(
            razao_social=data["comprador_nome"][:100],
            cnpj=data["comprador_documento"],
            quilometragemHodometro=str(data.get("km") or ""),
            dataHoraMedicaoHodometro=data["data_hora_km"].strftime("%Y-%m-%dT%H:%M") if data.get("data_hora_km") else None,
        )
    kind = {"1": K.SAIDA_VENDA, "2": K.TRANSF_FILIAIS, "3": K.TRANSF_ESTAB}[tipo]
    _run(
        organization=vehicle.organization,
        user=user,
        kind=kind,
        vehicle=vehicle,
        call=lambda c: c.renave_saida(id_estoque, body),
        description=f"Saída RENAVE {vehicle.placa}",
    )
    vehicle.state = StockVehicle.State.FINALIZADO if tipo == "1" else StockVehicle.State.TRANSFERIDO
    vehicle.exit_date = data["data_venda"]
    vehicle.exit_value_cents = data.get("valor_venda_cents")
    vehicle.save(update_fields=["state", "exit_date", "exit_value_cents", "updated_at"])
    return vehicle


def cancelar_entrada(*, vehicle: StockVehicle, user) -> StockVehicle:
    id_estoque = _require_id(vehicle)
    doc = _ensure_ready(vehicle.organization, vehicle.client)
    _run(
        organization=vehicle.organization,
        user=user,
        kind=K.CANCELAR_ENTRADA,
        vehicle=vehicle,
        call=lambda c: c.renave_cancelar_entrada(id_estoque, doc),
    )
    vehicle.state = StockVehicle.State.CANCELADO
    vehicle.save(update_fields=["state", "updated_at"])
    return vehicle


def cancelar_saida(*, vehicle: StockVehicle, user) -> StockVehicle:
    id_estoque = _require_id(vehicle)
    doc = _ensure_ready(vehicle.organization, vehicle.client)
    _run(
        organization=vehicle.organization,
        user=user,
        kind=K.CANCELAR_SAIDA,
        vehicle=vehicle,
        call=lambda c: c.renave_cancelar_saida(id_estoque, doc),
    )
    vehicle.state = StockVehicle.State.CONFIRMADO
    vehicle.exit_date = None
    vehicle.exit_value_cents = None
    vehicle.save(update_fields=["state", "exit_date", "exit_value_cents", "updated_at"])
    return vehicle


def enviar_nota(*, vehicle: StockVehicle, user, chave: str, evento: str) -> None:
    id_estoque = _require_id(vehicle)
    doc = _ensure_ready(vehicle.organization, vehicle.client)
    body = {"cpf_cnpj": doc, "chaveNotaFiscal": chave, "evento": evento}
    _run(
        organization=vehicle.organization,
        user=user,
        kind=K.NOTA_FISCAL,
        vehicle=vehicle,
        call=lambda c: c.renave_enviar_nota(id_estoque, body),
    )


def enviar_atpv_assinada(*, vehicle: StockVehicle, user, tipo_assinatura: str, arquivo: bytes) -> None:
    id_estoque = _require_id(vehicle)
    doc = _ensure_ready(vehicle.organization, vehicle.client)
    body = {"cpf_cnpj": doc, "idEstoque": id_estoque, "tipoAssinatura": tipo_assinatura, "atpv": base64.b64encode(arquivo).decode()}
    _run(
        organization=vehicle.organization,
        user=user,
        kind=K.ATPV_ASSINADA,
        vehicle=vehicle,
        call=lambda c: c.renave_enviar_atpv_assinada(body),
    )


def documento(*, vehicle: StockVehicle, kind: str) -> tuple[bytes, str, str]:
    """Retorna (conteúdo, content-type, nome do arquivo)."""
    id_estoque = _require_id(vehicle)
    doc = owner_document(vehicle.organization, vehicle.client)
    client = CarvenClient(vehicle.organization)
    try:
        resp = client.renave_documento(kind, id_estoque, doc)
    except ProviderError as exc:
        raise ProviderUnavailable() from exc
    if not resp.ok:
        _raise_for(resp, client)
    if kind == "atpv":
        return resp.data if isinstance(resp.data, bytes) else b"", "application/zip", f"atpv_{vehicle.placa}.zip"
    pdf_b64 = resp.data.get("pdf", "") if isinstance(resp.data, dict) else ""
    return base64.b64decode(pdf_b64), "application/pdf", f"{kind}_{vehicle.placa}.pdf"


# --- sincronização ------------------------------------------------------------------


def _apply_remote(vehicle: StockVehicle, item: dict) -> None:
    vehicle.id_estoque = item.get("id") or vehicle.id_estoque
    vehicle.protocolo = str(item.get("protocoloPedido") or vehicle.protocolo)
    vehicle.situacao = str(item.get("situacaoPedido") or "")[:80]
    state = {
        "Entrada solicitada": "SOLICITADO",
        "Em estoque": "CONFIRMADO",
        "Entrada negada": "NEGADO",
        "Finalizado": "FINALIZADO",
        "Transferido": "TRANSFERIDO",
    }.get(vehicle.situacao)
    if state:
        vehicle.state = state
    vehicle.raw = item
    vehicle.last_synced_at = timezone.now()


def sync_stock(organization, client_company=None, *, refresh_remote=True) -> dict:
    doc = owner_document(organization, client_company)
    client = CarvenClient(organization)
    message = ""
    if refresh_remote:
        resp = client.renave_atualizar_estoque(doc)
        if resp.status_code == 429:
            message = scrub_provider(resp.data.get("mensagem", "")) if isinstance(resp.data, dict) else ""
        elif not resp.ok:
            _raise_for(resp, client)
        else:
            message = scrub_provider(resp.data.get("mensagem", ""))

    page, updated = 1, 0
    while page <= 50:
        resp = client.renave_listar_estoque(cpf_cnpj=doc, porPagina=100, page=page)
        if not resp.ok:
            _raise_for(resp, client)
        block = resp.data.get("estoque", {})
        for item in block.get("data", []):
            placa = str(item.get("placa", "")).replace("-", "").upper()
            vehicle = (
                StockVehicle.objects.filter(organization=organization, id_estoque=item.get("id")).first()
                or StockVehicle.objects.filter(organization=organization, owner_document=doc, placa=placa, id_estoque__isnull=True).first()
                or StockVehicle(
                    organization=organization, client=client_company, owner_document=doc, placa=placa, renavam=str(item.get("renavam", ""))
                )
            )
            _apply_remote(vehicle, item)
            vehicle.save()
            updated += 1
        if not block.get("next_page_url"):
            break
        page += 1
    return {"updated": updated, "message": message}


def resolve_id(vehicle: StockVehicle) -> bool:
    if vehicle.id_estoque:
        return True
    resp = CarvenClient(vehicle.organization).renave_listar_estoque(cpf_cnpj=vehicle.owner_document, placa=vehicle.placa, porPagina=10)
    if not resp.ok:
        return False
    for item in resp.data.get("estoque", {}).get("data", []):
        if str(item.get("placa", "")).replace("-", "").upper() == vehicle.placa:
            _apply_remote(vehicle, item)
            vehicle.save()
            return True
    return False


def today() -> date:
    return timezone.localdate()
