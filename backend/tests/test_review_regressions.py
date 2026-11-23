"""Regressões dos problemas encontrados na revisão das fases 1 a 3."""

from unittest.mock import patch

import pytest
from django.core.files.base import ContentFile
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APIClient

from billing import entitlements
from billing import service as billing
from billing.models import Subscription
from estoque import service as stock
from estoque.models import Avaliacao, AvaliacaoFoto, Vehicle
from financeiro.models import Lancamento
from organizations.models import Organization
from pessoas.models import Pessoa
from posvenda.models import Garantia, Ocorrencia
from renave.models import StockVehicle
from vendas.models import Venda
from vitrine.models import Site
from wallet import service as wallet

from . import test_gestao
from .conftest import OTHER_CNPJ
from .test_gestao import _venda, make_vehicle, use_plan


@pytest.fixture
def premium(org):
    use_plan(org, "premium")
    return org


@pytest.fixture
def cliente(org):
    return test_gestao.cliente.__wrapped__(org)


def branch(api):
    r = api.post("/api/lojas/", {"cnpj": OTHER_CNPJ, "legal_name": "Filial", "uf": "RN", "city": "Natal"}, format="json")
    assert r.status_code == 201, r.data
    return Organization.objects.get(cnpj=OTHER_CNPJ)


def branch_api(user, org):
    c = APIClient()
    c.force_authenticate(user)
    c.credentials(HTTP_X_ORGANIZATION=str(org.public_id))
    return c


def closed_sale(api, cliente, published=False):
    vid = make_vehicle(api, published=published)
    sale_id = _venda(api, vid, cliente)
    assert (
        api.put(f"/api/vendas/{sale_id}/payments", {"items": [{"method": "pix", "amount_cents": 6000000}]}, format="json").status_code
        == 200
    )
    assert api.post(f"/api/vendas/{sale_id}/close").status_code == 200
    return Venda.objects.get(public_id=sale_id)


def test_branch_postpaid_consumption_is_in_parent_invoice(api, premium):
    b = branch(api)
    assert wallet.get_wallet(b).credit_limit_cents == Subscription.objects.get(organization=premium).plan.credit_limit_cents
    reservation = wallet.reserve(b, 3000, "RENAVE filial", ref_type="renave", ref_id="one")
    wallet.capture(reservation)
    sub = Subscription.objects.get(organization=premium)
    inv = billing.renew(sub, sub.next_billing_date)
    assert sum(inv.items.filter(kind="usage").values_list("total_cents", flat=True)) == 3000
    assert wallet.get_wallet(b).balance_cents == 0
    assert billing.renew(sub, sub.next_billing_date) is None


def test_downgrade_blocks_branch_fiscal_and_operations(api, premium, user):
    b = branch(api)
    use_plan(premium, "essencial")
    c = branch_api(user, b)
    assert c.get("/api/estoque/veiculos").status_code == 402
    assert c.get("/api/fiscal/notas").status_code == 402
    assert wallet.get_wallet(b).credit_limit_cents == 0
    with pytest.raises(entitlements.PlanRequired):
        entitlements.require_feature(b, "fiscal")
    use_plan(premium, "premium")
    assert c.get("/api/estoque/veiculos").status_code == 200


def test_transfer_cannot_delete_origin_payable(api, premium, user):
    b = branch(api)
    vid = make_vehicle(api)
    v = Vehicle.objects.get(public_id=vid)
    cost = stock.add_cost(v, category="mecanica", description="Motor", amount_cents=15000, date=timezone.localdate(), paid=False)
    payable_id = cost.payable_id
    payload = {"vehicle": vid, "target": str(b.public_id)}
    assert api.post("/api/lojas/transferir", payload, format="json").status_code == 422
    payable = Lancamento.objects.get(pk=payable_id)
    payable.paid_at = timezone.localdate()
    payable.save()
    assert api.post("/api/lojas/transferir", payload, format="json").status_code == 200
    cost.refresh_from_db()
    assert cost.payable_id is None and cost.organization_id == b.pk
    stock.remove_cost(cost)
    payable.refresh_from_db()
    assert payable.organization_id == premium.pk and payable.vehicle_id is None


