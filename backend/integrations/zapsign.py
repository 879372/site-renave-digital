"""ZapSign: criação de documento para assinatura eletrônica a partir de texto.

Docs: https://docs.zapsign.com.br — POST /api/v1/docs/ com `markdown_text` e `signers`.
Autenticação: Authorization: Bearer <token>.
"""

from django.conf import settings

from .http import BaseClient, ProviderError


class ZapSignClient(BaseClient):
    provider = "zapsign"

    def __init__(self, organization=None):
        super().__init__(organization)
        cfg = settings.ZAPSIGN
        self.base_url = cfg["BASE_URL"]
        self.timeout = cfg["TIMEOUT"]
        self._token = cfg["TOKEN"]

    @property
    def configured(self) -> bool:
        return bool(self._token)

    def default_headers(self):
        return {"Accept": "application/json", "Content-Type": "application/json", "Authorization": f"Bearer {self._token}"}

    def create_document(self, *, name: str, text: str, signers: list[dict], external_id: str) -> dict:
        body = {
            "name": name[:255],
            "markdown_text": text,
            "lang": "pt-br",
            "external_id": external_id,
            "signers": [
                {
                    "name": s["name"][:150],
                    "email": s.get("email", ""),
                    "phone_number": s.get("phone", ""),
                    "send_automatic_email": bool(s.get("email")),
                }
                for s in signers
            ],
        }
        resp = self.request("POST", "/api/v1/docs/", json=body)
        if not resp.ok or not isinstance(resp.data, dict):
            raise ProviderError(self.error_message(resp.data) or "Falha ao enviar para assinatura.", status_code=resp.status_code)
        return resp.data
