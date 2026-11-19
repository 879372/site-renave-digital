import hashlib
import secrets

import pyotp
from django.conf import settings

from vault.crypto import decrypt_bytes, encrypt_bytes


def new_secret() -> str:
    return pyotp.random_base32()


def store_secret(user, secret: str) -> None:
    user.totp_secret_encrypted = encrypt_bytes(secret.encode(), aad=f"totp:{user.public_id}".encode())


def load_secret(user) -> str | None:
    if not user.totp_secret_encrypted:
        return None
    raw = decrypt_bytes(bytes(user.totp_secret_encrypted), aad=f"totp:{user.public_id}".encode())
    return raw.decode()


def provisioning_uri(user, secret: str) -> str:
    return pyotp.TOTP(secret).provisioning_uri(name=user.email, issuer_name=settings.TOTP_ISSUER)


def verify(user, code: str) -> bool:
    secret = load_secret(user)
    if not secret or not code:
        return False
    return pyotp.TOTP(secret).verify(code.strip().replace(" ", ""), valid_window=1)


def _hash(code: str) -> str:
    return hashlib.sha256(code.strip().upper().encode()).hexdigest()


def generate_recovery_codes(user, count: int = 8) -> list[str]:
    codes = [f"{secrets.token_hex(3)}-{secrets.token_hex(3)}".upper() for _ in range(count)]
    user.recovery_codes = [_hash(code) for code in codes]
    return codes


def consume_recovery_code(user, code: str) -> bool:
    hashed = _hash(code)
    if hashed in user.recovery_codes:
        user.recovery_codes = [item for item in user.recovery_codes if item != hashed]
        user.save(update_fields=["recovery_codes"])
        return True
    return False
