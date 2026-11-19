"""Bloqueio progressivo de login por e-mail e por IP (Redis)."""

import hashlib

from django.conf import settings
from django.core.cache import cache


def _key(kind: str, value: str) -> str:
    digest = hashlib.sha256(value.lower().encode()).hexdigest()[:32]
    return f"auth:fail:{kind}:{digest}"


def is_locked(email: str, ip: str) -> bool:
    limit = settings.LOGIN_MAX_FAILURES
    return (cache.get(_key("email", email), 0) >= limit) or (cache.get(_key("ip", ip), 0) >= limit * 4)


def register_failure(email: str, ip: str) -> None:
    ttl = settings.LOGIN_LOCKOUT_SECONDS
    for kind, value in (("email", email), ("ip", ip)):
        key = _key(kind, value)
        if cache.add(key, 1, ttl):
            continue
        try:
            cache.incr(key)
        except ValueError:
            cache.set(key, 1, ttl)


def reset(email: str) -> None:
    cache.delete(_key("email", email))
