"""Tabela FIPE pela API pública da Parallelum (v2). Token opcional aumenta o limite diário.

Docs: https://deividfortuna.github.io/fipe/v2
"""

from django.conf import settings
from django.core.cache import cache

from .http import BaseClient, ProviderError

TYPES = {"carro": "cars", "moto": "motorcycles", "caminhao": "trucks"}
CACHE_TTL = 60 * 60 * 24


def parse_price(text: str) -> int | None:
    """'R$ 52.341,00' -> 5234100"""
    digits = "".join(ch for ch in str(text or "") if ch.isdigit())
    return int(digits) if digits else None


class FipeClient(BaseClient):
    provider = "fipe"

    def __init__(self, organization=None):
        super().__init__(organization)
        cfg = settings.FIPE_API
        self.base_url = cfg["BASE_URL"]
        self.timeout = cfg["TIMEOUT"]
        self._token = cfg["TOKEN"]

    def default_headers(self):
        headers = {"Accept": "application/json"}
        if self._token:
            headers["X-Subscription-Token"] = self._token
        return headers

    def _get(self, path: str):
        key = f"fipe:{path}"
        if (hit := cache.get(key)) is not None:
            return hit
        resp = self.request("GET", path)
        if not resp.ok:
            raise ProviderError("A tabela FIPE não respondeu. Tente novamente.", status_code=resp.status_code, retryable=True)
        cache.set(key, resp.data, CACHE_TTL)
        return resp.data

    def brands(self, kind: str):
        return self._get(f"/{TYPES[kind]}/brands")

    def models(self, kind: str, brand: str):
        return self._get(f"/{TYPES[kind]}/brands/{brand}/models")

    def years(self, kind: str, brand: str, model: str):
        return self._get(f"/{TYPES[kind]}/brands/{brand}/models/{model}/years")

    def price(self, kind: str, brand: str, model: str, year: str) -> dict:
        return self._normalize(self._get(f"/{TYPES[kind]}/brands/{brand}/models/{model}/years/{year}"))

    def years_by_code(self, kind: str, code: str):
        return self._get(f"/{TYPES[kind]}/{code}/years")

    def price_by_code(self, kind: str, code: str, year: str) -> dict:
        return self._normalize(self._get(f"/{TYPES[kind]}/{code}/years/{year}"))

    @staticmethod
    def _normalize(data: dict) -> dict:
        data = data or {}
        return {
            "code": data.get("codeFipe", ""),
            "brand": data.get("brand", ""),
            "model": data.get("model", ""),
            "model_year": data.get("modelYear"),
            "fuel": data.get("fuel", ""),
            "price_cents": parse_price(data.get("price")),
            "reference": data.get("referenceMonth", ""),
        }
