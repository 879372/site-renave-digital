import httpx
import pytest
import respx
from rest_framework.test import APIClient

from accounts.models import User
from core.masking import scrub_provider
from organizations.models import Membership, Organization

from .test_auth_and_tenancy import REGISTER


@pytest.mark.django_db
def test_cadastro_exige_confirmacao_e_registra_aceite():
    c = APIClient()
    r = c.post("/api/auth/register", {**REGISTER, "password_confirm": "outra"}, format="json")
    assert r.status_code == 400 and "password_confirm" in r.json()["error"]["fields"]
    r = c.post("/api/auth/register", REGISTER, format="json")
    assert r.status_code == 201
    user = User.objects.get(email=REGISTER["email"])
    assert user.terms_accepted_at and user.legal_version


@pytest.mark.django_db
def test_cadastro_completa_endereco_pelo_cnpj(monkeypatch):
    monkeypatch.setattr(
        "integrations.lookups.company",
        lambda cnpj: {
            "zip_code": "59000000",
            "street": "Rua A",
            "number": "10",
            "district": "Centro",
            "city_ibge": "2408102",
            "city": "Natal",
            "uf": "RN",
        },
    )
    APIClient().post("/api/auth/register", REGISTER, format="json")
    org = Organization.objects.get(cnpj="19131243000197")
    assert org.street == "Rua A" and org.city_ibge == "2408102"


@respx.mock
@pytest.mark.django_db
def test_lookup_cnpj_publico(monkeypatch):
    monkeypatch.undo()  # libera _get, mas o respx bloqueia a rede
    respx.get("https://brasilapi.com.br/api/cnpj/v1/19131243000197").mock(
        return_value=httpx.Response(
            200,
            json={
                "razao_social": "EMPRESA X LTDA",
                "municipio": "SAO PAULO",
                "uf": "SP",
                "codigo_municipio_ibge": 3550308,
                "cep": "01001-000",
            },
        )
    )
    r = APIClient().get("/api/lookup/cnpj/19131243000197")
    assert r.status_code == 200
    body = r.json()
    assert body["legal_name"] == "EMPRESA X LTDA" and body["city"] == "Sao Paulo" and body["city_ibge"] == "3550308"
    assert APIClient().get("/api/lookup/cnpj/123").status_code == 404


def test_exportar_dados(api, user):
    r = api.get("/api/auth/me/export")
    assert r.status_code == 200 and r.json()["titular"]["email"] == user.email
    assert "attachment" in r["Content-Disposition"]


def test_excluir_conta_anonimiza(api, user, org):
    assert api.post("/api/auth/me/delete", {"password": "errada", "confirmation": "EXCLUIR"}, format="json").status_code == 403
    r = api.post("/api/auth/me/delete", {"password": "Senha-Forte-123", "confirmation": "excluir"}, format="json")
    assert r.status_code == 204
    user.refresh_from_db()
    org.refresh_from_db()
    assert not user.is_active and user.cpf == "" and "anonimo" in user.email
    assert not org.is_active and not Membership.objects.filter(user=user).exists()


def test_proprietario_com_equipe_nao_exclui(api, user, org):
    other = User.objects.create_user(email="op@x.com", password="Senha-Forte-123", full_name="Op")
    Membership.objects.create(user=other, organization=org, role="operator")
    r = api.post("/api/auth/me/delete", {"password": "Senha-Forte-123", "confirmation": "EXCLUIR"}, format="json")
    assert r.status_code == 403


def test_lojista_cadastra_outra_empresa(api, user):
    r = api.post(
        "/api/organizations/", {"cnpj": "19.131.243/0001-97", "legal_name": "Filial", "uf": "rn", "city": "Mossoró"}, format="json"
    )
    assert r.status_code == 201
    assert Membership.objects.filter(user=user, role="owner").count() == 2


def test_nomes_de_fornecedores_nao_vazam(api, db):
    from consultas.models import Product

    Product.objects.create(code="leilao", sku="veicular-leilao-base-3-cf", name="Leilão", price_cents=100, is_active=True)
    body = api.get("/api/consultas/products").content.decode()
    assert "veicular-leilao-base-3-cf" not in body and '"code":"leilao"' in body
    assert scrub_provider("Erro no motor Geranet NFe e na Carven") == "Erro no motor serviço e na serviço"


def test_emails_saem_do_dominio_com_resposta_para_suporte(user, django_capture_on_commit_callbacks):
    from django.core import mail
    from rest_framework.test import APIClient

    with django_capture_on_commit_callbacks(execute=True):
        assert APIClient().post("/api/auth/password/reset", {"email": user.email}, format="json").status_code == 202
    assert len(mail.outbox) == 1
    msg = mail.outbox[0]
    assert msg.from_email.endswith("@kaiobez.com.br>") and msg.reply_to == ["contato@kaiobez.com.br"]
    assert "/redefinir-senha?uid=" in msg.body


def test_convite_envia_email(api, django_capture_on_commit_callbacks):
    from django.core import mail

    with django_capture_on_commit_callbacks(execute=True):
        r = api.post("/api/organizations/invitations", {"email": "novo@loja.com.br", "role": "operator"}, format="json")
    assert r.status_code == 201 and mail.outbox[0].to == ["novo@loja.com.br"]
