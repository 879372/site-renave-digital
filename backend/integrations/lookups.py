"""Consultas cadastrais públicas e gratuitas (CNPJ e CEP) para preencher formulários.

Fontes abertas: BrasilAPI (dados públicos da Receita Federal) e ViaCEP.
Os nomes das fontes nunca são expostos ao front.
"""

import logging

import httpx
from django.core.cache import cache

from core import documents

logger = logging.getLogger(__name__)
TIMEOUT = 8.0


def _title(value: str | None) -> str:
    if not value:
        return ""
    small = {"de", "da", "do", "das", "dos", "e"}
    words = str(value).lower().split()
    return " ".join(w if w in small and i else w.capitalize() for i, w in enumerate(words))


def _get(url: str) -> dict | None:
    try:
        response = httpx.get(url, timeout=TIMEOUT, headers={"Accept": "application/json", "User-Agent": "plataforma/1.0"})
    except httpx.HTTPError:
        logger.warning("Consulta cadastral indisponível")
        return None
    if response.status_code != 200:
        return None
    try:
        data = response.json()
    except ValueError:
        return None
    return data if isinstance(data, dict) and not data.get("erro") else None


def company(cnpj: str) -> dict | None:
    cnpj = documents.normalize_cnpj(cnpj)
    if not documents.is_valid_cnpj(cnpj):
        return None
    key = f"lookup:cnpj:{cnpj}"
    if (cached := cache.get(key)) is not None:
        return cached or None
    data = _get(f"https://brasilapi.com.br/api/cnpj/v1/{cnpj}")
    if data is None:
        cache.set(key, {}, 300)
        return None
    kind, name = (data.get("descricao_tipo_de_logradouro") or "").strip(), (data.get("logradouro") or "").strip()
    street = name if not kind or name.upper().startswith(kind.upper()) or kind.upper() in name.upper().split() else f"{kind} {name}"
    result = {
        "cnpj": cnpj,
        "legal_name": (data.get("razao_social") or "").strip(),
        "trade_name": (data.get("nome_fantasia") or "").strip(),
        "status": (data.get("descricao_situacao_cadastral") or "").strip(),
        "zip_code": documents.only_digits(data.get("cep") or ""),
        "street": _title(street),
        "number": (data.get("numero") or "").strip()[:10],
        "complement": _title(data.get("complemento"))[:60],
        "district": _title(data.get("bairro"))[:60],
        "city": _title(data.get("municipio")),
        "city_ibge": str(data.get("codigo_municipio_ibge") or ""),
        "uf": (data.get("uf") or "").upper(),
        "phone": documents.only_digits(data.get("ddd_telefone_1") or ""),
    }
    cache.set(key, result, 60 * 60 * 24)
    return result


def address(cep: str) -> dict | None:
    cep = documents.only_digits(cep)
    if len(cep) != 8:
        return None
    key = f"lookup:cep:{cep}"
    if (cached := cache.get(key)) is not None:
        return cached or None
    data = _get(f"https://viacep.com.br/ws/{cep}/json/")
    if data is None:
        cache.set(key, {}, 300)
        return None
    result = {
        "zip_code": cep,
        "street": data.get("logradouro", ""),
        "district": data.get("bairro", ""),
        "city": data.get("localidade", ""),
        "uf": data.get("uf", ""),
        "city_ibge": data.get("ibge", ""),
    }
    cache.set(key, result, 60 * 60 * 24 * 7)
    return result