def test_transfer_preserves_consignor_and_payout(api, premium, user, cliente):
    b = branch(api)
    vid = make_vehicle(api, ownership="consignado", consignor=str(cliente.public_id), consignment_mode="liquido", consignment_value=5000000)
    assert api.post("/api/lojas/transferir", {"vehicle": vid, "target": str(b.public_id)}, format="json").status_code == 200
    v = Vehicle.objects.get(public_id=vid)
    assert v.consignor.organization_id == b.pk and v.consignor.documento == cliente.documento
    c = branch_api(user, b)
    buyer = Pessoa.objects.create(organization=b, nome="Comprador")
    sale_id = _venda(c, vid, buyer)
    c.put(f"/api/vendas/{sale_id}/payments", {"items": [{"method": "pix", "amount_cents": 6000000}]}, format="json")
    r = c.post(f"/api/vendas/{sale_id}/close")
    assert r.status_code == 200, r.data
    payout = Lancamento.objects.get(organization=b, origin="consignacao")
    assert payout.amount_cents == 5000000 and payout.pessoa_id == v.consignor_id


def test_company_buyer_never_sends_dealer_transfer(api, premium, cliente):
    sale = closed_sale(api, cliente)
    cliente.documento = OTHER_CNPJ
    cliente.save()
    reg = StockVehicle.objects.create(organization=premium, placa="ABC1D23", owner_document=premium.cnpj)
    sale.vehicle.renave = reg
    sale.vehicle.save()
    with patch("renave.service.saida") as send:
        r = api.post(f"/api/vendas/{sale.public_id}/renave-saida", {}, format="json")
    assert r.status_code == 422
    assert r.data["error"]["code"] == "renave_cnpj_unsupported"
    send.assert_not_called()


def test_rejected_warranty_change_rolls_back_occurrence(api, premium, cliente):
    sale = closed_sale(api, cliente)
    warranty = Garantia.objects.get(venda=sale)
    r = api.post(
        "/api/posvenda/ocorrencias", {"garantia": str(warranty.public_id), "description": "Motor", "cost_cents": 15000}, format="json"
    )
    oc = Ocorrencia.objects.get(public_id=r.data["id"])
    entry = oc.lancamento
    entry.paid_at = timezone.localdate()
    entry.save()
    r = api.patch(f"/api/posvenda/ocorrencias/{oc.public_id}", {"cost_cents": 25000, "resolution": "changed"}, format="json")
    assert r.status_code == 400
    oc.refresh_from_db()
    entry.refresh_from_db()
    assert oc.cost_cents == entry.amount_cents == 15000
    assert oc.resolution == ""


def test_purchase_copies_evaluation_image(api, premium, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    av = Avaliacao.objects.create(organization=premium, marca="Fiat", modelo="Uno", status="aprovada")
    photo = AvaliacaoFoto(organization=premium, avaliacao=av)
    photo.image.save("original.jpg", ContentFile(b"image content"))
    vehicle = stock.buy_from_evaluation(av)
    copied = vehicle.photos.get()
    assert copied.image.name != photo.image.name
    copied.image.delete()
    assert photo.image.storage.exists(photo.image.name)
    with photo.image.open("rb") as f:
        assert f.read() == b"image content"


def test_cancel_restores_previously_published_car(api, premium, cliente):
    sale = closed_sale(api, cliente, published=True)
    sale.vehicle.refresh_from_db()
    assert not sale.vehicle.published
    assert api.post(f"/api/vendas/{sale.public_id}/cancel", {"reason": "Desistência do cliente"}, format="json").status_code == 200
    sale.vehicle.refresh_from_db()
    assert sale.vehicle.published and sale.vehicle.status == "disponivel"


@pytest.mark.parametrize("maximum", ["abc", "-1", "99999999999999999999999"])
def test_public_price_filter_returns_validation_error(api, premium, maximum):
    Site.objects.create(organization=premium, slug="review-loja", is_published=True)
    assert APIClient().get(f"/api/public/lojas/review-loja/veiculos?max={maximum}").status_code == 400


def test_dashboard_cost_queries_dont_grow_with_stock(api, premium):
    make_vehicle(api)
    with CaptureQueriesContext(connection) as first:
        assert api.get("/api/painel/dashboard").status_code == 200
    Vehicle.objects.bulk_create(
        [Vehicle(organization=premium, marca="Fiat", modelo=f"Carro {i}", purchase_price_cents=10000) for i in range(30)]
    )
    with CaptureQueriesContext(connection) as many:
        response = api.get("/api/painel/dashboard")
    assert response.status_code == 200
    assert len(many) <= len(first) + 1
    assert response.data["stock"]["cost_cents"] == 5300000
