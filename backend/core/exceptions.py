import logging

from rest_framework import status
from rest_framework.exceptions import APIException
from rest_framework.views import exception_handler

logger = logging.getLogger(__name__)


class BusinessError(APIException):
    """Erro de regra de negócio com código estável para o front."""

    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    default_code = "business_error"
    default_detail = "Não foi possível concluir a operação."

    def __init__(self, detail=None, code=None, status_code=None, extra=None):
        super().__init__(detail, code)
        if status_code:
            self.status_code = status_code
        self.extra = extra or {}


class InsufficientBalance(BusinessError):
    status_code = status.HTTP_402_PAYMENT_REQUIRED
    default_code = "insufficient_balance"
    default_detail = "Saldo insuficiente. Faça uma recarga para continuar."


class ProviderUnavailable(BusinessError):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_code = "provider_unavailable"
    default_detail = "O serviço está temporariamente indisponível. Tente novamente em instantes."


def api_exception_handler(exc, context):
    """Formato único de erro: {"error": {"code", "message", "fields"?}}."""
    response = exception_handler(exc, context)
    if response is None:
        logger.exception("Erro não tratado na API")
        return None

    code = getattr(exc, "default_code", "error")
    if hasattr(exc, "get_codes"):
        codes = exc.get_codes()
        if isinstance(codes, str):
            code = codes

    data = response.data
    body = {"code": code}
    if isinstance(data, dict) and "detail" in data and len(data) == 1:
        body["message"] = str(data["detail"])
    elif isinstance(data, dict):
        body["message"] = "Verifique os campos informados."
        body["fields"] = data
        body["code"] = "validation_error" if response.status_code == 400 else code
    else:
        body["message"] = " ".join(str(item) for item in data)
    if getattr(exc, "extra", None):
        body.update(exc.extra)
    response.data = {"error": body}
    return response
