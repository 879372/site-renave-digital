from datetime import date, timedelta

import pytest
from django.utils import timezone
from freezegun import freeze_time
from rest_framework.test import APIClient

from billing import entitlements, service
from billing.models import Invoice, InvoiceItem, Plan, Subscription
from core.exceptions import InsufficientBalance
from organizations.models import Membership, Organization, Role
from wallet import service as wallet
from wallet.models import LedgerEntry, ServicePrice

from .conftest import OTHER_CNPJ
from .test_backoffice import login

WEBHOOK = "/api/hooks/asaas"


def plan(code):
    return Plan.objects.get(code=code)


def sub_of(org):
    return Subscription.objects.select_related("plan").get(organization=org)


def pay(invoice):
    return service.mark_paid(Invoice.objects.get(pk=invoice.pk))


@pytest.fixture
def active_essencial(org):
    entitlements.get_subscription(org)
    inv = service.change_plan(org, plan("essencial"), "monthly")
    pay(inv)
    return sub_of(org)


# --- teste e direitos ----------------------------------------------------------------------


def test_revenda_nova_ganha_teste_do_profissional(org):
    sub = entitlements.get_subscription(org)
    assert sub.status == Subscription.Status.TRIALING and sub.plan.code == "profissional"
    assert sub.trial_ends_at > timezone.now() + timedelta(days=13)
    assert entitlements.has_feature(org, "crm")
    assert wallet.get_wallet(org).credit_limit_cents == 0  # teste é pré-pago


def test_criar_empresa_pela_api_inicia_teste(api):
    r = api.post("/api/organizations/", {"cnpj": OTHER_CNPJ, "legal_name": "Outra Loja", "uf": "RN", "city": "Natal"}, format="json")
    assert r.status_code == 201, r.json()
    org = Organization.objects.get(cnpj=OTHER_CNPJ)
    assert sub_of(org).status == Subscription.Status.TRIALING


def test_toda_empresa_esta_nos_planos_mesmo_com_tipo_antigo(org):
    """A plataforma é só para lojas: um tipo legado (ex.: despachante) não escapa da assinatura."""
    org.kind = Organization.Kind.DESPACHANTE
    org.save()
    assert entitlements.get_subscription(org).status == Subscription.Status.TRIALING


def test_cadastro_ignora_tipo_de_negocio(api):
    r = api.post(
        "/api/organizations/",
        {"cnpj": OTHER_CNPJ, "legal_name": "Outra", "uf": "RN", "city": "Natal", "kind": "despachante"},
        format="json",
    )
    assert r.status_code == 201
    assert Organization.objects.get(cnpj=OTHER_CNPJ).kind == Organization.Kind.REVENDA


def test_fim_do_teste_cai_no_gratis_sem_nota_fiscal(org):
    entitlements.get_subscription(org)
    with freeze_time(timezone.now() + timedelta(days=15)):
        assert service.expire_trials() == 1
    sub = sub_of(org)
    assert sub.plan.code == "gratis" and sub.status == Subscription.Status.ACTIVE
    with pytest.raises(entitlements.PlanRequired) as exc:
        entitlements.require_feature(org, "fiscal")
    assert exc.value.extra["required_plan"] == "essencial"


def test_api_me_mostra_plano_e_limites(api, org):
    r = api.get("/api/billing/me")
    body = r.json()
    assert r.status_code == 200 and body["applies"] is True
    assert body["subscription"]["plan"]["code"] == "profissional"
    assert body["limits"] == {"vehicles": 100, "users": 6, "plate_queries": 300}
    assert "fiscal" in body["features"]


def test_planos_publicados(api):
    codes = [p["code"] for p in api.get("/api/billing/plans").json()]
    assert codes == ["gratis", "essencial", "profissional", "premium"]


# --- preços ----------------------------------------------------------------------------------


def test_renave_custa_30_e_nfe_inclusa_no_plano(org):
    assert wallet.price_for(ServicePrice.Code.RENAVE_ENTRADA, org) == 3000
    assert wallet.price_for(ServicePrice.Code.NFE, org) == 0  # teste do Profissional inclui nota
    service.change_plan(org, plan("gratis"), "monthly")
    assert wallet.price_for(ServicePrice.Code.NFE, org) == 190  # sem o recurso (e a emissão é bloqueada)


