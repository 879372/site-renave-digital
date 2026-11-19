from django.db import transaction
from django.utils import timezone

from core.exceptions import BusinessError

from . import certificates
from .crypto import decrypt_bytes, encrypt_bytes
from .models import Certificate

MAX_PFX_BYTES = 50 * 1024


def store_certificate(*, organization, client, pfx: bytes, password: str, uploaded_by) -> Certificate:
    if len(pfx) > MAX_PFX_BYTES:
        raise BusinessError("Arquivo muito grande para um certificado A1.")
    try:
        info = certificates.load(pfx, password)
    except certificates.CertificateError as exc:
        raise BusinessError(str(exc), code="invalid_certificate")

    expected = client.document if client else organization.cnpj
    if not certificates.same_holder(info.holder_document, expected):
        raise BusinessError(
            f"O certificado pertence ao documento {info.holder_document}, diferente de {expected}.",
            code="certificate_holder_mismatch",
        )
    if info.not_after <= timezone.now():
        raise BusinessError("Este certificado está vencido.", code="certificate_expired")

    with transaction.atomic():
        Certificate.objects.filter(organization=organization, client=client, is_active=True).update(is_active=False)
        cert = Certificate(
            organization=organization,
            client=client,
            holder_document=info.holder_document,
            holder_name=info.holder_name,
            subject=info.subject,
            serial=info.serial,
            fingerprint=info.fingerprint,
            not_before=info.not_before,
            not_after=info.not_after,
            uploaded_by=uploaded_by,
            pfx_encrypted=b"",
            password_encrypted=b"",
        )
        cert.pfx_encrypted = encrypt_bytes(pfx, cert.aad)
        cert.password_encrypted = encrypt_bytes(password.encode(), cert.aad)
        cert.save()
    return cert


def active_certificate(organization, client=None) -> Certificate:
    cert = Certificate.objects.filter(organization=organization, client=client, is_active=True).first()
    if cert is None:
        owner = client.name if client else "a empresa"
        raise BusinessError(f"Cadastre o certificado digital A1 de {owner} antes de continuar.", code="certificate_missing")
    if cert.not_after <= timezone.now():
        raise BusinessError("O certificado digital está vencido. Envie um novo.", code="certificate_expired")
    return cert


def open_certificate(cert: Certificate) -> tuple[bytes, str]:
    """Decifra para uso imediato numa chamada ao provedor. Não guarde o retorno."""
    pfx = decrypt_bytes(bytes(cert.pfx_encrypted), cert.aad)
    password = decrypt_bytes(bytes(cert.password_encrypted), cert.aad).decode()
    return pfx, password
