from datetime import timedelta

import httpx
import pytest
import respx
from django.utils import timezone

from fiscal import service as fiscal
from fiscal.models import NotaFiscal
from renave.models import StockVehicle
from vault.models import Certificate
from wallet import service as wallet

CARVEN = "https://homologacao.carven.com.br"


@pytest.fixture
def cert(org):
    from vault.crypto import encrypt_bytes

    c = Certificate(
        organization=org,
        holder_document=org.cnpj,
        holder_name="LOJA",
        subject="CN=LOJA",
        serial="1",
        fingerprint="f",
        not_before=timezone.now() - timedelta(days=1),
        not_after=timezone.now() + timedelta(days=300),
        carven_synced_at=timezone.now(),
        pfx_encrypted=b"",
        password_encrypted=b"",
    )
    c.pfx_encrypted = encrypt_bytes(b"pfx", c.aad)
    c.password_encrypted = encrypt_bytes(b"senha", c.aad)
    c.save()
    return c


ENTRADA = {
    "tipo_operacao": "compra_veiculo",
    "placa": "REH1F23",
    "renavam": "44184914479",
    "crv": "777227011523",
    "codigo_seguranca_crv": "77722711523",
    "tipo_crv": "DIGITAL",
    "km": 54545,
    "data_hora_km": "2026-10-19T11:59:00-03:00",
    "data_compra": "2026-10-21",
    "vendedor_tipo": "fisica",
    "vendedor_documento": "529.982.247-25",
    "valor_compra_cents": 4566600,
}


@respx.mock
def test_entrada_renave_cobra_e_envia_cpf_cnpj(api, funded, cert, monkeypatch):
    monkeypatch.setattr("renave.tasks.resolve_stock_id.apply_async", lambda *a, **k: None)
    respx.post(f"{CARVEN}/api/auth/login").mock(return_value=httpx.Response(200, json={"access_token": "tok", "expires_after": 3600}))
    route = respx.post(f"{CARVEN}/api/renave/usado/estoque/entrada-estoque").mock(
        return_value=httpx.Response(200, json={"status": "sucesso", "mensagem": "Estoque salvo com sucesso!"})
    )
    r = api.post("/api/renave/stock", ENTRADA, format="json")
    assert r.status_code == 201, r.json()
    sent = route.calls[0].request
    assert sent.headers["authorization"] == "Bearer tok"
    import json

    body = json.loads(sent.content)
    assert body["cpf_cnpj"] == funded.cnpj and body["cpf"] == "52998224725" and body["valorCompra"] == "4566600"
    assert wallet.get_wallet(funded).balance_cents == 100_00 - wallet.price_for("renave.entrada")


@respx.mock
def test_entrada_recusada_estorna(api, funded, cert, monkeypatch):
    respx.post(f"{CARVEN}/api/auth/login").mock(return_value=httpx.Response(200, json={"access_token": "tok"}))
    respx.post(f"{CARVEN}/api/renave/usado/estoque/entrada-estoque").mock(
        return_value=httpx.Response(422, json={"message": "x", "errors": {"crv": ["CRV inválido."]}})
    )
    r = api.post("/api/renave/stock", ENTRADA, format="json")
    assert r.status_code == 422 and "CRV inválido" in r.json()["error"]["message"]
    assert wallet.get_wallet(funded).balance_cents == 100_00
    assert StockVehicle.objects.get().state == "NEGADO"


def test_entrada_sem_certificado(api, funded):
    r = api.post("/api/renave/stock", ENTRADA, format="json")
    assert r.status_code == 422 and r.json()["error"]["code"] == "certificate_missing"


def test_payload_nfe_veiculo(org):
    org.state_registration = "123"
    org.tax_regime = "1"
    org.street, org.number, org.district, org.city_ibge, org.zip_code = "Rua A", "10", "Centro", "2408102", "59000000"
    cfg = fiscal.get_settings(org)
    nota = NotaFiscal(
        organization=org, tipo="1", serie=1, numero=7, ambiente="2", destinatario_nome="X", destinatario_documento="1", total_cents=1
    )
    data = {
        "documento": "52998224725",
        "nome": "Comprador",
        "cep": "59000000",
        "logradouro": "R",
        "numero": "1",
        "bairro": "B",
        "cidade": "Recife",
        "cidade_ibge": "2611606",
        "uf": "PE",
        "placa": "REH1F23",
        "chassi": "9BWZZZ377VT004251",
        "renavam": "44184914479",
        "marca_modelo": "VW/GOL",
        "ano_fabricacao": 2020,
        "ano_modelo": 2021,
        "cor": "PRATA",
        "valor_cents": 4500000,
    }
    p = fiscal.build_nfe(org, cfg, nota, data)
    item = p["itens"][0]
    assert item["cfop"] == cfg.cfop_venda_interestadual  # RN -> PE
    assert item["valorTotal"] == "45000.00" and "9BWZZZ377VT004251" in item["informacaoAdicional"]
    assert p["cliente"]["cpf"] == "52998224725" and p["cliente"]["consumidorFinal"] == "1"
    assert p["numeroNotaEmitir"] == "7"
