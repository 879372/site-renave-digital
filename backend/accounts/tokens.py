"""Emissão de tokens: access no corpo, refresh em cookie httpOnly."""

from django.conf import settings
from django.core import signing
from rest_framework_simplejwt.tokens import RefreshToken

MFA_SALT = "accounts.mfa-login"
MFA_MAX_AGE = 300


def set_refresh_cookie(response, refresh: str) -> None:
    response.set_cookie(
        settings.REFRESH_COOKIE_NAME,
        refresh,
        max_age=int(settings.SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"].total_seconds()),
        httponly=True,
        secure=settings.REFRESH_COOKIE_SECURE,
        samesite="Strict",
        path=settings.REFRESH_COOKIE_PATH,
    )


def clear_refresh_cookie(response) -> None:
    response.delete_cookie(settings.REFRESH_COOKIE_NAME, path=settings.REFRESH_COOKIE_PATH, samesite="Strict")


def issue_tokens(user) -> tuple[str, str]:
    from django.contrib.auth.models import update_last_login

    update_last_login(None, user)
    refresh = RefreshToken.for_user(user)
    refresh["mfa"] = bool(user.totp_enabled)
    return str(refresh.access_token), str(refresh)


def make_mfa_token(user) -> str:
    return signing.dumps({"uid": str(user.public_id)}, salt=MFA_SALT)


def read_mfa_token(token: str) -> str | None:
    try:
        return signing.loads(token, salt=MFA_SALT, max_age=MFA_MAX_AGE)["uid"]
    except signing.BadSignature:
        return None
