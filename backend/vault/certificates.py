"""Leitura e validação de certificados ICP-Brasil A1 (.pfx/.p12)."""

import re
from dataclasses import dataclass
from datetime import datetime

from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import NameOID

# OIDs ICP-Brasil (DOC-ICP-04): dados do titular no SubjectAltName/otherName.
OID_CNPJ = "2.16.76.1.3.3"
OID_PF_DATA = "2.16.76.1.3.1"  # nascimento(8) + CPF(11) + ...


class CertificateError(ValueError):
    pass


@dataclass
class CertificateInfo:
    holder_document: str
    holder_name: str
    subject: str
    serial: str
    fingerprint: str
    not_before: datetime
    not_after: datetime


def _other_names(cert: x509.Certificate) -> dict[str, bytes]:
    try:
        san = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    except x509.ExtensionNotFound:
        return {}
    out = {}
    for general in san:
        if isinstance(general, x509.OtherName):
            out[general.type_id.dotted_string] = general.value
    return out


def _der_string(value: bytes) -> str:
    # valor é um DER (OCTET STRING / UTF8String / PrintableString): pula tag + tamanho
    if len(value) > 2 and value[1] < 0x80:
        value = value[2:]
    elif len(value) > 3:
        value = value[2 + (value[1] & 0x7F) :]
    return value.decode("latin-1", errors="ignore")


def load(pfx: bytes, password: str) -> CertificateInfo:
    try:
        key, cert, _ = pkcs12.load_key_and_certificates(pfx, password.encode() if password else None)
    except ValueError as exc:
        raise CertificateError("Não foi possível abrir o certificado: senha incorreta ou arquivo inválido.") from exc
    if cert is None or key is None:
        raise CertificateError("O arquivo não contém certificado e chave privada.")

    others = _other_names(cert)
    document = ""
    if OID_CNPJ in others:
        document = re.sub(r"[^0-9A-Z]", "", _der_string(others[OID_CNPJ]).upper())[:14]
    elif OID_PF_DATA in others:
        document = re.sub(r"\D", "", _der_string(others[OID_PF_DATA]))[8:19]

    cn_attrs = cert.subject.get_attributes_for_oid(NameOID.COMMON_NAME)
    common_name = cn_attrs[0].value if cn_attrs else ""
    if not document:
        match = re.search(r":([0-9A-Z]{14}|\d{11})\b", str(common_name))
        document = match.group(1) if match else ""
    if not document:
        raise CertificateError("Não foi possível identificar o CPF/CNPJ do titular no certificado.")

    return CertificateInfo(
        holder_document=document,
        holder_name=str(common_name).split(":")[0].strip(),
        subject=cert.subject.rfc4514_string()[:500],
        serial=format(cert.serial_number, "x"),
        fingerprint=cert.fingerprint(hashes.SHA256()).hex(),
        not_before=cert.not_valid_before_utc,
        not_after=cert.not_valid_after_utc,
    )


def same_holder(certificate_document: str, expected_document: str) -> bool:
    """CNPJ: basta a mesma raiz (matriz serve às filiais). CPF: igual."""
    if len(certificate_document) == 14 and len(expected_document) == 14:
        return certificate_document[:8] == expected_document[:8]
    return certificate_document == expected_document
