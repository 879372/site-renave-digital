import pytest
from rest_framework.test import APIClient

from accounts.models import User
from organizations.models import Membership, Organization, Role
from wallet import service as wallet

VALID_CNPJ = "11222333000181"
OTHER_CNPJ = "19131243000197"


@pytest.fixture(autouse=True)
def _clear_cache():
    from django.core.cache import cache

    cache.clear()


@pytest.fixture(autouse=True)
def _no_public_lookups(monkeypatch):
    """Testes nunca acessam serviços externos de CNPJ/CEP."""
    monkeypatch.setattr("integrations.lookups._get", lambda url: None)


@pytest.fixture
def user(db):
    return User.objects.create_user(email="dono@loja.com.br", password="Senha-Forte-123", full_name="Dono da Loja", cpf="52998224725")


@pytest.fixture
def org(user):
    org = Organization.objects.create(cnpj=VALID_CNPJ, legal_name="Loja Exemplo LTDA", uf="RN", city="Natal", email="loja@x.com")
    Membership.objects.create(user=user, organization=org, role=Role.OWNER)
    return org


@pytest.fixture
def api(user, org):
    client = APIClient()
    client.force_authenticate(user)
    client.credentials(HTTP_X_ORGANIZATION=str(org.public_id))
    return client


@pytest.fixture
def funded(org):
    wallet.credit(org, 100_00, "Crédito de teste", key="seed")
    return org
