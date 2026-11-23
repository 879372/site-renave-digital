"""Cliente Geranet (NF-e). Docs: https://nfe.geranet.net/documentacao/introducao"""

from django.conf import settings

from .http import BaseClient, ProviderError, ProviderResponse


class GeranetClient(BaseClient):
    provider = "geranet"

    def __init__(self, organization=None):
        super().__init__(organization)
        cfg = settings.GERANET
        self.base_url = cfg["BASE_URL"]
        self.timeout = cfg["TIMEOUT"]
        self.ambiente = cfg["AMBIENTE"]
        self._api_key = cfg["API_KEY"]

    def default_headers(self):
        if not self._api_key:
            raise ProviderError("Integração fiscal não configurada.")
        return {"Accept": "application/json", "Authorization": f"Bearer {self._api_key}"}

    def _envelope(self, acao: str, pfx: bytes, senha: str, uf: str, **extra) -> dict:
        return {
            "acao": acao,
            "modeloDocumento": "nfe",
            "nomeSistema": "REVENDA DIGITAL",
            "certificadoDigital": pfx.hex(),
            "senhaCertificadoDigital": senha,
            "ambiente": self.ambiente,
            "modelo": "55",
            "ufEmitente": uf,
            **extra,
        }

    def emitir(self, *, pfx: bytes, senha: str, uf: str, nfe: dict) -> ProviderResponse:
        return self.request("POST", "/nfe/emitir", json=self._envelope("emitir", pfx, senha, uf, nfe=nfe), log_response=False)

    def consultar(self, *, pfx: bytes, senha: str, uf: str, chave: str) -> ProviderResponse:
        return self.request("POST", "/nfe/consultar", json=self._envelope("consultar", pfx, senha, uf, chave=chave), log_response=False)

    def cancelar(self, *, pfx: bytes, senha: str, uf: str, chave: str, protocolo: str, justificativa: str) -> ProviderResponse:
        body = self._envelope("cancelar", pfx, senha, uf, chave=chave, protocolo=protocolo, justificativa=justificativa)
        return self.request("POST", "/nfe/cancelar", json=body, log_response=False)

    def carta_correcao(self, *, pfx: bytes, senha: str, uf: str, chave: str, correcao: str, sequencia: int) -> ProviderResponse:
        body = self._envelope("cartaCorrecao", pfx, senha, uf, chave=chave, numeroCorrecao=str(sequencia), textoCorrecao=correcao)
        return self.request("POST", "/nfe/carta-correcao", json=body, log_response=False)

    def consultar_cnpj(self, cnpj: str) -> ProviderResponse:
        return self.request("POST", "/cnpj/consultar", json={"cnpj": cnpj})
