"""Mascaramento de dados pessoais para logs e respostas resumidas."""

import re
from typing import Any

SENSITIVE_KEYS = {
    "cpf",
    "cnpj",
    "cpf_cnpj",
    "senha",
    "password",
    "client_secret",
    "certificadodigital",
    "senhacertificadodigital",
    "chave-certificado",
    "certificado",
    "access_token",
    "token",
    "x-api-key",
    "authorization",
    "email",
    "telefone",
    "nome",
    "logradouro",
    "longadouro",
    "cep",
    "bytes",
    "atpv",
    "pdf",
    "xml",
}


def mask_document(value: str) -> str:
    if not value:
        return value
    digits = re.sub(r"[^0-9A-Za-z]", "", str(value))
    if len(digits) <= 4:
        return "***"
    return f"{'*' * (len(digits) - 4)}{digits[-4:]}"


def redact(data: Any, depth: int = 0) -> Any:
    """Copia a estrutura trocando valores de chaves sensíveis. Limita profundidade e tamanho."""
    if depth > 6:
        return "…"
    if isinstance(data, dict):
        out = {}
        for key, value in data.items():
            if str(key).lower() in SENSITIVE_KEYS:
                out[key] = "[redacted]" if not isinstance(value, (dict, list)) else redact(value, depth + 1)
            else:
                out[key] = redact(value, depth + 1)
        return out
    if isinstance(data, list):
        return [redact(item, depth + 1) for item in data[:50]]
    if isinstance(data, str) and len(data) > 500:
        return data[:500] + "…"
    return data


_PROVIDER_NAMES = re.compile(r"\b(bus\s?cars|carven|geranet(\s+nfe)?|brasil\s?api|via\s?cep)\b", re.IGNORECASE)


def scrub_provider(text) -> str:
    """Remove nomes de fornecedores de mensagens que chegam ao usuário."""
    if not text:
        return ""
    return _PROVIDER_NAMES.sub("serviço", str(text))