# --- contratação -----------------------------------------------------------------------------


def test_contratar_so_muda_o_plano_depois_de_pagar(api, org):
    r = api.post("/api/billing/change-plan", {"plan": "essencial", "cycle": "monthly"}, format="json")
    assert r.status_code == 201, r.json()
    inv = Invoice.objects.get(public_id=r.json()["invoice"]["id"])
    assert inv.total_cents == 9990 and inv.status == Invoice.Status.OPEN
    assert sub_of(org).status == Subscription.Status.TRIALING

    pay(inv)
    sub = sub_of(org)
    assert sub.plan.code == "essencial" and sub.status == Subscription.Status.ACTIVE
    assert sub.paid_through == service.add_months(timezone.localdate(), 1)
    assert wallet.get_wallet(org).credit_limit_cents == 50000


def test_vendedor_nao_contrata_plano(api, org, user):
    Membership.objects.filter(user=user, organization=org).update(role=Role.SELLER)
    r = api.post("/api/billing/change-plan", {"plan": "essencial"}, format="json")
    assert r.status_code == 403


def test_nova_contratacao_cancela_fatura_anterior_em_aberto(org):
    entitlements.get_subscription(org)
    first = service.change_plan(org, plan("essencial"), "monthly")
    second = service.change_plan(org, plan("premium"), "annual")
    first.refresh_from_db()
    assert first.status == Invoice.Status.CANCELED
    assert second.total_cents == 269900
    pay(first)  # pagou a fatura velha mesmo assim: não troca o plano
    assert sub_of(org).plan.code == "profissional"


def test_subir_de_plano_desconta_dias_nao_usados(org, active_essencial):
    with freeze_time(timezone.localdate() + timedelta(days=15)):
        inv = service.change_plan(org, plan("premium"), "monthly")
    credit = inv.items.get(kind=InvoiceItem.Kind.PRORATION).total_cents
    assert -9990 < credit < -3000
    assert inv.total_cents == 26990 + credit


def test_descer_de_plano_fica_agendado_para_o_fim_do_periodo(org, active_essencial):
    assert service.change_plan(org, plan("gratis"), "monthly") is None
    sub = sub_of(org)
    assert sub.plan.code == "essencial" and sub.scheduled_plan.code == "gratis"

    service.renew(sub, sub.next_billing_date)
    sub = sub_of(org)
    assert sub.plan.code == "gratis" and sub.next_billing_date is None
    assert wallet.get_wallet(org).credit_limit_cents == 0


def test_desistir_da_descida_agendada(org, active_essencial):
    service.change_plan(org, plan("gratis"), "monthly")
    assert service.change_plan(org, plan("essencial"), "monthly") is None
    assert sub_of(org).scheduled_plan is None


# --- pós-pago e fechamento mensal --------------------------------------------------------------


def test_pos_pago_respeita_limite(org, active_essencial):
    wallet.capture(wallet.reserve(org, 49000, "RENAVE", ref_type="t", ref_id="1"))
    assert wallet.get_wallet(org).balance_cents == -49000
    with pytest.raises(InsufficientBalance):
        wallet.reserve(org, 3000, "RENAVE", ref_type="t", ref_id="2")


def test_fechamento_fatura_consumo_e_mensalidade(org, active_essencial):
    for i in range(3):
        wallet.capture(wallet.reserve(org, 3000, "RENAVE", ref_type="t", ref_id=str(i)))
    sub = sub_of(org)
    inv = service.renew(sub, sub.next_billing_date)
    kinds = dict(inv.items.values_list("kind", "total_cents"))
    assert kinds == {InvoiceItem.Kind.USAGE: 9000, InvoiceItem.Kind.PLAN: 9990}
    assert inv.total_cents == 18990
    assert wallet.get_wallet(org).balance_cents == 0
    assert LedgerEntry.objects.filter(kind=LedgerEntry.Kind.INVOICED, amount_cents=9000).exists()

    assert service.renew(sub_of(org), sub.next_billing_date) is None  # idempotente no mesmo dia
    new = sub_of(org)
    assert new.next_billing_date == service.add_months(sub.next_billing_date, 1)
    assert new.paid_through == service.add_months(sub.paid_through, 1)


