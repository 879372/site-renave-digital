from django.urls import path
from rest_framework.routers import SimpleRouter

from . import auth, views

router = SimpleRouter(trailing_slash=False)
router.register("stats", views.StatsViewSet, basename="admin-stats")
router.register("organizations", views.OrganizationAdminViewSet, basename="admin-organizations")
router.register("users", views.UserAdminViewSet, basename="admin-users")
router.register("memberships", views.MembershipAdminViewSet, basename="admin-memberships")
router.register("topups", views.TopUpAdminViewSet, basename="admin-topups")
router.register("ledger", views.LedgerAdminViewSet, basename="admin-ledger")
router.register("products", views.ProductAdminViewSet, basename="admin-products")
router.register("prices", views.ServicePriceAdminViewSet, basename="admin-prices")
router.register("consultas", views.ConsultaAdminViewSet, basename="admin-consultas")
router.register("notas", views.NotaAdminViewSet, basename="admin-notas")
router.register("stock", views.StockAdminViewSet, basename="admin-stock")
router.register("renave-operations", views.RenaveOperationAdminViewSet, basename="admin-renave-ops")
router.register("comunicacoes", views.ComunicacaoAdminViewSet, basename="admin-comunicacoes")
router.register("certificates", views.CertificateAdminViewSet, basename="admin-certificates")
router.register("integration-calls", views.IntegrationCallAdminViewSet, basename="admin-calls")
router.register("webhooks", views.WebhookAdminViewSet, basename="admin-webhooks")
router.register("audit", views.AuditAdminViewSet, basename="admin-audit")

urlpatterns = [
    path("auth/login", auth.AdminLoginView.as_view()),
    path("auth/refresh", auth.AdminRefreshView.as_view()),
    path("auth/logout", auth.AdminLogoutView.as_view()),
    path("auth/me", auth.AdminMeView.as_view()),
    *router.urls,
]
