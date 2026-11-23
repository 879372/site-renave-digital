from django.urls import path
from rest_framework.routers import SimpleRouter

from . import views

router = SimpleRouter(trailing_slash=False)
router.register("metas", views.MetaViewSet, basename="metas")
router.register("", views.VendaViewSet, basename="vendas")

urlpatterns = [
    path("vendedores", views.VendedoresView.as_view()),
    path("comissoes/regra", views.RegraComissaoView.as_view()),
    path("comissoes", views.ComissaoRelatorioView.as_view()),
    *router.urls,
]
