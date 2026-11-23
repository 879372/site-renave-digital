from .base import *  # noqa: F403
from .base import env, env_bool

DEBUG = False

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = env_bool("DJANGO_SECURE_SSL_REDIRECT", True)
# O healthcheck do Railway chama por HTTP interno; não redirecionar.
SECURE_REDIRECT_EXEMPT = [r"^api/health/"]
# O Railway (e a Vercel, no rewrite de /api) entregam o host público no X-Forwarded-Host.
USE_X_FORWARDED_HOST = env_bool("DJANGO_USE_X_FORWARDED_HOST", False)
# Host usado pelo healthcheck do Railway.
ALLOWED_HOSTS = [*ALLOWED_HOSTS, "healthcheck.railway.app"]  # noqa: F405
SECURE_HSTS_SECONDS = 63072000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
REFRESH_COOKIE_SECURE = True

# E-mail transacional via API HTTPS do Resend. Sem a chave, a API sobe, mas os e-mails não saem.
if not env("RESEND_API_KEY"):
    import logging

    logging.getLogger("config").error("RESEND_API_KEY ausente: e-mails (senha, convites) não serão enviados.")
