from .base import *  # noqa: F403
from .base import DATABASES

DEBUG = False
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
DATABASES["default"]["OPTIONS"] = {}
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
CELERY_TASK_ALWAYS_EAGER = True
REFRESH_COOKIE_SECURE = False
REST_FRAMEWORK = {**REST_FRAMEWORK, "DEFAULT_THROTTLE_CLASSES": []}  # noqa: F405
BUSCARS = {**BUSCARS, "API_KEY": "bk_test", "WEBHOOK_SECRET": "whsec_test"}  # noqa: F405
CARVEN = {**CARVEN, "CLIENT_ID": "cid", "CLIENT_SECRET": "csecret"}  # noqa: F405
GERANET = {**GERANET, "API_KEY": "gn_test"}  # noqa: F405
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
