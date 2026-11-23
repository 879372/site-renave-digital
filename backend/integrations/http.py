"""Cliente HTTP base para provedores: timeouts, request-id, log mascarado."""

import logging
import time
from dataclasses import dataclass
from typing import Any

import httpx

from core.context import request_id_var
from core.masking import redact, scrub_provider

from .models import IntegrationCall

logger = logging.getLogger("integrations")


class ProviderError(Exception):
    """Falha de comunicação ou resposta inesperada do provedor."""

    def __init__(self, message: str, *, status_code: int | None = None, body: Any = None, retryable: bool = False):
        super().__init__(message)
        self.status_code = status_code
        self.body = body
        self.retryable = retryable


@dataclass
class ProviderResponse:
    status_code: int
    data: Any
    headers: httpx.Headers

    @property
    def ok(self) -> bool:
        return 200 <= self.status_code < 300


class BaseClient:
    provider: str = ""
    base_url: str = ""
    timeout: float = 30.0

    def __init__(self, organization=None):
        self.organization = organization

    def default_headers(self) -> dict[str, str]:
        return {"Accept": "application/json"}

    def _log_body(self, body):
        return redact(body) if isinstance(body, (dict, list)) else None

    def request(
        self,
        method: str,
        path: str,
        *,
        json=None,
        params=None,
        files=None,
        data=None,
        headers=None,
        timeout=None,
        log_response=True,
        log_path=None,
    ) -> ProviderResponse:
        url = f"{self.base_url.rstrip('/')}/{path.lstrip('/')}"
        all_headers = {**self.default_headers(), "X-Request-ID": request_id_var.get(), **(headers or {})}
        started = time.monotonic()
        call = IntegrationCall(
            provider=self.provider,
            organization=self.organization,
            method=method,
            path=(log_path or path)[:255],
            request_id=request_id_var.get(),
            request_body=self._log_body(json if json is not None else data),
        )
        try:
            with httpx.Client(timeout=timeout or self.timeout) as client:
                response = client.request(method, url, json=json, params=params, files=files, data=data, headers=all_headers)
        except httpx.TimeoutException as exc:
            call.error = "timeout"
            self._save(call, started)
            raise ProviderError("Tempo de resposta do provedor esgotado.", retryable=True) from exc
        except httpx.HTTPError as exc:
            call.error = str(exc)[:300]
            self._save(call, started)
            raise ProviderError("Falha de comunicação com o provedor.", retryable=True) from exc

        content_type = response.headers.get("content-type", "")
        if "json" in content_type:
            try:
                payload = response.json()
            except ValueError:
                payload = None
        else:
            payload = response.content

        call.status_code = response.status_code
        call.success = response.is_success
        if log_response and isinstance(payload, (dict, list)):
            call.response_body = self._log_body(payload)
        if not response.is_success:
            call.error = self.error_message(payload)[:300]
        self._save(call, started)
        return ProviderResponse(response.status_code, payload, response.headers)

    def error_message(self, payload) -> str:
        return scrub_provider(self._extract_error(payload))

    def _extract_error(self, payload) -> str:
        if isinstance(payload, dict):
            for key in ("error", "mensagem", "message", "msg"):
                value = payload.get(key)
                if isinstance(value, str) and value:
                    return value
        return "Erro do provedor."

    def _save(self, call: IntegrationCall, started: float) -> None:
        call.duration_ms = int((time.monotonic() - started) * 1000)
        try:
            call.save()
        except Exception:  # log de integração nunca pode derrubar a operação
            logger.exception("Falha ao gravar IntegrationCall")
