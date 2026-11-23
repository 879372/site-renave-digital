"""Configuração base, compartilhada por todos os ambientes.

Tudo que é segredo ou muda por ambiente vem de variáveis de ambiente.
"""

import os
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent.parent
load_dotenv(BASE_DIR / ".env")


def env(name: str, default: str | None = None, *, required: bool = False) -> str:
    value = os.environ.get(name, default)
    if required and not value:
        raise RuntimeError(f"Variável de ambiente obrigatória ausente: {name}")
    return value or ""


def env_bool(name: str, default: bool = False) -> bool:
    return env(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def env_list(name: str, default: str = "") -> list[str]:
    return [item.strip() for item in env(name, default).split(",") if item.strip()]


SECRET_KEY = env("DJANGO_SECRET_KEY", required=True)
DEBUG = False
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # terceiros
    "rest_framework",
    "rest_framework_simplejwt.token_blacklist",
    "drf_spectacular",
    "corsheaders",
    "django_filters",
    # plataforma
    "core",
    "accounts",
    "organizations",
    "audit",
    "vault",
    "wallet",
    "billing",
    "integrations",
    "consultas",
    "renave",
    "comunicacao",
    "fiscal",
    "pessoas",
    "estoque",
    "financeiro",
    "vendas",
    "contratos",
    "crm",
    "vitrine",
    "financiamento",
    "posvenda",
    "painel",
    "backoffice",
]

MIDDLEWARE = [
    "core.middleware.RequestIDMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "core.middleware.SecurityHeadersMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ]
        },
    }
]


def _database_from_url(url: str) -> dict:
    """Aceita DATABASE_URL (padrão do Railway/Heroku): postgresql://user:senha@host:porta/banco"""
    from urllib.parse import unquote, urlparse

    parts = urlparse(url)
    return {
        "NAME": unquote(parts.path.lstrip("/")),
        "USER": unquote(parts.username or ""),
        "PASSWORD": unquote(parts.password or ""),
        "HOST": parts.hostname or "",
        "PORT": str(parts.port or 5432),
    }


_db = (
    _database_from_url(env("DATABASE_URL"))
    if env("DATABASE_URL")
    else {
        "NAME": env("DATABASE_NAME", "renave"),
        "USER": env("DATABASE_USER", "renave"),
        "PASSWORD": env("DATABASE_PASSWORD", ""),
        "HOST": env("DATABASE_HOST", "localhost"),
        "PORT": env("DATABASE_PORT", "5432"),
    }
)
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        **_db,
        "CONN_HEALTH_CHECKS": True,
        "OPTIONS": {
            "pool": {"min_size": 1, "max_size": int(env("DATABASE_POOL_MAX", "10"))},
        },
    }
}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REDIS_URL = env("REDIS_URL", "redis://localhost:6379/0")
CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": REDIS_URL,
        "OPTIONS": {"CLIENT_CLASS": "django_redis.client.DefaultClient"},
        "KEY_PREFIX": "rd",
    }
}

AUTH_USER_MODEL = "accounts.User"
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
]
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 10}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "pt-br"
TIME_ZONE = "America/Sao_Paulo"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
# Arquivos enviados (fotos de veículos, documentos): Cloudflare R2 (API S3) quando configurado.
R2_BUCKET = env("R2_BUCKET")
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}
if R2_BUCKET:
    STORAGES["default"] = {
        "BACKEND": "storages.backends.s3.S3Storage",
        "OPTIONS": {
            "bucket_name": R2_BUCKET,
            "endpoint_url": env("R2_ENDPOINT_URL", required=True),
            "access_key": env("R2_ACCESS_KEY_ID", required=True),
            "secret_key": env("R2_SECRET_ACCESS_KEY", required=True),
            "region_name": env("R2_REGION", "auto"),
            "signature_version": "s3v4",
            "default_acl": None,
            "file_overwrite": False,
            # Domínio público do bucket (fotos da vitrine). Sem ele, as URLs saem assinadas e expiram.
            "custom_domain": env("R2_PUBLIC_DOMAIN") or None,
            "querystring_auth": not env("R2_PUBLIC_DOMAIN"),
        },
    }
MEDIA_ROOT = BASE_DIR / "media"
MEDIA_URL = env("MEDIA_URL", "/api/media/")
MAX_PHOTO_BYTES = 8 * 1024 * 1024
MAX_DOCUMENT_BYTES = 10 * 1024 * 1024

