"""Checkout InfinitePay: webhook é apenas aviso; pagamento sempre conferido na API."""

from urllib.parse import urlparse

from django.conf import settings

from .http import BaseClient, ProviderError


class InfinitePayClient(BaseClient):
    provider = "infinitepay"

    def __init__(self, organization=None):
        super().__init__(organization)
        self.base_url = settings.INFINITEPAY["BASE_URL"]
        self.timeout = settings.INFINITEPAY["TIMEOUT"]

    def default_headers(self):
        headers = {"Accept": "application/json", "Content-Type": "application/json"}
        if settings.INFINITEPAY["API_KEY"]:
            headers["X-Api-Key"] = settings.INFINITEPAY["API_KEY"]
        return headers

    def _log_body(self, body):
        # Não gravar dados pessoais, URL de retorno ou comprovante nos logs.
        return {"order_nsu": body.get("order_nsu")} if isinstance(body, dict) else None

    def post(self, path, payload):
        response = self.request("POST", path, json=payload, log_response=False)
        if not response.ok or not isinstance(response.data, dict):
            raise ProviderError(
                "Não foi possível consultar o checkout InfinitePay.",
                status_code=response.status_code,
                retryable=response.status_code in (408, 429) or response.status_code >= 500,
            )
        return response.data

    def create_link(self, checkout, description):
        cfg = settings.INFINITEPAY
        payload = {
            "handle": checkout.handle,
            "order_nsu": checkout.reference,
            "items": [{"quantity": 1, "price": checkout.amount_cents, "description": description[:120]}],
            "redirect_url": f"{cfg['FRONTEND_URL']}/pagamento/retorno?order_nsu={checkout.reference}",
            "webhook_url": f"{settings.PUBLIC_API_URL}/api/hooks/infinitepay",
        }
        if cfg["API_KEY"]:
            payload["options"] = {"single_payment": True, "payment_methods_enabled": ["credit_card", "pix"]}
        data = self.post("/links", payload)
        url = next((data.get(k) for k in ("url", "link", "checkout_url", "payment_url", "link_url") if data.get(k)), "")
        if not isinstance(url, str):
            raise ProviderError("Checkout retornou um link inválido.")
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.hostname != "infinitepay.io" and not (parsed.hostname or "").endswith(".infinitepay.io"):
            raise ProviderError("Checkout retornou um link inválido.")
        return url

    def payment_check(self, checkout, transaction_nsu, slug):
        return self.post(
            "/payment_check", {"handle": checkout.handle, "order_nsu": checkout.reference, "transaction_nsu": transaction_nsu, "slug": slug}
        )
