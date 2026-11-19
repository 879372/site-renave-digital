import re
import uuid

from .context import organization_id_var, request_id_var, user_id_var

_VALID_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{8,64}$")

CSP = "; ".join(
    [
        "default-src 'none'",
        "frame-ancestors 'none'",
        "base-uri 'none'",
        "form-action 'self'",
    ]
)


class RequestIDMiddleware:
    """Propaga X-Request-ID (ou gera um) para logs, respostas e chamadas a provedores."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        incoming = request.headers.get("X-Request-ID", "")
        request_id = incoming if _VALID_REQUEST_ID.match(incoming) else uuid.uuid4().hex
        request.request_id = request_id
        tokens = [
            request_id_var.set(request_id),
            user_id_var.set("-"),
            organization_id_var.set("-"),
        ]
        try:
            response = self.get_response(request)
        finally:
            for var, token in zip((request_id_var, user_id_var, organization_id_var), tokens, strict=True):
                var.reset(token)
        response["X-Request-ID"] = request_id
        return response


class SecurityHeadersMiddleware:
    """Cabeçalhos de segurança para respostas da API (o front tem a própria CSP)."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if request.path.startswith("/api/") and not request.path.startswith("/api/docs"):
            response.setdefault("Content-Security-Policy", CSP)
            response.setdefault("Cache-Control", "no-store")
        response.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        response.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        return response
