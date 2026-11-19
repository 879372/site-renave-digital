"""Emissão de NF-e de veículos via Geranet.

A emissão roda em task Celery (a SEFAZ pode levar dezenas de segundos). O número é
reservado na criação e reaproveitado em reenvios da mesma nota.
"""

import logging
import random

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from core.exceptions import BusinessError, ProviderUnavailable
from core.masking import scrub_provider
from integrations.geranet import GeranetClient
from integrations.http import ProviderError
from vault.service import active_certificate, open_certificate
from wallet import service as wallet
from wallet.models import ServicePrice

from .models import FiscalSettings, NotaFiscal

logger = logging.getLogger(__name__)

REQUIRED_ORG_FIELDS = {
    "state_registration": "inscrição estadual",
    "tax_regime": "regime tributário",
    "street": "logradouro",
    "number": "número",
    "district": "bairro",
    "city": "cidade",
    "city_ibge": "código IBGE da cidade",
    "uf": "UF",
    "zip_code": "CEP",
}


def get_settings(organization) -> FiscalSettings:
    obj, _ = FiscalSettings.objects.get_or_create(organization=organization)
    return obj


def _check_emitter(org):
    missing = [label for field, label in REQUIRED_ORG_FIELDS.items() if not getattr(org, field)]
    if missing:
        raise BusinessError("Complete os dados fiscais da empresa antes de emitir: " + ", ".join(missing) + ".", code="fiscal_incomplete")
    if org.tax_regime not in ("1", "4"):
        raise BusinessError("Emissão para regime normal ainda não habilitada. Fale com o suporte.", code="fiscal_regime_unsupported")


def _money(cents: int) -> str:
    return f"{cents / 100:.2f}"


def build_nfe(org, cfg: FiscalSettings, nota: NotaFiscal, d: dict) -> dict:
    interestadual = d["uf"] != org.uf
    entrada = nota.tipo == NotaFiscal.Tipo.ENTRADA
    if entrada:
        cfop = cfg.cfop_compra_interestadual if interestadual else cfg.cfop_compra_estadual
        natureza = cfg.natureza_compra
    else:
        cfop = cfg.cfop_venda_interestadual if interestadual else cfg.cfop_venda_estadual
        natureza = cfg.natureza_venda
    now = timezone.localtime().strftime("%Y-%m-%d %H:%M:%S")
    doc = d["documento"]
    veiculo_info = (
        f"Placa: {d['placa']} | Chassi: {d['chassi']} | RENAVAM: {d['renavam']} | Marca/Modelo: {d['marca_modelo']} | "
        f"Ano/Modelo: {d['ano_fabricacao']}/{d['ano_modelo']} | Cor: {d['cor']} | KM: {d.get('km', '')}"
    )
    valor = _money(d["valor_cents"])
    return {
        "contingencia": "nao",
        "empresa": {
            "cnpj": org.cnpj,
            "inscricaoEstadual": org.state_registration,
            "razaoSocial": org.legal_name,
            "nomeFantasia": (org.trade_name or "")[:60],
            "telefone": org.phone,
            "email": org.email,
            "logradouro": org.street,
            "numero": org.number,
            "complemento": org.complement,
            "bairro": org.district,
            "municipio": f"{org.city.upper()} - {org.uf}",
            "codigoMunicipio": org.city_ibge,
            "uf": org.uf,
            "cep": org.zip_code,
            "codigoRegimeTributario": org.tax_regime,
            "tipoAtividade": "1",
            "serie": str(nota.serie),
            "informacaoComplementar": "",
        },
        "cliente": {
            "cnpj": doc if len(doc) == 14 else "",
            "cpf": doc if len(doc) == 11 else "",
            "inscricaoEstadual": d.get("inscricao_estadual", ""),
            "razaoSocial": d["nome"],
            "nomeFantasia": "",
            "consumidorFinal": "1" if len(doc) == 11 else "0",
            "indicadorIEdestinatario": "1" if d.get("inscricao_estadual") else "9",
            "telefone": d.get("telefone", ""),
            "email": d.get("email", ""),
            "logradouro": d["logradouro"],
            "numero": d["numero"],
            "complemento": d.get("complemento", ""),
            "bairro": d["bairro"],
            "municipio": f"{d['cidade'].upper()} - {d['uf']}",
            "codigoMunicipio": d["cidade_ibge"],
            "codigoPais": "1058",
            "nomePais": "Brasil",
            "uf": d["uf"],
            "cep": d["cep"],
        },
        "indicadorPresenca": "1",
        "indicativoIntermediador": "0",
        "intermediador": None,
        "numeroNotaEmitir": str(nota.numero),
        "codigoNumerico": f"{random.SystemRandom().randint(10_000_000, 99_999_999)}",
        "dataSaida": now,
        "dataEmissao": now,
        "modelo": "55",
        "ambiente": nota.ambiente,
        "tipo": nota.tipo,
        "frete": "9",
        "finalidade": "1",
        "informacaoAdicionalFisco": "",
        "informacaoComplementar": " ".join(filter(None, [cfg.informacao_complementar, d.get("observacoes", "")]))[:2000],
        "notaFiscalReferencia": "",
        "naturezaOperacao": natureza,
        "numeroVenda": "",
        "pagamento": {
            "troco": 0.0,
            "detalhamento": [{"tipo": d.get("forma_pagamento", "99"), "valor": float(valor), "indicadorPagamento": "0"}],
        },
        "itens": [
            {
                "desconto": "0.00",
                "frete": "0.00",
                "seguro": "0.00",
                "outro": "0.00",
                "quantidade": "1.00000000",
                "valorUnitario": f"{d['valor_cents'] / 100:.8f}",
                "valorTotal": valor,
                "informacaoAdicional": veiculo_info[:500],
                "ncmProduto": d.get("ncm") or cfg.ncm_padrao,
                "cest": "",
                "tipoItem": "00",
                "eanProduto": "SEM GTIN",
                "codigoProduto": d["placa"],
                "nomeProduto": f"VEICULO {d['marca_modelo']} {d['ano_fabricacao']}/{d['ano_modelo']}".upper()[:120],
                "cfop": cfop,
                "unidadeMedidaProduto": "UN",
                "origemProduto": "0",
                "icmsCsosn": cfg.icms_csosn,
                "pisCst": cfg.pis_cst,
                "pisAliquota": "0",
                "cofinsCst": cfg.cofins_cst,
                "cofinsAliquota": "0",
            }
        ],
    }