def test_plano_anual_cobra_mensalidade_uma_vez_e_consumo_todo_mes(org):
    entitlements.get_subscription(org)
    pay(service.change_plan(org, plan("essencial"), "annual"))
    sub = sub_of(org)
    wallet.capture(wallet.reserve(org, 3000, "RENAVE", ref_type="t", ref_id="1"))
    inv = service.renew(sub, sub.next_billing_date)
    assert list(inv.items.values_list("kind", flat=True)) == [InvoiceItem.Kind.USAGE]
    assert service.renew(sub_of(org), sub_of(org).next_billing_date) is None  # mês sem consumo, sem fatura


# --- inadimplência ----------------------------------------------------------------------------


def test_atraso_suspende_e_pagamento_reativa(org, active_essencial):
    wallet.capture(wallet.reserve(org, 6000, "RENAVE", ref_type="t", ref_id="1"))
    sub = sub_of(org)
    inv = service.renew(sub, sub.next_billing_date)

    service.enforce_overdue(inv.due_date + timedelta(days=1))
    assert sub_of(org).status == Subscription.Status.PAST_DUE

    wallet.capture(wallet.reserve(org, 3000, "RENAVE", ref_type="t", ref_id="2"))
    service.enforce_overdue(inv.due_date + timedelta(days=7))
    sub = sub_of(org)
    assert sub.status == Subscription.Status.SUSPENDED
    assert not entitlements.has_feature(org, "fiscal")
    with pytest.raises(InsufficientBalance):  # limite congelado no consumo atual
        wallet.reserve(org, 3000, "RENAVE", ref_type="t", ref_id="3")

    pay(inv)
    sub = sub_of(org)
    assert sub.status == Subscription.Status.ACTIVE
    assert wallet.get_wallet(org).credit_limit_cents == 50000


def test_fatura_de_troca_nao_paga_expira(org):
    entitlements.get_subscription(org)
    inv = service.change_plan(org, plan("essencial"), "monthly")
    service.enforce_overdue(inv.due_date + timedelta(days=1))
    inv.refresh_from_db()
    assert inv.status == Invoice.Status.CANCELED
    assert sub_of(org).status == Subscription.Status.TRIALING


# --- limites do plano -------------------------------------------------------------------------


def test_gratis_nao_convida_usuarios(api, org):
    entitlements.get_subscription(org)
    service.change_plan(org, plan("gratis"), "monthly")
    r = api.post("/api/organizations/invitations", {"email": "novo@loja.com.br", "role": "operator"}, format="json")
    assert r.status_code == 402 and r.json()["error"]["code"] == "plan_limit"


# --- webhook ------------------------------------------------------------------------------------


def _event(inv, event="PAYMENT_RECEIVED", value=None, eid="evt_1"):
    return {
        "id": eid,
        "event": event,
        "payment": {"id": "pay_1", "externalReference": f"invoice:{inv.public_id}", "value": value or inv.total_cents / 100},
    }


def test_webhook_exige_token(org):
    entitlements.get_subscription(org)
    inv = service.change_plan(org, plan("essencial"), "monthly")
    c = APIClient()
    assert c.post(WEBHOOK, _event(inv), format="json", HTTP_ASAAS_ACCESS_TOKEN="errado").status_code == 401
    assert c.post(WEBHOOK, _event(inv), format="json").status_code == 401


def test_webhook_pagamento_ativa_plano_e_deduplica(org):
    entitlements.get_subscription(org)
    inv = service.change_plan(org, plan("essencial"), "monthly")
    c = APIClient()
    for _ in range(2):
        r = c.post(WEBHOOK, _event(inv), format="json", HTTP_ASAAS_ACCESS_TOKEN="asaas_whtoken")
        assert r.status_code == 200
    assert sub_of(org).plan.code == "essencial"