# --- API -------------------------------------------------------------------

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["rest_framework_simplejwt.authentication.JWTAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["accounts.permissions.IsAuthenticatedAndVerified"],
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PARSER_CLASSES": [
        "rest_framework.parsers.JSONParser",
        "rest_framework.parsers.MultiPartParser",
    ],
    "DEFAULT_FILTER_BACKENDS": ["django_filters.rest_framework.DjangoFilterBackend"],
    "DEFAULT_PAGINATION_CLASS": "core.pagination.DefaultPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "EXCEPTION_HANDLER": "core.exceptions.api_exception_handler",
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "anon": "60/min",
        "user": "600/min",
        "auth": "10/min",
        "consulta": "120/min",
        "lookup": "30/min",
    },
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=10),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": True,
    "ALGORITHM": "HS256",
    "SIGNING_KEY": env("JWT_SIGNING_KEY", SECRET_KEY),
    "AUTH_HEADER_TYPES": ("Bearer",),
}
REFRESH_COOKIE_NAME = "rd_refresh"
REFRESH_COOKIE_PATH = "/api/auth/"
REFRESH_COOKIE_SECURE = True

SPECTACULAR_SETTINGS = {
    "TITLE": "REVENDA DIGITAL API",
    "DESCRIPTION": "Consultas veiculares, estoque RENAVE, comunicação de venda e NF-e.",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
}

CORS_ALLOWED_ORIGINS = env_list("CORS_ALLOWED_ORIGINS", "http://localhost:5180")
CORS_ALLOW_CREDENTIALS = True
CORS_ALLOW_HEADERS = ["authorization", "content-type", "x-organization", "x-request-id", "idempotency-key"]
CSRF_TRUSTED_ORIGINS = CORS_ALLOWED_ORIGINS

# --- Segurança ------------------------------------------------------------------

SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Strict"
CSRF_COOKIE_SAMESITE = "Strict"
X_FRAME_OPTIONS = "DENY"
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024

ADMIN_URL = env("DJANGO_ADMIN_URL", "painel-interno/")

# --- E-mail (Resend por HTTPS) ----------------------------------------------------
# Sem a chave, o desenvolvimento mantém o backend de console.
RESEND_API_KEY = env("RESEND_API_KEY")
EMAIL_TIMEOUT = 15
EMAIL_BACKEND = "core.email_backend.ResendEmailBackend" if RESEND_API_KEY else "django.core.mail.backends.console.EmailBackend"
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", "REVENDA DIGITAL <nao-responda@kaibez.com.br>")
SERVER_EMAIL = DEFAULT_FROM_EMAIL
SUPPORT_EMAIL = env("SUPPORT_EMAIL", "contato@kaibez.com.br")
PRIVACY_EMAIL = env("PRIVACY_EMAIL", "privacidade@kaibez.com.br")

# Chave mestra do cofre (32 bytes em base64 urlsafe). Rotacionável: VAULT_MASTER_KEYS_OLD.
VAULT_MASTER_KEY = env("VAULT_MASTER_KEY", required=True)
VAULT_MASTER_KEYS_OLD = env_list("VAULT_MASTER_KEYS_OLD")

LOGIN_MAX_FAILURES = int(env("LOGIN_MAX_FAILURES", "5"))
LOGIN_LOCKOUT_SECONDS = int(env("LOGIN_LOCKOUT_SECONDS", "900"))
TOTP_ISSUER = "REVENDA DIGITAL"
# Versão vigente dos Termos de Uso e da Política de Privacidade (data de publicação).
LEGAL_VERSION = env("LEGAL_VERSION", "2026-11-19")

# --- Celery ---------------------------------------------------------------------

CELERY_BROKER_URL = env("CELERY_BROKER_URL", REDIS_URL)
CELERY_RESULT_BACKEND = None
CELERY_TASK_ACKS_LATE = True
CELERY_TASK_REJECT_ON_WORKER_LOST = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_TASK_TIME_LIMIT = 300
CELERY_TASK_SOFT_TIME_LIMIT = 240
CELERY_TIMEZONE = TIME_ZONE
CELERY_BEAT_SCHEDULE = {
    "consultas-varrer-pendentes": {
        "task": "consultas.tasks.sweep_pending",
        "schedule": 300.0,
    },
    # Fim de testes, fechamento mensal e inadimplência. Idempotente: pode rodar mais de uma vez.
    "billing-rotina-diaria": {
        "task": "billing.tasks.run_daily",
        "schedule": 3600.0,
    },
}

