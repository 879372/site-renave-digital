"""Verificação de e-mail por código de 6 dígitos.

O código fica só no cache (Redis), como HMAC — nunca em texto puro — e vale CODE_TTL.
Cada código aceita MAX_ATTEMPTS tentativas; depois disso é preciso pedir outro.
Reenvio limitado a um a cada RESEND_COOLDOWN segundos por usuário.
"""

import hashlib
import hmac
import secrets
import time

from django.conf import settings
from django.core.cache import cache
from rest_framework import status
from rest_framework.exceptions import PermissionDenied

from core import email as mailer

CODE_TTL = 30 * 60
RESEND_COOLDOWN = 60
MAX_ATTEMPTS = 5


class EmailUnverified(PermissionDenied):
    status_code = status.HTTP_403_FORBIDDEN
    default_code = "email_unverified"
    default_detail = "Confirme seu e-mail para continuar."


def _key(user) -> str:
    return f"accounts:email-verify:{user.pk}"


def _digest(user, code: str) -> str:
    msg = f"{user.pk}:{user.email}:{code}".encode()
    return hmac.new(settings.SECRET_KEY.encode(), msg, hashlib.sha256).hexdigest()


def retry_in(user) -> int:
    data = cache.get(_key(user))
    if not data:
        return 0
    return max(0, int(data["sent_at"] + RESEND_COOLDOWN - time.time()))


def send_code(user) -> int:
    """Envia um código novo. Devolve 0 se enviou, ou os segundos que faltam para poder reenviar."""
    wait = retry_in(user)
    if wait:
        return wait
    code = f"{secrets.randbelow(1_000_000):06d}"
    cache.set(_key(user), {"digest": _digest(user, code), "attempts": 0, "sent_at": time.time()}, CODE_TTL)
    origin = settings.CORS_ALLOWED_ORIGINS[0]
    mailer.send(
        f"{code} é o seu código de verificação — REVENDA DIGITAL",
        f"Olá, {user.full_name.split()[0] if user.full_name else ''}.\n\n"
        f"Seu código para confirmar o e-mail na REVENDA DIGITAL é:\n\n    {code}\n\n"
        f"Ele vale por {CODE_TTL // 60} minutos. Você também pode confirmar pelo link:\n"
        f"{origin}/verificar-email?codigo={code}\n\n"
        "Se você não criou uma conta na REVENDA DIGITAL, ignore este e-mail.",
        [user.email],
    )
    return 0


def check_code(user, code: str) -> str:
    """Devolve "ok", "invalid" (pode tentar de novo) ou "expired" (precisa de um código novo)."""
    key = _key(user)
    data = cache.get(key)
    if not data or data["attempts"] >= MAX_ATTEMPTS:
        return "expired"
    if hmac.compare_digest(data["digest"], _digest(user, (code or "").strip())):
        cache.delete(key)
        return "ok"
    data["attempts"] += 1
    remaining = int(data["sent_at"] + CODE_TTL - time.time())
    if remaining > 0:
        cache.set(key, data, remaining)
    return "expired" if data["attempts"] >= MAX_ATTEMPTS else "invalid"


def mark_verified(user) -> None:
    if not user.email_verified:
        user.email_verified = True
        user.save(update_fields=["email_verified"])
    cache.delete(_key(user))
