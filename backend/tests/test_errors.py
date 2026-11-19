import pytest
from django.test import override_settings

from core import errors


@override_settings(DEBUG=False)
def test_unknown_route_returns_json_404(client):
    response = client.get("/api/rota-que-nao-existe")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_server_error_handler_is_json(rf):
    response = errors.server_error(rf.get("/api/x"))
    assert response.status_code == 500
    assert response["Content-Type"] == "application/json"
    assert b"server_error" in response.content


pytestmark = pytest.mark.django_db
