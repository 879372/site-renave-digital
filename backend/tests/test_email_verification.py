import re

import pytest
from django.core import mail
from rest_framework.test import APIClient

from accounts import verification
from accounts.models import User
from organizations.models import Membership, Role

from .test_lgpd_and_privacy import REGISTER

pytestmark = pytest.mark.django_db


def _code_from_outbox():
    return re.search(r"^\s+(\d{6})$", mail.outbox[-1].body, re.M).group(1)


@pytest.fixture
def registered(django_capture_on_commit_callbacks):
    """Cadastro pelo endpoint real: cria a conta não verificada e envia o código."""
    client = APIClient()
    with django_capture_on_commit_callbacks(execute=True):
        r = client.post("/api/auth/register", REGISTER, format="json")
    assert r.status_code == 201
    assert r.json()["user"]["email_verified"] is False
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {r.json()['access']}")
    user = User.objects.get(email=REGISTER["email"])
    org = Membership.objects.get(user=user, role=Role.OWNER).organization
    return client, user, org


def test_register_sends_code_and_blocks_business_endpoints(registered):
    client, _user, org = registered
    assert len(mail.outbox) == 1
    assert "código de verificação" in mail.outbox[0].subject
    assert re.search(r"/verificar-email\?codigo=\d{6}", mail.outbox[0].body)

    assert client.get("/api/auth/me").status_code == 200  # o app precisa saber quem é para mostrar a tela
    r = client.get("/api/wallet/", HTTP_X_ORGANIZATION=str(org.public_id))
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "email_unverified"
    r = client.get("/api/organizations/")
    assert r.json()["error"]["code"] == "email_unverified"


def test_correct_code_verifies_and_unlocks(registered):
    client, user, org = registered
    r = client.post("/api/auth/email/verify", {"code": _code_from_outbox()}, format="json")
    assert r.status_code == 204
    user.refresh_from_db()
    assert user.email_verified
    assert client.get("/api/wallet/", HTTP_X_ORGANIZATION=str(org.public_id)).status_code == 200


def test_wrong_code_counts_attempts_then_expires(registered):
    client, user, _org = registered
    right = _code_from_outbox()
    wrong = "000000" if right != "000000" else "111111"
    for _ in range(verification.MAX_ATTEMPTS - 1):
        r = client.post("/api/auth/email/verify", {"code": wrong}, format="json")
        assert r.status_code == 400
        assert "incorreto" in r.json()["error"]["fields"]["code"][0]
    r = client.post("/api/auth/email/verify", {"code": wrong}, format="json")
    assert "expirou" in r.json()["error"]["fields"]["code"][0]
    # Depois de esgotar as tentativas, nem o código certo vale mais.
    r = client.post("/api/auth/email/verify", {"code": right}, format="json")
    assert r.status_code == 400
    user.refresh_from_db()
    assert not user.email_verified


def test_resend_respects_cooldown(registered, django_capture_on_commit_callbacks, monkeypatch):
    client, _user, _org = registered
    r = client.post("/api/auth/email/send")
    assert r.json()["sent"] is False
    assert 0 < r.json()["retry_in"] <= verification.RESEND_COOLDOWN
    assert len(mail.outbox) == 1

    now = verification.time.time()
    monkeypatch.setattr(verification.time, "time", lambda: now + verification.RESEND_COOLDOWN + 1)
    with django_capture_on_commit_callbacks(execute=True):
        r = client.post("/api/auth/email/send")
    assert r.json()["sent"] is True
    assert len(mail.outbox) == 2
    old = re.search(r"^\s+(\d{6})$", mail.outbox[0].body, re.M).group(1)
    new = _code_from_outbox()
    if old != new:  # o código anterior deixa de valer
        assert client.post("/api/auth/email/verify", {"code": old}, format="json").status_code == 400
    assert client.post("/api/auth/email/verify", {"code": new}, format="json").status_code == 204


def test_code_is_not_stored_in_plain_text(registered):
    _client, user, _org = registered
    stored = verification.cache.get(verification._key(user))
    assert _code_from_outbox() not in str(stored)


def test_invalid_format_is_rejected(registered):
    client, _user, _org = registered
    r = client.post("/api/auth/email/verify", {"code": "12ab"}, format="json")
    assert r.status_code == 400
    assert r.json()["error"]["fields"]["code"] == ["Digite os 6 números do código."]


def test_verified_user_send_is_noop(api):
    r = api.post("/api/auth/email/send")
    assert r.json() == {"verified": True, "sent": False, "retry_in": 0}
    assert mail.outbox == []
