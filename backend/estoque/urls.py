from django.urls import re_path
from rest_framework.routers import SimpleRouter

from . import views

router = SimpleRouter(trailing_slash=False)
router.register("veiculos", views.VehicleViewSet, basename="veiculos")
router.register("avaliacoes", views.AvaliacaoViewSet, basename="avaliacoes")

F = r"(?P<kind>carro|moto|caminhao)"
urlpatterns = [
    re_path(rf"^fipe/{F}/codigo/(?P<code>[\w-]+)/anos/(?P<year>[\w-]+)$", views.FipeView.as_view()),
    re_path(rf"^fipe/{F}/codigo/(?P<code>[\w-]+)/anos$", views.FipeView.as_view()),
    re_path(rf"^fipe/{F}/marcas/(?P<brand>\d+)/modelos/(?P<model>\d+)/anos/(?P<year>[\w-]+)$", views.FipeView.as_view()),
    re_path(rf"^fipe/{F}/marcas/(?P<brand>\d+)/modelos/(?P<model>\d+)/anos$", views.FipeView.as_view()),
    re_path(rf"^fipe/{F}/marcas/(?P<brand>\d+)/modelos$", views.FipeView.as_view()),
    re_path(rf"^fipe/{F}/marcas$", views.FipeView.as_view()),
    *router.urls,
]