def criar(*, organization, user, data: dict, vehicle=None) -> NotaFiscal:
    _check_emitter(organization)
    active_certificate(organization)  # falha cedo se não houver certificado
    ambiente = settings.GERANET["AMBIENTE"]
    price = wallet.price_for(ServicePrice.Code.NFE) if ambiente == "1" else 0
    with transaction.atomic():
        cfg = FiscalSettings.objects.select_for_update().get(pk=get_settings(organization).pk)
        nota = NotaFiscal(
            organization=organization,
            user=user,
            vehicle=vehicle,
            tipo=data["tipo"],
            ambiente=ambiente,
            serie=cfg.serie,
            numero=cfg.next_number,
            destinatario_nome=data["nome"][:150],
            destinatario_documento=data["documento"],
            total_cents=data["valor_cents"],
            price_cents=price,
        )
        nota.set_payload(build_nfe(organization, cfg, nota, data))
        cfg.next_number += 1
        cfg.save(update_fields=["next_number", "updated_at"])
        nota.save()
        if price:
            nota.reservation = wallet.reserve(
                organization, price, f"NF-e {nota.serie}/{nota.numero}", ref_type="nfe", ref_id=nota.public_id, user=user
            )
            nota.save(update_fields=["reservation"])
    from .tasks import emitir_nfe

    transaction.on_commit(lambda: emitir_nfe.delay(nota.pk))
    return nota


