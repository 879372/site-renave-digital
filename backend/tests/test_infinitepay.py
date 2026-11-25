import json
from unittest.mock import patch

import pytest
import respx
from django.core import mail
from django.utils import timezone
from httpx import Response
from rest_framework.test import APIClient

from billing import entitlements, gateway, service
from billing.models import Checkout, Invoice, Plan
from billing.webhooks import confirm_checkout
from integrations.http import ProviderError
from organizations.models import Organization
from wallet.models import TopUp
from wallet.service import get_wallet

pytestmark = pytest.mark.django_db
BASE = "https://checkout.test"
URL = "https://buy.infinitepay.io/loja/checkout-1"


@pytest.fixture
def checkout_on(settings):
    settings.INFINITEPAY = {**settings.INFINITEPAY, "HANDLE": "lojista-teste", "API_KEY": "", "BASE_URL": BASE}
    settings.PUBLIC_API_URL = "https://api.revendadigital.kaibez.com.br"


def invoice(org):
    entitlements.get_subscription(org)
    inv = service.change_plan(org, Plan.objects.get(code="essencial"), "monthly")
    with respx.mock:
        respx.post(BASE + "/links").mock(return_value=Response(200, json={"url": URL}))
        return gateway.push_invoice(inv)


def checked(amount, **extra):
    return {"success": True, "paid": True, "amount": amount, "paid_amount": amount + 100, **extra}


def test_link_exact_amount_stable_reference_and_no_customer_registration(org, checkout_on, django_capture_on_commit_callbacks):
    with respx.mock as mock:
        route = mock.post(BASE + "/links").mock(return_value=Response(200, json={"url": URL}))
        entitlements.get_subscription(org)
        inv = service.change_plan(org, Plan.objects.get(code="essencial"), "monthly")
        with django_capture_on_commit_callbacks(execute=True):
            gateway.push_invoice(inv)
            gateway.push_invoice(inv)
        assert route.call_count == 1
        body = json.loads(route.calls[0].request.content)
        checkout = Checkout.objects.get(invoice=inv)
        assert body["order_nsu"] == checkout.reference
        assert body["items"][0]["price"] == inv.total_cents == 9990
        assert body["webhook_url"] == "https://api.revendadigital.kaibez.com.br/api/hooks/infinitepay"
        assert body["handle"] == "lojista-teste"
        assert "options" not in body
        assert len(mail.outbox) == 1 and URL in mail.outbox[0].body
    inv.refresh_from_db()
    assert inv.payment_url == URL and inv.provider == "infinitepay"
    assert inv.status == "open"


def test_confirm_payment_activates_plan_exactly_once(org, checkout_on, django_capture_on_commit_callbacks):
    inv = invoice(org)
    checkout = inv.checkout
    with respx.mock as mock:
        route = mock.post(BASE + "/payment_check").mock(return_value=Response(200, json=checked(inv.total_cents)))
        with django_capture_on_commit_callbacks(execute=True):
            assert confirm_checkout(checkout.reference, "tx-1", "slug-1")
            assert confirm_checkout(checkout.reference, "tx-1", "slug-1")
        assert route.call_count == 1
        assert json.loads(route.calls[0].request.content)["handle"] == "lojista-teste"
    inv.refresh_from_db()
    assert inv.status == "paid"
    assert entitlements.get_subscription(org).plan.code == "essencial"
    assert len(mail.outbox) == 1 and "confirmado" in mail.outbox[0].subject


@pytest.mark.parametrize(
    "response",
    [
        {"success": False, "paid": True, "amount": 9990, "paid_amount": 9990},
        {"success": True, "paid": False, "amount": 9990, "paid_amount": 9990},
        checked(1),
        checked(10000),
        checked(9990, paid_amount=1),
        {**checked(9990), "amount": "9990"},
        checked(9990, paid="true"),
        {},
    ],
)
def test_invalid_or_underpaid_never_releases_plan(org, checkout_on, response):
    inv = invoice(org)
    with respx.mock:
        respx.post(BASE + "/payment_check").mock(return_value=Response(200, json=response))
        assert not confirm_checkout(inv.checkout.reference, "tx-1", "slug-1")
    inv.refresh_from_db()
    assert inv.status == "open"
    assert entitlements.get_subscription(org).status == "trialing"


def test_webhook_only_queues_known_order_and_ignores_claimed_amount(org, checkout_on):
    inv = invoice(org)
    payload = {"order_nsu": inv.checkout.reference, "transaction_nsu": "tx-1", "invoice_slug": "slug-1", "paid": True, "amount": 9990}
    with patch("billing.tasks.confirm_checkout_payment.apply_async") as queue:
        assert APIClient().post("/api/hooks/infinitepay", payload, format="json").status_code == 200
        queue.assert_called_once_with(
            args=(inv.checkout.reference, "tx-1", "slug-1"), argsrepr="(<confirmação de checkout>)", kwargsrepr="{}"
        )
    inv.refresh_from_db()
    assert inv.status == "open"
    assert APIClient().post("/api/hooks/infinitepay", [], format="json").status_code == 400
    assert APIClient().post("/api/hooks/infinitepay", {"order_nsu": inv.checkout.reference}, format="json").status_code == 400


