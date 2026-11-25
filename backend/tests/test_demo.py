from io import StringIO
from unittest.mock import patch

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.utils import timezone

from billing.models import Invoice
from billing.service import run_daily
from core.management.commands.seed_demo import DEMO_CNPJ
from estoque.models import Vehicle
from organizations.models import Organization
from vendas.models import Venda


@pytest.mark.django_db
def test_demo_complete_idempotent_without_billing(user, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    with patch("billing.tasks.push_invoice.delay") as push:
        call_command("seed_demo", owner_email=user.email, stdout=StringIO())
        org = Organization.objects.get(cnpj=DEMO_CNPJ)
        assert org.memberships.filter(user=user, role="owner").exists()
        assert org.vehicles.count() == 16
        assert sum(v.photos.count() for v in org.vehicles.all()) == 16
        assert org.vendas.filter(status=Venda.Status.FECHADA).count() == 6
        assert org.leads.count() == 18
        assert org.avaliacoes.count() == 4
        assert org.fichas.count() == 3
        assert org.ocorrencias.count() == 2
        assert org.documentos.count() == 9
        assert org.vehicles.filter(ownership="consignado", status=Vehicle.Status.VENDIDO).exists()
        assert org.lancamentos.filter(origin="consignacao").exists()
        assert org.lancamentos.filter(due_date__lt=timezone.localdate(), paid_at__isnull=True).exists()
        for sale in org.vendas.filter(status="fechada"):
            assert sale.paid_total() == sale.price_cents
            assert sale.profit_cents == sale.price_cents - sale.cost_cents - sale.consignor_payout_cents
        before = (org.vehicles.count(), org.lancamentos.count(), org.documentos.count())
        call_command("seed_demo", owner_email=user.email, stdout=StringIO())
        assert before == (org.vehicles.count(), org.lancamentos.count(), org.documentos.count())
        run_daily()
        assert not Invoice.objects.filter(organization=org).exists()
        push.assert_not_called()
        assert not org.renave_operations.exists()
        assert not org.notas.exists()


@pytest.mark.django_db
def test_demo_requires_existing_owner():
    with pytest.raises(CommandError):
        call_command("seed_demo", owner_email="absent@example.invalid", no_images=True)
    assert not Organization.objects.filter(cnpj=DEMO_CNPJ).exists()


@pytest.mark.django_db
def test_demo_storefront_uses_configured_public_path(user, settings):
    from rest_framework.test import APIClient

    settings.STOREFRONT_BASE_URL = "https://app.revendadigital.kaibez.com.br/loja"
    call_command("seed_demo", owner_email=user.email, no_images=True, stdout=StringIO())
    org = Organization.objects.get(cnpj=DEMO_CNPJ)
    client = APIClient()
    client.force_authenticate(user)
    client.credentials(HTTP_X_ORGANIZATION=str(org.public_id))
    response = client.get("/api/site/")
    assert response.status_code == 200
    assert response.data["url"] == "https://app.revendadigital.kaibez.com.br/loja/revenda-demonstracao"
    assert response.data["feed_url"]
    assert client.put("/api/site/", {"title": org.trade_name}, format="json").status_code == 200


@pytest.mark.django_db
def test_complete_demo_fills_both_stores_without_external_calls_or_duplicates(user, settings, tmp_path):
    from rest_framework.test import APIClient

    from financeiro.models import Lancamento
    from wallet.service import get_wallet

    settings.MEDIA_ROOT = tmp_path
    call_command("seed_demo", owner_email=user.email, no_images=True, stdout=StringIO())
    with (
        patch("integrations.http.BaseClient.request", side_effect=AssertionError("Não chamar provedor")),
        patch("core.email._deliver.apply_async") as email,
    ):
        call_command("complete_demo", owner_email=user.email, stdout=StringIO())
        orgs = Organization.objects.filter(cnpj__in=["00000000000000", "00000000000001"])
        before = {}
        for org in orgs:
            assert org.vehicles.count() >= 15
            assert not org.vehicles.filter(photos__isnull=True).exists()
            assert org.vendas.filter(status="fechada").count() >= 6
            assert org.garantias.count() >= 6
            assert org.ocorrencias.count() >= 4
            assert org.pessoas.count() >= 10
            assert org.leads.count() >= 12
            assert org.fichas.count() >= 4
            assert org.documentos.count() >= 6
            assert org.clients.count() == 2
            assert org.certificates.filter(is_active=False).exists()
            assert org.site.feed_token
            assert org.notas.filter(ambiente="2", status="error", authorized_at__isnull=True).count() == 3
            assert org.stock.filter(id_estoque__isnull=True, state="NEGADO").count() == 3
            assert org.consultas.count() == 1
            assert get_wallet(org).balance_cents == 50000
            assert org.lancamentos.filter(origin="comissao").exists()
            assert org.vehicles.filter(documents__isnull=False).exists()
            client = APIClient()
            client.force_authenticate(user)
            client.credentials(HTTP_X_ORGANIZATION=str(org.public_id))
            paths = [
                "estoque/veiculos",
                "estoque/avaliacoes",
                "vendas/",
                "crm/leads",
                "crm/tarefas",
                "pessoas/",
                "financiamento/fichas",
                "posvenda/garantias",
                "posvenda/ocorrencias",
                "financeiro/resumo",
                "financeiro/dre",
                "financeiro/fluxo",
                "vendas/comissoes",
                "contratos/modelos",
                "contratos/documentos",
                "painel/dashboard",
                "painel/relatorios?tipo=estoque",
                "site/",
                "fiscal/notas",
                "renave/stock",
                "comunicacao-venda/",
                "consultas/",
                "wallet/",
                "billing/me",
            ]
            for path in paths:
                r = client.get("/api/" + path)
                assert r.status_code == 200, (path, r.status_code)
            assert client.post("/api/billing/change-plan", {}, format="json").status_code == 403
            assert client.post("/api/wallet/topups", {"amount_cents": 2000}, format="json").status_code == 403
            assert client.post("/api/fiscal/notas", {}, format="json").status_code == 403
            assert client.put("/api/site/", {"title": str(org)}, format="json").status_code == 200
            before[org.pk] = (org.vehicles.count(), org.lancamentos.count(), org.documentos.count(), org.invoices.count())
        call_command("complete_demo", owner_email=user.email, stdout=StringIO())
        for org in orgs:
            assert before[org.pk] == (org.vehicles.count(), org.lancamentos.count(), org.documentos.count(), org.invoices.count())
        run_daily()
        assert not Invoice.objects.filter(provider="infinitepay").exists()
        assert not Lancamento.objects.filter(organization__cnpj__in=["00000000000000", "00000000000001"], amount_cents__lte=0).exists()
        email.assert_not_called()
