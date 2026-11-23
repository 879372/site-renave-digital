"""O app (app.) e os sites das lojas (<slug>.) chamam a API em outro domínio (api.)."""

from django.test import override_settings
from rest_framework.test import APIClient

APP = "https://app.revendadigital.kaibez.com.br"


@override_settings(CORS_ALLOWED_ORIGINS=[APP], CSRF_TRUSTED_ORIGINS=[APP])
def test_preflight_do_app_com_credenciais(db):
    r = APIClient().options(
        "/api/billing/me",
        HTTP_ORIGIN=APP,
        HTTP_ACCESS_CONTROL_REQUEST_METHOD="GET",
        HTTP_ACCESS_CONTROL_REQUEST_HEADERS="authorization,x-organization",
    )
    assert r["access-control-allow-origin"] == APP
    assert r["access-control-allow-credentials"] == "true"
    assert "x-organization" in r["access-control-allow-headers"]


def test_site_da_loja_pode_chamar_rotas_publicas(db):
    r = APIClient().options(
        "/api/public/lojas/teste", HTTP_ORIGIN="https://teste.revendadigital.kaibez.com.br", HTTP_ACCESS_CONTROL_REQUEST_METHOD="GET"
    )
    assert r["access-control-allow-origin"] == "https://teste.revendadigital.kaibez.com.br"


def test_outro_dominio_nao_e_liberado(db):
    r = APIClient().options(
        "/api/public/lojas/teste", HTTP_ORIGIN="https://revendadigital.kaibez.com.br.golpe.com", HTTP_ACCESS_CONTROL_REQUEST_METHOD="GET"
    )
    assert "access-control-allow-origin" not in r
