import pytest
from rest_framework.test import APIClient

from accounts.models import User
from consultas.models import Product
from wallet import service as wallet
from wallet.models import TopUp

PWD = "Senha-Admin-12345"


@pytest.fixture
def staff(db):
    return User.objects.create_user(email="equipe@renave.test", password=PWD, full_name="Equipe", is_staff=True)


@pytest.fixture
def superadmin(db):
    return User.objects.create_user(email="root@renave.test", password=PWD, full_name="Root", is_staff=True, is_superuser=True)


def login(user):
    c = APIClient()
    r = c.post("/api/admin/auth/login", {"email": user.email, "password": PWD}, format="json")
    assert r.status_code == 200, r.json()
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {r.json()['access']}")
    return c, r


def test_login_admin_cookie_proprio_e_refresh(staff):
    c, r = login(staff)
    assert "rd_admin_refresh" in r.cookies and r.cookies["rd_admin_refresh"]["path"] == "/api/admin/auth/"
    assert "rd_refresh" not in r.cookies
    r2 = c.post("/api/admin/auth/refresh")
    assert r2.status_code == 200 and r2.json()["user"]["email"] == staff.email
    assert c.get("/api/admin/stats").status_code == 200


def test_lojista_nao_entra_no_admin(user):
    r = APIClient().post("/api/admin/auth/login", {"email": user.email, "password": "Senha-Forte-123"}, format="json")
    assert r.status_code == 401


def test_token_de_lojista_nao_acessa_api_admin(staff):
    """Mesmo um usuário da equipe precisa do token de admin (scope)."""
    c = APIClient()
    r = c.post("/api/auth/login", {"email": staff.email, "password": PWD}, format="json")
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {r.json()['access']}")
    assert c.get("/api/admin/stats").status_code == 403


def test_metricas(staff, funded):
    c, _ = login(staff)
    body = c.get("/api/admin/stats?days=7").json()
    assert body["organizations"]["total"] == 1 and len(body["series"]) == 8
    assert body["wallets_balance_cents"] == 100_00


def test_ajuste_de_saldo_e_auditoria(staff, funded):
    c, _ = login(staff)
    url = f"/api/admin/organizations/{funded.public_id}/wallet-adjust"
    assert c.post(url, {"amount_cents": 500, "reason": "x"}, format="json").status_code == 400
    assert c.post(url, {"amount_cents": -2500, "reason": "Estorno de cobrança duplicada"}, format="json").status_code == 201
    assert wallet.get_wallet(funded).balance_cents == 75_00
    assert c.post(url, {"amount_cents": -999_999, "reason": "Débito maior que o saldo"}, format="json").status_code == 402
    detail = c.get(f"/api/admin/organizations/{funded.public_id}").json()
    assert detail["balance_cents"] == 75_00 and detail["members"][0]["role"] == "owner"


def test_confirmar_recarga(staff, org):
    t = TopUp.objects.create(organization=org, amount_cents=10_000)
    c, _ = login(staff)
    assert c.get("/api/admin/topups?status=pending").json()["count"] == 1
    assert c.post(f"/api/admin/topups/{t.public_id}/confirm").json()["status"] == "paid"
    assert wallet.get_wallet(org).balance_cents == 10_000


def test_produtos_crud(staff):
    c, _ = login(staff)
    r = c.post(
        "/api/admin/products", {"code": "teste", "sku": "sku-x", "name": "Teste", "price_cents": 990, "cost_cents": 300}, format="json"
    )
    assert r.status_code == 201 and r.json()["margin_cents"] == 690
    pid = r.json()["id"]
    assert c.patch(f"/api/admin/products/{pid}", {"is_active": True}, format="json").json()["is_active"] is True
    assert Product.objects.get(code="teste").is_active


def test_equipe_so_superadmin(staff, superadmin):
    c, _ = login(staff)
    payload = {"email": "novo@renave.test", "full_name": "Novo", "password": "Outra-Senha-987654"}
    assert c.post("/api/admin/users/staff", payload, format="json").status_code == 403
    c2, _ = login(superadmin)
    r = c2.post("/api/admin/users/staff", payload, format="json")
    assert r.status_code == 201 and r.json()["is_staff"]


def test_busca_empresas(staff, org):
    c, _ = login(staff)
    assert c.get("/api/admin/organizations?search=11.222.333").json()["count"] == 1
    assert c.get("/api/admin/organizations?search=inexistente").json()["count"] == 0


def test_login_registra_ultimo_acesso(staff):
    assert staff.last_login is None
    login(staff)
    staff.refresh_from_db()
    assert staff.last_login is not None
