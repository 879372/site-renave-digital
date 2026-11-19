"""Cliente Carven (comunicação de venda + RENAVE). Docs: https://hml.carven.com.br/docs"""

import threading

from django.conf import settings
from django.core.cache import cache

from .http import BaseClient, ProviderError, ProviderResponse

TOKEN_CACHE_KEY = "carven:token"
_lock = threading.Lock()


class CarvenClient(BaseClient):
    provider = "carven"

    def __init__(self, organization=None):
        super().__init__(organization)
        cfg = settings.CARVEN
        self.base_url = cfg["BASE_URL"]
        self.timeout = cfg["TIMEOUT"]
        self._client_id = cfg["CLIENT_ID"]
        self._client_secret = cfg["CLIENT_SECRET"]

    # --- autenticação --------------------------------------------------------------

    def _login(self) -> str:
        if not (self._client_id and self._client_secret):
            raise ProviderError("Integração RENAVE não configurada.")
        resp = super().request(
            "POST", "/api/auth/login", json={"client_id": self._client_id, "client_secret": self._client_secret}, log_response=False
        )
        if resp.status_code != 200 or not isinstance(resp.data, dict) or not resp.data.get("access_token"):
            raise ProviderError("Falha na autenticação da integração RENAVE.", status_code=resp.status_code)
        token = resp.data["access_token"]
        ttl = max(int(resp.data.get("expires_after", 3600)) - 120, 60)
        cache.set(TOKEN_CACHE_KEY, token, ttl)
        return token

    def _token(self, force=False) -> str:
        if not force and (token := cache.get(TOKEN_CACHE_KEY)):
            return token
        with _lock:
            if not force and (token := cache.get(TOKEN_CACHE_KEY)):
                return token
            return self._login()

    def request(self, method, path, *, retry_auth=True, **kwargs) -> ProviderResponse:
        headers = {"Authorization": f"Bearer {self._token()}", "Cache-Control": "no-cache", **kwargs.pop("headers", {})}
        resp = super().request(method, path, headers=headers, **kwargs)
        if resp.status_code == 401 and retry_auth:
            cache.delete(TOKEN_CACHE_KEY)
            return self.request(method, path, retry_auth=False, headers=kwargs.pop("headers", {}), **kwargs)
        return resp

    def _extract_error(self, payload) -> str:
        if isinstance(payload, dict):
            if payload.get("validacao"):
                return "; ".join(map(str, payload["validacao"]))
            if isinstance(payload.get("errors"), dict):
                return "; ".join(msg for msgs in payload["errors"].values() for msg in msgs)
        return super()._extract_error(payload)

    # --- comunicação de venda ------------------------------------------------------

    def comunicacao_inserir(self, body: dict) -> ProviderResponse:
        return self.request("POST", "/api/comunicacao-venda/inserir", json=body)

    def comunicacao_alterar(self, protocolo: str, body: dict) -> ProviderResponse:
        return self.request("PUT", f"/api/comunicacao-venda/{protocolo}", json=body)

    def comunicacao_detalhes(self, protocolo: str) -> ProviderResponse:
        return self.request("GET", f"/api/comunicacao-venda/{protocolo}")

    def comunicacao_transmitir(self, protocolo: str) -> ProviderResponse:
        return self.request("POST", f"/api/comunicacao-venda/transmitir/enviar/{protocolo}")

    def comunicacao_cancelar(self, protocolo: str, body: dict) -> ProviderResponse:
        return self.request("POST", f"/api/comunicacao-venda/transmitir/cancelar/{protocolo}", json=body)

    def comunicacao_motivos_cancelamento(self, protocolo: str) -> ProviderResponse:
        return self.request("GET", f"/api/comunicacao-venda/motivos-cancelamento/{protocolo}")

    def comunicacao_comprovante(self, protocolo: str) -> ProviderResponse:
        return self.request("GET", f"/api/comunicacao-venda/comprovante/{protocolo}", log_response=False)

    def comunicacao_historico(self, protocolo: str) -> ProviderResponse:
        return self.request("GET", f"/api/comunicacao-venda/{protocolo}/historico")

    # --- RENAVE ---------------------------------------------------------------------

    def renave_salvar_certificado(self, cpf_cnpj: str, nome: str, pfx: bytes, senha: str) -> ProviderResponse:
        return self.request(
            "POST",
            "/api/renave/salvar-certificado-renave",
            data={"cpf_cnpj": cpf_cnpj, "nome_cliente": nome[:255], "chave-certificado": senha},
            files={"certificado": ("certificado.pfx", pfx, "application/x-pkcs12")},
        )

    def renave_cliente_autenticado(self, cpf_cnpj: str) -> ProviderResponse:
        return self.request("GET", "/api/renave/usado/cliente-autenticado", params={"cpf_cnpj": cpf_cnpj})

    def renave_aptidao(self, body: dict) -> ProviderResponse:
        return self.request("POST", "/api/renave/consultar-aptidao", json=body)

    def renave_entrada(self, body: dict) -> ProviderResponse:
        return self.request("POST", "/api/renave/usado/estoque/entrada-estoque", json=body)

    def renave_cancelar_entrada(self, id_estoque: int, cpf_cnpj: str) -> ProviderResponse:
        return self.request("DELETE", f"/api/renave/usado/estoque/cancelar-estoque/{id_estoque}", params={"cpf_cnpj": cpf_cnpj})

    def renave_atualizar_estoque(self, cpf_cnpj: str, mes_referencia: str | None = None) -> ProviderResponse:
        body = {"cpf_cnpj": cpf_cnpj}
        if mes_referencia:
            body["mes_referencia"] = mes_referencia
        return self.request("POST", "/api/renave/usado/estoque/atualizar", json=body)

    def renave_listar_estoque(self, **params) -> ProviderResponse:
        return self.request("GET", "/api/renave/usado/estoque", params={k: v for k, v in params.items() if v not in (None, "")})

    def renave_detalhes(self, id_estoque: int, cpf_cnpj: str) -> ProviderResponse:
        return self.request("GET", f"/api/renave/detalhes/{id_estoque}", params={"cpf_cnpj": cpf_cnpj})

    def renave_restricoes(self, id_estoque: int, cpf_cnpj: str) -> ProviderResponse:
        return self.request("GET", f"/api/renave/consultar-restricao/{id_estoque}", params={"cpf_cnpj": cpf_cnpj})

    def renave_documento(self, kind: str, id_estoque: int, cpf_cnpj: str) -> ProviderResponse:
        paths = {
            "termo_entrada": "obter-termo-entrada",
            "termo_saida": "obter-termo-saida",
            "crlve": "obter-crlve",
            "atpv": "obter-atpv",
        }
        return self.request(
            "GET", f"/api/renave/usado/estoque/{paths[kind]}/{id_estoque}", params={"cpf_cnpj": cpf_cnpj}, log_response=False
        )

    def renave_enviar_nota(self, id_estoque: int, body: dict) -> ProviderResponse:
        return self.request("POST", f"/api/renave/usado/estoque/enviar-nota-fiscal/{id_estoque}", json=body)

    def renave_saida(self, id_estoque: int, body: dict) -> ProviderResponse:
        return self.request("POST", f"/api/renave/usado/estoque/saida/{id_estoque}", json=body)

    def renave_cancelar_saida(self, id_estoque: int, cpf_cnpj: str) -> ProviderResponse:
        return self.request("POST", f"/api/renave/usado/estoque/cancelar-saida-estoque/{id_estoque}", json={"cpf_cnpj": cpf_cnpj})

    def renave_enviar_atpv_assinada(self, body: dict) -> ProviderResponse:
        return self.request("POST", "/api/renave/usado/estoque/enviar-atpv-assinada", json=body)
