"""Cliente BusCars (consultas). Docs: https://buscars.com.br/docs"""

import hashlib
import hmac
from datetime import UTC, datetime

from django.conf import settings
from django.core.cache import cache

from .http import BaseClient, ProviderError, ProviderResponse

CATALOG_CACHE_KEY = "buscars:catalogo"
WEBHOOK_TOLERANCE_SECONDS = 300


class BusCarsClient(BaseClient):
    provider = "buscars"

    def __init__(self, organization=None):
        super().__init__(organization)
        cfg = settings.BUSCARS
        self.base_url = cfg["BASE_URL"]
        self.timeout = cfg["TIMEOUT"]
        self._api_key = cfg["API_KEY"]

    def default_headers(self):
        if not self._api_key:
            raise ProviderError("Integração de consultas não configurada.")
        return {"Accept": "application/json", "x-api-key": self._api_key}

    def consultar(self, sku: str, valor: str, *, idempotency_key: str, extra: dict | None = None) -> ProviderResponse:
        body = {"sku": sku, "valor": valor, **(extra or {})}
        return self.request("POST", "/v1/consulta", json=body, headers={"idempotency-key": idempotency_key})

    def criar_assincrona(self, tipo: str, sku: str, valor: str, *, idempotency_key: str) -> ProviderResponse:
        return self.request(
            "POST", "/v1/consultas", json={"tipo": tipo, "sku": sku, "valor": valor}, headers={"idempotency-key": idempotency_key}
        )

    def status(self, consulta_id: str) -> ProviderResponse:
        return self.request("GET", f"/v1/consultas/{consulta_id}/status")

    def catalogo(self, *, use_cache=True) -> list[dict]:
        if use_cache and (cached := cache.get(CATALOG_CACHE_KEY)) is not None:
            return cached
        resp = self.request("GET", "/v1/catalogo", log_response=False)
        if not resp.ok:
            raise ProviderError("Não foi possível carregar o catálogo.", status_code=resp.status_code)
        data = resp.data.get("data", resp.data) if isinstance(resp.data, dict) else resp.data
        items = data.get("produtos", data) if isinstance(data, dict) else data
        cache.set(CATALOG_CACHE_KEY, items, 600)
        return items

    def saldo(self) -> ProviderResponse:
        return self.request("GET", "/v1/saldo")


def verify_webhook(
    raw_body: bytes, timestamp: str, signature_header: str, *, secret: str | None = None, now: datetime | None = None
) -> bool:
    """HMAC SHA-256 de `timestamp + "." + corpo_cru`, comparação em tempo constante e janela de 5 min."""
    secret = secret if secret is not None else settings.BUSCARS["WEBHOOK_SECRET"]
    if not (secret and timestamp and signature_header):
        return False
    try:
        sent_at = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError:
        return False
    now = now or datetime.now(UTC)
    if abs((now - sent_at).total_seconds()) > WEBHOOK_TOLERANCE_SECONDS:
        return False
    expected = "sha256=" + hmac.new(secret.encode(), timestamp.encode() + b"." + raw_body, hashlib.sha256).hexdigest()
    return any(hmac.compare_digest(expected, candidate.strip()) for candidate in signature_header.split(","))
