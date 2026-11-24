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