# --- Provedores -----------------------------------------------------------------

BUSCARS = {
    "BASE_URL": env("BUSCARS_BASE_URL", "https://api.buscars.com.br"),
    "API_KEY": env("BUSCARS_API_KEY"),
    "WEBHOOK_SECRET": env("BUSCARS_WEBHOOK_SECRET"),
    "TIMEOUT": float(env("BUSCARS_TIMEOUT", "60")),
}
CARVEN = {
    "BASE_URL": env("CARVEN_BASE_URL", "https://homologacao.carven.com.br"),
    "CLIENT_ID": env("CARVEN_CLIENT_ID"),
    "CLIENT_SECRET": env("CARVEN_CLIENT_SECRET"),
    "TIMEOUT": float(env("CARVEN_TIMEOUT", "60")),
}
GERANET = {
    "BASE_URL": env("GERANET_BASE_URL", "https://nfe.geranet.net/api/v1"),
    "API_KEY": env("GERANET_API_KEY"),
    "AMBIENTE": env("GERANET_AMBIENTE", "2"),  # 1 produção, 2 homologação
    "TIMEOUT": float(env("GERANET_TIMEOUT", "120")),
}

# Consulta de placa (API PLACAS / wdapi2: GET {BASE_URL}/consulta/{placa}/{token}).
PLACA_API = {
    "BASE_URL": env("PLACA_API_BASE_URL", "https://wdapi2.com.br"),
    "TOKEN": env("PLACA_API_TOKEN"),
    "TIMEOUT": float(env("PLACA_API_TIMEOUT", "20")),
}
FIPE_API = {
    "BASE_URL": env("FIPE_API_BASE_URL", "https://fipe.parallelum.com.br/api/v2"),
    "TOKEN": env("FIPE_API_TOKEN"),
    "TIMEOUT": float(env("FIPE_API_TIMEOUT", "15")),
}
# Assinatura eletrônica (ZapSign). Sandbox: https://sandbox.api.zapsign.com.br
ZAPSIGN = {
    "BASE_URL": env("ZAPSIGN_BASE_URL", "https://sandbox.api.zapsign.com.br"),
    "TOKEN": env("ZAPSIGN_API_TOKEN"),
    "WEBHOOK_TOKEN": env("ZAPSIGN_WEBHOOK_TOKEN"),
    "TIMEOUT": float(env("ZAPSIGN_TIMEOUT", "30")),
}
# Site das lojas: <slug>.STOREFRONT_DOMAIN
STOREFRONT_DOMAIN = env("STOREFRONT_DOMAIN", "revendadigital.kaibez.com.br")

ASAAS = {
    "BASE_URL": env("ASAAS_BASE_URL", "https://api-sandbox.asaas.com/v3"),
    "API_KEY": env("ASAAS_API_KEY"),
    "WEBHOOK_TOKEN": env("ASAAS_WEBHOOK_TOKEN"),
    "TIMEOUT": float(env("ASAAS_TIMEOUT", "30")),
}

PUBLIC_API_URL = env("PUBLIC_API_URL", "http://localhost:8000")

# --- Logs -----------------------------------------------------------------------

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {"request_id": {"()": "core.logging.RequestIDFilter"}},
    "formatters": {"json": {"()": "core.logging.JSONFormatter"}},
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "json", "filters": ["request_id"]},
    },
    "root": {"handlers": ["console"], "level": env("LOG_LEVEL", "INFO")},
    "loggers": {
        "django.db.backends": {"level": "WARNING"},
        "httpx": {"level": "WARNING"},
    },
}

SENTRY_DSN = env("SENTRY_DSN")
if SENTRY_DSN:
    import sentry_sdk

    sentry_sdk.init(
        dsn=SENTRY_DSN,
        environment=env("SENTRY_ENVIRONMENT", "production"),
        traces_sample_rate=float(env("SENTRY_TRACES_SAMPLE_RATE", "0.05")),
        send_default_pii=False,
    )
