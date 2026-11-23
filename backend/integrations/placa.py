"""Consulta de placa (API PLACAS / wdapi2): marca, modelo, ano, cor e código FIPE.

Formato: GET {BASE_URL}/consulta/{placa}/{token}. A resposta varia um pouco entre
planos do provedor, então a leitura é tolerante e só devolve campos conhecidos.
"""

from django.conf import settings

from .fipe import parse_price
from .http import BaseClient, ProviderError


def _first(data: dict, *keys):
    for key in keys:
        value = data.get(key)
        if value not in (None, "", "*****"):
            return value
    return ""


def _int(value):
    try:
        return int(str(value)[:4])
    except (TypeError, ValueError):
        return None


class PlacaClient(BaseClient):
    provider = "placa"

    def __init__(self, organization=None):
        super().__init__(organization)
        cfg = settings.PLACA_API
        self.base_url = cfg["BASE_URL"]
        self.timeout = cfg["TIMEOUT"]
        self._token = cfg["TOKEN"]

    @property
    def configured(self) -> bool:
        return bool(self._token)

    def _log_body(self, body):  # nunca grava o token (vai na URL)
        return None

    def lookup(self, placa: str) -> dict:
        if not self._token:
            raise ProviderError("Consulta de placa não configurada.")
        # O token vai na URL: o log de integração grava o caminho sem ele.
        resp = self.request("GET", f"/consulta/{placa}/{self._token}", log_path=f"/consulta/{placa}/***")
        if resp.status_code == 404 or (isinstance(resp.data, dict) and resp.data.get("mensagemRetorno", "").lower().startswith("placa")):
            raise ProviderError("Placa não encontrada.", status_code=404)
        if not resp.ok or not isinstance(resp.data, dict):
            raise ProviderError("A consulta de placa não respondeu. Tente novamente.", status_code=resp.status_code, retryable=True)
        return self.normalize(resp.data)

    @staticmethod
    def normalize(d: dict) -> dict:
        fipe = {}
        fipe_list = (d.get("fipe") or {}).get("dados") if isinstance(d.get("fipe"), dict) else None
        if fipe_list:
            best = max(fipe_list, key=lambda x: x.get("score", 0) or 0)
            fipe = {
                "code": best.get("codigo_fipe", ""),
                "price_cents": parse_price(best.get("texto_valor")),
                "model": best.get("texto_modelo", ""),
                "reference": best.get("mes_referencia", ""),
            }
        return {
            "marca": str(_first(d, "MARCA", "marca")).title(),
            "modelo": str(_first(d, "MODELO", "modelo", "SUBMODELO")).upper(),
            "versao": str(_first(d, "VERSAO", "versao", "SUBMODELO")),
            "ano_fabricacao": _int(_first(d, "ano", "anoFabricacao")),
            "ano_modelo": _int(_first(d, "anoModelo", "ano_modelo")),
            "cor": str(_first(d, "cor", "COR")).title(),
            "combustivel": str((d.get("extra") or {}).get("combustivel", "") if isinstance(d.get("extra"), dict) else "").title(),
            "municipio": str(_first(d, "municipio")).title(),
            "uf": str(_first(d, "uf", "UF")).upper()[:2],
            "fipe": fipe,
        }
