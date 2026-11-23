from django.urls import path
from rest_framework.routers import SimpleRouter

from . import views

router = SimpleRouter(trailing_slash=False)
router.register("contas", views.ContaViewSet, basename="fin-contas")
router.register("categorias", views.CategoriaViewSet, basename="fin-categorias")
router.register("lancamentos", views.LancamentoViewSet, basename="fin-lancamentos")

urlpatterns = [
    path("resumo", views.ResumoView.as_view()),
    path("fluxo", views.FluxoView.as_view()),
    path("dre", views.DreView.as_view()),
    path("conciliacao", views.ConciliacaoView.as_view()),
    *router.urls,
]
