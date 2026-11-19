"""Validação e normalização de documentos brasileiros e identificadores veiculares.

CNPJ segue o novo formato alfanumérico (IN RFB 2.229/2024): 12 posições [0-9A-Z]
e 2 dígitos verificadores numéricos. Valor de cada caractere = ord(c) - 48.
"""

import re

from django.core.exceptions import ValidationError

_ONLY_ALNUM = re.compile(r"[^0-9A-Za-z]")
_ONLY_DIGITS = re.compile(r"\D")
PLATE_RE = re.compile(r"^[A-Z]{3}[0-9][A-Z0-9][0-9]{2}$")
VIN_RE = re.compile(r"^[A-HJ-NPR-Z0-9]{17}$")


def only_digits(value: str) -> str:
    return _ONLY_DIGITS.sub("", value or "")


def normalize_cnpj(value: str) -> str:
    return _ONLY_ALNUM.sub("", value or "").upper()


def is_valid_cpf(value: str) -> bool:
    cpf = only_digits(value)
    if len(cpf) != 11 or cpf == cpf[0] * 11:
        return False
    for size in (9, 10):
        total = sum(int(cpf[i]) * (size + 1 - i) for i in range(size))
        digit = (total * 10) % 11 % 10
        if digit != int(cpf[size]):
            return False
    return True


def is_valid_cnpj(value: str) -> bool:
    cnpj = normalize_cnpj(value)
    if not re.fullmatch(r"[0-9A-Z]{12}[0-9]{2}", cnpj) or cnpj == cnpj[0] * 14:
        return False
    values = [ord(ch) - 48 for ch in cnpj]
    for size in (12, 13):
        weights = list(range(size - 7, 1, -1)) + list(range(9, 1, -1))
        total = sum(v * w for v, w in zip(values[:size], weights, strict=True))
        remainder = total % 11
        digit = 0 if remainder < 2 else 11 - remainder
        if digit != values[size]:
            return False
    return True


def normalize_document(value: str) -> str:
    """CPF (11 dígitos) ou CNPJ (14 alfanuméricos), sem máscara."""
    raw = normalize_cnpj(value)
    return raw


def is_valid_document(value: str) -> bool:
    doc = normalize_document(value)
    return is_valid_cpf(doc) if len(doc) == 11 else is_valid_cnpj(doc)


def normalize_plate(value: str) -> str:
    return _ONLY_ALNUM.sub("", value or "").upper()


def is_valid_plate(value: str) -> bool:
    return bool(PLATE_RE.match(normalize_plate(value)))


def is_valid_renavam(value: str) -> bool:
    renavam = only_digits(value).zfill(11)
    if len(renavam) != 11:
        return False
    base = renavam[:10][::-1]
    weights = [2, 3, 4, 5, 6, 7, 8, 9, 2, 3]
    total = sum(int(d) * w for d, w in zip(base, weights, strict=True))
    digit = (total * 10) % 11
    digit = 0 if digit == 10 else digit
    return digit == int(renavam[10])


def is_valid_vin(value: str) -> bool:
    return bool(VIN_RE.match(_ONLY_ALNUM.sub("", value or "").upper()))


# --- validadores Django -------------------------------------------------------


def validate_cpf(value):
    if not is_valid_cpf(value):
        raise ValidationError("CPF inválido.")


def validate_cnpj(value):
    if not is_valid_cnpj(value):
        raise ValidationError("CNPJ inválido.")


def validate_document(value):
    if not is_valid_document(value):
        raise ValidationError("CPF/CNPJ inválido.")


def validate_plate(value):
    if not is_valid_plate(value):
        raise ValidationError("Placa inválida.")