def test_recarga_checkout_and_duplicate_confirmation_credit_once(api, org, checkout_on):
    with respx.mock:
        respx.post(BASE + "/links").mock(return_value=Response(200, json={"url": URL}))
        response = api.post("/api/wallet/topups", {"amount_cents": 5000}, format="json")
    assert response.status_code == 201
    assert response.data["payment_url"] == URL and response.data["provider"] == "infinitepay"
    topup = TopUp.objects.get()
    with respx.mock:
        respx.post(BASE + "/payment_check").mock(return_value=Response(200, json=checked(5000)))
        assert confirm_checkout(topup.checkout.reference, "tx-topup", "slug-topup")
        assert confirm_checkout(topup.checkout.reference, "tx-topup", "slug-topup")
    assert get_wallet(org).balance_cents == 5000


def test_same_transaction_cannot_pay_two_orders(org, checkout_on):
    one = invoice(org)
    two = Invoice.objects.create(
        organization=org, subscription=one.subscription, kind="renewal", total_cents=one.total_cents, due_date=timezone.localdate()
    )
    with respx.mock:
        respx.post(BASE + "/links").mock(return_value=Response(200, json={"url": URL}))
        two = gateway.push_invoice(two)
        respx.post(BASE + "/payment_check").mock(return_value=Response(200, json=checked(one.total_cents)))
        assert confirm_checkout(one.checkout.reference, "same-tx", "slug-1")
        assert not confirm_checkout(two.checkout.reference, "same-tx", "slug-2")
    two.refresh_from_db()
    assert two.status == "open"


def test_payment_of_canceled_upgrade_does_not_activate_it(org, checkout_on):
    inv = invoice(org)
    service.cancel_invoice(inv)
    with respx.mock:
        respx.post(BASE + "/payment_check").mock(return_value=Response(200, json=checked(inv.total_cents)))
        assert confirm_checkout(inv.checkout.reference, "late-tx", "slug")
    assert entitlements.get_subscription(org).status == "trialing"
    inv.refresh_from_db()
    assert inv.status == "paid" and inv.canceled_at is not None


def test_502_retryable_and_failed_topup_rolls_back(api, org, checkout_on):
    with respx.mock:
        respx.post(BASE + "/links").mock(return_value=Response(503, json={}))
        response = api.post("/api/wallet/topups", {"amount_cents": 5000}, format="json")
    assert response.status_code == 503
    assert not TopUp.objects.exists() and not Checkout.objects.exists()


def test_confirmation_endpoint_tenant_isolation(api, org, checkout_on):
    inv = invoice(org)
    other = Organization.objects.create(cnpj="19131243000197", legal_name="Outra")
    checkout = Checkout.objects.create(
        topup=TopUp.objects.create(organization=other, amount_cents=5000, provider="infinitepay"), amount_cents=5000, handle="lojista-teste"
    )
    with patch("billing.webhooks.confirm_checkout") as check:
        assert (
            api.post(
                "/api/billing/checkout/confirm", {"order_nsu": checkout.reference, "transaction_nsu": "tx", "slug": "s"}, format="json"
            ).status_code
            == 404
        )
        check.assert_not_called()
    with respx.mock:
        respx.post(BASE + "/payment_check").mock(return_value=Response(200, json=checked(inv.total_cents)))
        assert api.post(
            "/api/billing/checkout/confirm", {"order_nsu": inv.checkout.reference, "transaction_nsu": "tx", "slug": "s"}, format="json"
        ).data["paid"]


def test_checkout_uses_key_for_single_payment(org, checkout_on, settings):
    settings.INFINITEPAY = {**settings.INFINITEPAY, "API_KEY": "inchk_test"}
    with respx.mock as mock:
        route = mock.post(BASE + "/links").mock(return_value=Response(200, json={"url": URL}))
        entitlements.get_subscription(org)
        inv = service.change_plan(org, Plan.objects.get(code="essencial"), "monthly")
        gateway.push_invoice(inv)
        body = json.loads(route.calls[0].request.content)
        assert body["options"]["single_payment"] is True
        assert route.calls[0].request.headers["X-Api-Key"] == "inchk_test"


def test_gateway_rejects_external_redirect(org, checkout_on):
    entitlements.get_subscription(org)
    inv = service.change_plan(org, Plan.objects.get(code="essencial"), "monthly")
    with respx.mock:
        respx.post(BASE + "/links").mock(return_value=Response(200, json={"url": "https://evil.test/pay"}))
        with pytest.raises(ProviderError):
            gateway.push_invoice(inv)
    inv.refresh_from_db()
    assert not inv.payment_url
