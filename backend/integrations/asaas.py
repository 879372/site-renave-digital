"""Cliente Asaas (cobranças Pix, boleto e cartão). Docs: https://docs.asaas.com/reference

Autenticação pelo cabeçalho `access_token`. Sandbox: https://api-sandbox.asaas.com/v3
"""

from django.conf import settings

from .http import BaseClient, ProviderError, ProviderResponse


class AsaasClient(BaseClient):
    provider = "asaas"

    def __init__(self, organization=None):
        super().__init__(organization)
        cfg = settings.ASAAS
        self.base_url = cfg["BASE_URL"]
        self.timeout = cfg["TIMEOUT"]
        self._api_key = cfg["API_KEY"]

    def default_headers(self) -> dict[str, str]:
        if not self._api_key:
            raise ProviderError("Gateway de pagamento não configurado.")
        return {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "RevendaDigital/1.0",
            "access_token": self._api_key,
        }

    def _extract_error(self, payload) -> str:
        if isinstance(payload, dict) and isinstance(payload.get("errors"), list):
            return "; ".join(str(e.get("description", "")) for e in payload["errors"] if isinstance(e, dict)) or "Erro do gateway."
        return super()._extract_error(payload)

    def _check(self, resp: ProviderResponse) -> dict:
        if not resp.ok or not isinstance(resp.data, dict):
            raise ProviderError(self.error_message(resp.data), status_code=resp.status_code, retryable=resp.status_code >= 500)
        return resp.data

    def create_customer(self, *, name: str, cpf_cnpj: str, email: str = "", phone: str = "", external_reference: str = "") -> dict:
        body = {"name": name[:100], "cpfCnpj": cpf_cnpj, "externalReference": external_reference, "notificationDisabled": True}
        if email:
            body["email"] = email
        if phone:
            body["mobilePhone"] = phone
        return self._check(self.request("POST", "/customers", json=body))

    def create_payment(
        self, *, customer: str, value_cents: int, due_date: str, description: str, external_reference: str, billing_type: str = "UNDEFINED"
    ) -> dict:
        body = {
            "customer": customer,
            "billingType": billing_type,
            "value": round(value_cents / 100, 2),
            "dueDate": due_date,
            "description": description[:500],
            "externalReference": external_reference,
        }
        return self._check(self.request("POST", "/payments", json=body))

    def pix_qr_code(self, payment_id: str) -> dict:
        return self._check(self.request("GET", f"/payments/{payment_id}/pixQrCode"))

    def delete_payment(self, payment_id: str) -> dict:
        return self._check(self.request("DELETE", f"/payments/{payment_id}"))
