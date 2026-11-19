import pyotp
import pytest
from rest_framework.test import APIClient

from accounts import totp
from organizations.models import Membership, Organization, Role

from .conftest import OTHER_CNPJ

REGISTER = {
    "full_name": "Maria Lojista",
    "email": "maria@loja.com.br",
    "phone": "84999990000",
    "cpf": "529.982.247-25",
    "password": "Uma-Senha-Muito-Forte-9",
    "password_confirm": "Uma-Senha-Muito-Forte-9",
    "cnpj": "19.131.243/0001-97",
    "legal_name": "Maria Veiculos LTDA",
    "uf": "rn",
    "city": "Natal",
    "accept_terms": True,
}


@pytest.mark.django_db
def test_cadastro_login_refresh_logout():
    c = APIClient()
    r = c.post("/api/auth/register", REGISTER, format="json")
    assert r.status_code == 201, r.json()
    assert "access" in r.json() and "rd_refresh" in r.cookies
    assert r.cookies["rd_refresh"]["httponly"]

    r = c.post("/api/auth/refresh")
    assert r.status_code == 200 and r.json()["access"]

    me = c.get("/api/auth/me", HTTP_AUTHORIZATION=f"Bearer {r.json()['access']}")
    assert me.json()["organizations"][0]["role"] == "owner"

    assert c.post("/api/auth/logout").status_code == 204
    assert c.post("/api/auth/refresh").status_code == 401


@pytest.mark.django_db
def test_login_errado_bloqueia(user):
    c = APIClient()
    for _ in range(5):
        assert c.post("/api/auth/login", {"email": user.email, "password": "errada"}, format="json").status_code == 401
    r = c.post("/api/auth/login", {"email": user.email, "password": "Senha-Forte-123"}, format="json")
    assert r.status_code == 429


@pytest.mark.django_db
def test_login_com_2fa(user):
    secret = totp.new_secret()
    totp.store_secret(user, secret)
    user.totp_enabled = True
    user.save()
    c = APIClient()
    r = c.post("/api/auth/login", {"email": user.email, "password": "Senha-Forte-123"}, format="json")
    assert r.json()["mfa_required"] and "access" not in r.json()
    bad = c.post("/api/auth/login/mfa", {"mfa_token": r.json()["mfa_token"], "code": "000000"}, format="json")
    assert bad.status_code == 401
    ok = c.post("/api/auth/login/mfa", {"mfa_token": r.json()["mfa_token"], "code": pyotp.TOTP(secret).now()}, format="json")
    assert ok.status_code == 200 and ok.json()["access"]


@pytest.mark.django_db
def test_isolamento_entre_empresas(api, user):
    other = Organization.objects.create(cnpj=OTHER_CNPJ, legal_name="Outra")
    api.credentials(HTTP_X_ORGANIZATION=str(other.public_id))
    assert api.get("/api/wallet/").status_code == 404


@pytest.mark.django_db
def test_papel_somente_leitura_nao_executa(api, user, org):
    Membership.objects.filter(user=user).update(role=Role.VIEWER)
    r = api.post("/api/consultas/", {"product": "x", "value": "ABC1D23"}, format="json")
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "permission_denied"


@pytest.mark.django_db
def test_sem_cabecalho_de_empresa(user):
    c = APIClient()
    c.force_authenticate(user)
    assert c.get("/api/wallet/").status_code == 403
