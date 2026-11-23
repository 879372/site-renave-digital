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
    path("billing/", include("billing.urls")),
    path("pessoas/", include("pessoas.urls")),
    path("estoque/", include("estoque.urls")),
    path("financeiro/", include("financeiro.urls")),
    path("vendas/", include("vendas.urls")),
    path("contratos/", include("contratos.urls")),
    path("crm/", include("crm.urls")),
    path("site/", include("vitrine.urls")),
    path("public/", include("vitrine.public_urls")),
    path("financiamento/", include("financiamento.urls")),
    path("posvenda/", include("posvenda.urls")),
    path("lojas/", include("organizations.branch_urls")),
    path("painel/", include("painel.urls")),
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

if not settings.R2_BUCKET:
    # Sem R2, fotos públicas (veículos, avaliações, logo do site) saem do disco.
    # Documentos nunca: só pelo download autenticado da API.
    from django.urls import re_path
    from django.views.static import serve

    urlpatterns += [re_path(r"^api/media/(?P<path>(?:veiculos|avaliacoes|sites)/[\w./-]+)$", serve, {"document_root": settings.MEDIA_ROOT})]

if settings.DEBUG:
    urlpatterns += [
        path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
        path("api/docs/", SpectacularRedocView.as_view(url_name="schema")),
    ]

handler404 = "core.errors.not_found"
handler500 = "core.errors.server_error"