def test_webhook_valor_menor_nao_ativa(org):
    entitlements.get_subscription(org)
    inv = service.change_plan(org, plan("essencial"), "monthly")
    APIClient().post(WEBHOOK, _event(inv, value=1.0), format="json", HTTP_ASAAS_ACCESS_TOKEN="asaas_whtoken")
    inv.refresh_from_db()
    assert inv.status == Invoice.Status.OPEN


# --- backoffice ---------------------------------------------------------------------------------


@pytest.fixture
def staff(db):
    from accounts.models import User

    return User.objects.create_user(email="equipe@renave.test", password="Senha-Admin-12345", full_name="Equipe", is_staff=True)


def test_backoffice_concede_plano_e_confirma_fatura(staff, org):
    entitlements.get_subscription(org)
    c, _ = login(staff)
    sub = sub_of(org)
    r = c.post(
        f"/api/admin/subscriptions/{sub.public_id}/grant-plan", {"plan": "premium", "reason": "Cortesia de lançamento"}, format="json"
    )
    assert r.status_code == 200, r.json()
    assert sub_of(org).plan.code == "premium"

    inv = service.change_plan(org, plan("premium"), "annual")
    r = c.post(f"/api/admin/invoices/{inv.public_id}/mark-paid")
    assert r.status_code == 200 and r.json()["status"] == "paid"
    assert sub_of(org).cycle == "annual"
    assert c.get("/api/admin/plans").status_code == 200


def test_add_months_fim_de_mes():
    assert service.add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)
    assert service.add_months(date(2026, 12, 15), 1) == date(2027, 1, 15)


# --- gateway Asaas -------------------------------------------------------------------------------


@pytest.fixture
def asaas_on(settings):
    settings.ASAAS = {**settings.ASAAS, "API_KEY": "aact_test", "BASE_URL": "https://asaas.test/v3"}


def test_fatura_vira_cobranca_no_asaas(org, asaas_on, django_capture_on_commit_callbacks):
    import respx
    from httpx import Response

    with respx.mock(assert_all_called=True) as mock:
        cust = mock.post("https://asaas.test/v3/customers").mock(return_value=Response(200, json={"id": "cus_1"}))
        pay_route = mock.post("https://asaas.test/v3/payments").mock(
            return_value=Response(200, json={"id": "pay_9", "invoiceUrl": "https://asaas.test/i/pay_9"})
        )
        entitlements.get_subscription(org)
        with django_capture_on_commit_callbacks(execute=True):
            inv = service.change_plan(org, plan("essencial"), "monthly")
    inv.refresh_from_db()
    assert inv.provider_payment_id == "pay_9" and inv.payment_url == "https://asaas.test/i/pay_9"
    import json

    body = json.loads(pay_route.calls[0].request.content)
    assert body["value"] == 99.9 and body["billingType"] == "UNDEFINED" and body["externalReference"] == f"invoice:{inv.public_id}"
    assert cust.calls[0].request.headers["access_token"] == "aact_test"


def test_recarga_pix_pelo_asaas(api, org, asaas_on):
    import respx
    from httpx import Response

    with respx.mock() as mock:
        mock.post("https://asaas.test/v3/customers").mock(return_value=Response(200, json={"id": "cus_1"}))
        mock.post("https://asaas.test/v3/payments").mock(return_value=Response(200, json={"id": "pay_7"}))
        mock.get("https://asaas.test/v3/payments/pay_7/pixQrCode").mock(
            return_value=Response(200, json={"payload": "000201PIX", "encodedImage": "iVBOR", "expirationDate": "2026-11-24 23:59:59"})
        )
        r = api.post("/api/wallet/topups", {"amount_cents": 5000}, format="json")
    assert r.status_code == 201, r.json()
    assert r.json()["pix_copy_paste"] == "000201PIX" and r.json()["provider"] == "asaas"

    from wallet.models import TopUp

    topup = TopUp.objects.get()
    event = {
        "id": "evt_t",
        "event": "PAYMENT_RECEIVED",
        "payment": {"id": "pay_7", "externalReference": f"topup:{topup.public_id}", "value": 50.0},
    }
    APIClient().post(WEBHOOK, event, format="json", HTTP_ASAAS_ACCESS_TOKEN="asaas_whtoken")
    assert wallet.get_wallet(org).balance_cents == 5000
