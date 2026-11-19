"""Criptografia em envelope (AES-256-GCM).

Cada valor é cifrado com uma chave de dados (DEK) aleatória; a DEK é cifrada pela
chave mestra (KEK) vinda do ambiente. Formato do blob:

    b"RD1" | kek_id(8) | dek_nonce(12) | dek_cifrada(48) | nonce(12) | ciphertext+tag

Rotação: defina a nova VAULT_MASTER_KEY e mova a antiga para VAULT_MASTER_KEYS_OLD;
os blobs antigos continuam legíveis e `reencrypt()` regrava com a chave nova.
"""

import base64
import hashlib
import os
from functools import lru_cache

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from django.conf import settings

MAGIC = b"RD1"


class VaultError(Exception):
    pass


def _decode_key(raw: str) -> bytes:
    key = base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4))
    if len(key) != 32:
        raise VaultError("A chave mestra precisa ter 32 bytes (base64 urlsafe).")
    return key


def _key_id(key: bytes) -> bytes:
    return hashlib.sha256(b"kek-id:" + key).digest()[:8]


@lru_cache(maxsize=1)
def _keys() -> tuple[bytes, dict[bytes, bytes]]:
    current = _decode_key(settings.VAULT_MASTER_KEY)
    all_keys = {_key_id(current): current}
    for old in settings.VAULT_MASTER_KEYS_OLD:
        key = _decode_key(old)
        all_keys[_key_id(key)] = key
    return current, all_keys


def generate_master_key() -> str:
    return base64.urlsafe_b64encode(os.urandom(32)).decode().rstrip("=")


def encrypt_bytes(plaintext: bytes, aad: bytes = b"") -> bytes:
    kek, _ = _keys()
    dek = AESGCM.generate_key(bit_length=256)
    dek_nonce, nonce = os.urandom(12), os.urandom(12)
    wrapped = AESGCM(kek).encrypt(dek_nonce, dek, b"dek")
    ciphertext = AESGCM(dek).encrypt(nonce, plaintext, aad)
    return MAGIC + _key_id(kek) + dek_nonce + wrapped + nonce + ciphertext


def decrypt_bytes(blob: bytes, aad: bytes = b"") -> bytes:
    if not blob or blob[:3] != MAGIC:
        raise VaultError("Formato de dado cifrado desconhecido.")
    _, keys = _keys()
    kek = keys.get(blob[3:11])
    if kek is None:
        raise VaultError("Chave mestra não disponível para este dado.")
    dek_nonce, wrapped = blob[11:23], blob[23:71]
    nonce, ciphertext = blob[71:83], blob[83:]
    try:
        dek = AESGCM(kek).decrypt(dek_nonce, wrapped, b"dek")
        return AESGCM(dek).decrypt(nonce, ciphertext, aad)
    except Exception as exc:  # InvalidTag
        raise VaultError("Falha ao decifrar (dado adulterado ou AAD incorreto).") from exc


def needs_rotation(blob: bytes) -> bool:
    kek, _ = _keys()
    return blob[3:11] != _key_id(kek)


def reencrypt(blob: bytes, aad: bytes = b"") -> bytes:
    return encrypt_bytes(decrypt_bytes(blob, aad), aad)
