from django.conf import settings
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView

from core import health

api = [
    path("health/live", health.live),
    path("health/ready", health.ready),
    path("auth/", include("accounts.urls")),
    path("organizations/", include("organizations.urls")),
    path("vault/", include("vault.urls")),
    path("wallet/", include("wallet.urls")),
    path("audit/", include("audit.urls")),
    path("consultas/", include("consultas.urls")),
    path("renave/", include("renave.urls")),
    path("comunicacao-venda/", include("comunicacao.urls")),
    path("fiscal/", include("fiscal.urls")),
    path("lookup/", include("integrations.lookup_urls")),
    path("hooks/", include("integrations.urls")),
    path("admin/", include("backoffice.urls")),
]

urlpatterns = [
    path(settings.ADMIN_URL, admin.site.urls),
    path("api/", include(api)),
]

if settings.DEBUG:
    urlpatterns += [
        path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
        path("api/docs/", SpectacularRedocView.as_view(url_name="schema")),
    ]

handler404 = "core.errors.not_found"
handler500 = "core.errors.server_error"