def emitir(nota: NotaFiscal) -> NotaFiscal:
    if nota.status in (NotaFiscal.Status.AUTHORIZED, NotaFiscal.Status.CANCELED):
        return nota
    nota.status = NotaFiscal.Status.PROCESSING
    nota.save(update_fields=["status", "updated_at"])
    org = nota.organization
    pfx, senha = open_certificate(active_certificate(org))
    client = GeranetClient(org)
    try:
        resp = client.emitir(pfx=pfx, senha=senha, uf=org.uf, nfe=nota.get_payload())
    except ProviderError:
        nota.status = NotaFiscal.Status.ERROR
        nota.message = "Falha de comunicação com a SEFAZ. Tente reenviar."
        nota.save(update_fields=["status", "message", "updated_at"])
        raise

    data = resp.data if isinstance(resp.data, dict) else {}
    nota.cstat = str(data.get("cstat") or "")[:10]
    nota.message = scrub_provider(data.get("mensagem"))[:500]
    if resp.ok and data.get("situacao") == "sucesso":
        nota.status = NotaFiscal.Status.AUTHORIZED
        nota.chave = data.get("chave", "")
        nota.protocolo = data.get("protocolo", "")
        nota.xml = bytes.fromhex(data["xml"]) if data.get("xml") else None
        nota.pdf = bytes.fromhex(data["pdf"]) if data.get("pdf") else None
        nota.authorized_at = timezone.now()
        if nota.reservation:
            wallet.capture(nota.reservation)
    else:
        nota.status = NotaFiscal.Status.REJECTED
        if nota.reservation:
            wallet.release(nota.reservation, "nota rejeitada")
            nota.reservation = None
    nota.save()

    if nota.status == NotaFiscal.Status.AUTHORIZED and nota.vehicle_id and get_settings(org).enviar_chave_renave:
        from renave import service as renave

        try:
            renave.enviar_nota(vehicle=nota.vehicle, user=nota.user, chave=nota.chave, evento="COMPRA" if nota.tipo == "0" else "VENDA")
        except Exception:
            logger.warning("Não foi possível enviar a chave ao RENAVE", exc_info=True)
    return nota


def reenviar(nota: NotaFiscal, user) -> NotaFiscal:
    if nota.status not in (NotaFiscal.Status.REJECTED, NotaFiscal.Status.ERROR):
        raise BusinessError("Somente notas rejeitadas ou com erro podem ser reenviadas.")
    if nota.price_cents and nota.reservation is None:
        nota.reservation = wallet.reserve(
            nota.organization,
            nota.price_cents,
            f"NF-e {nota.serie}/{nota.numero}",
            ref_type="nfe",
            ref_id=f"{nota.public_id}:{timezone.now().timestamp()}",
            user=user,
        )
    nota.status = NotaFiscal.Status.QUEUED
    nota.save(update_fields=["status", "reservation", "updated_at"])
    from .tasks import emitir_nfe

    emitir_nfe.delay(nota.pk)
    return nota


def cancelar(nota: NotaFiscal, justificativa: str) -> NotaFiscal:
    if nota.status != NotaFiscal.Status.AUTHORIZED:
        raise BusinessError("Só é possível cancelar notas autorizadas.")
    if len(justificativa.strip()) < 15:
        raise BusinessError("A justificativa precisa ter pelo menos 15 caracteres.")
    org = nota.organization
    pfx, senha = open_certificate(active_certificate(org))
    client = GeranetClient(org)
    try:
        resp = client.cancelar(
            pfx=pfx, senha=senha, uf=org.uf, chave=nota.chave, protocolo=nota.protocolo, justificativa=justificativa.strip()
        )
    except ProviderError as exc:
        raise ProviderUnavailable() from exc
    data = resp.data if isinstance(resp.data, dict) else {}
    if not (resp.ok and data.get("situacao") == "sucesso"):
        raise BusinessError(scrub_provider(data.get("mensagem")) or "Cancelamento recusado pela SEFAZ.", code="sefaz_rejected")
    nota.status = NotaFiscal.Status.CANCELED
    nota.canceled_at = timezone.now()
    nota.message = scrub_provider(data.get("mensagem", ""))[:500]
    if data.get("xml"):
        nota.xml = bytes.fromhex(data["xml"])
    nota.save()
    return nota


def carta_correcao(nota: NotaFiscal, texto: str) -> NotaFiscal:
    if nota.status != NotaFiscal.Status.AUTHORIZED:
        raise BusinessError("Carta de correção só para notas autorizadas.")
    if not 15 <= len(texto.strip()) <= 1000:
        raise BusinessError("O texto da correção deve ter entre 15 e 1000 caracteres.")
    org = nota.organization
    pfx, senha = open_certificate(active_certificate(org))
    client = GeranetClient(org)
    try:
        resp = client.carta_correcao(
            pfx=pfx, senha=senha, uf=org.uf, chave=nota.chave, correcao=texto.strip(), sequencia=nota.cce_count + 1
        )
    except ProviderError as exc:
        raise ProviderUnavailable() from exc
    data = resp.data if isinstance(resp.data, dict) else {}
    if not (resp.ok and data.get("situacao") == "sucesso"):
        raise BusinessError(scrub_provider(data.get("mensagem")) or "Carta de correção recusada.", code="sefaz_rejected")
    nota.cce_count += 1
    nota.save(update_fields=["cce_count", "updated_at"])
    return nota
