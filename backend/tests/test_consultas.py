import hashlib
import hmac
import json
from datetime import UTC, datetime

import httpx
import pytest
import respx

from consultas.models import Consulta, Product
from integrations.buscars import verify_webhook
from wallet import service as wallet

URL = "https://api.buscars.com.br/v1/consulta"


@pytest.fixture
def product(db):
    return Product.objects.create(
        code="completa", sku="veicular-completa-sf", name="Completa", input_type="PLACA", price_cents=40_00, is_active=True
    )


def balance(org):
    return wallet.get_wallet(org).balance_cents


@respx.mock
def test_sucesso_cobra(api, funded, product):
    route = respx.post(URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "success": True,
                "data": {
                    "consultaId": "ck_1",
                    "valorCobradoCentavos": 1500,
                    "resultado": {"familia": "VEICULAR", "encontrado": True, "dados": {"placa": "ABC1D23"}},
                },
            },
        )
    )
    r = api.post("/api/consultas/", {"product": product.code, "value": "abc-1d23"}, format="json")
    assert r.status_code == 201, r.json()
    assert r.json()["status"] == "success" and r.json()["result"]["dados"]["placa"] == "ABC1D23"
    assert route.calls[0].request.headers["idempotency-key"].startswith("rd-consulta-")
    assert json.loads(route.calls[0].request.content)["valor"] == "ABC1D23"
    assert balance(funded) == 60_00
    assert Consulta.objects.get().result_encrypted  # resultado cifrado em repouso


@respx.mock
def test_nada_consta_sem_cobranca_estorna(api, funded, product):
    respx.post(URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "success": True,
                "data": {
                    "consultaId": "ck_2",
                    "valorCobradoCentavos": 0,
                    "cobrado": False,
                    "resultado": {"encontrado": False, "mensagem": "Nada consta"},
                },
            },
        )
    )
    r = api.post("/api/consultas/", {"product": product.code, "value": "ABC1D23"}, format="json")
    assert r.json()["status"] == "not_found"
    assert balance(funded) == 100_00


@respx.mock
def test_falha_do_provedor_estorna(api, funded, product):
    respx.post(URL).mock(return_value=httpx.Response(503, json={"success": False, "error": "indisponível", "details": {"cobrado": False}}))
    r = api.post("/api/consultas/", {"product": product.code, "value": "ABC1D23"}, format="json")
    assert r.status_code == 503
    assert balance(funded) == 100_00
    assert Consulta.objects.get().status == "failed"


@respx.mock
def test_falha_com_cobranca_confirmada_cobra(api, funded, product):
    respx.post(URL).mock(return_value=httpx.Response(503, json={"success": False, "error": "x", "details": {"cobrado": True}}))
    api.post("/api/consultas/", {"product": product.code, "value": "ABC1D23"}, format="json")
    assert balance(funded) == 60_00


def test_sem_saldo_nao_chama_provedor(api, org, product):
    with respx.mock(assert_all_called=False) as mock:
        route = mock.post(URL)
        r = api.post("/api/consultas/", {"product": product.code, "value": "ABC1D23"}, format="json")
    assert r.status_code == 402 and not route.called
    assert Consulta.objects.count() == 0


def test_placa_invalida(api, funded, product):
    r = api.post("/api/consultas/", {"product": product.code, "value": "123"}, format="json")
    assert r.status_code == 422


def _sign(body: bytes, ts: str, secret="whsec_test"):
    return "sha256=" + hmac.new(secret.encode(), ts.encode() + b"." + body, hashlib.sha256).hexdigest()


def test_assinatura_webhook():
    body = b'{"consultaId":"cns_1"}'
    ts = datetime.now(UTC).isoformat()
    assert verify_webhook(body, ts, _sign(body, ts))
    assert verify_webhook(body, ts, "sha256=errado," + _sign(body, ts))  # rotação
    assert not verify_webhook(body + b" ", ts, _sign(body, ts))
    assert not verify_webhook(body, "2020-01-01T00:00:00Z", _sign(body, "2020-01-01T00:00:00Z"))


@pytest.mark.django_db
def test_webhook_endpoint_deduplica(client, monkeypatch):
    calls = []
    monkeypatch.setattr("consultas.tasks.refresh_consulta.delay", lambda cid: calls.append(cid))
    body = json.dumps({"deliveryId": "dlv_1", "evento": "consulta.sucesso", "consultaId": "cns_9"}).encode()
    ts = datetime.now(UTC).isoformat()
    headers = {"HTTP_X_BUSCARS_TIMESTAMP": ts, "HTTP_X_BUSCARS_SIGNATURE": _sign(body, ts), "HTTP_X_BUSCARS_DELIVERY": "dlv_1"}
    assert client.post("/api/hooks/consultas", body, content_type="application/json", **headers).status_code == 200
    assert client.post("/api/hooks/consultas", body, content_type="application/json", **headers).status_code == 200
    assert calls == ["cns_9"]
    assert client.post("/api/hooks/consultas", body, content_type="application/json").status_code == 401
