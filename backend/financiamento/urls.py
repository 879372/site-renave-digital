from django.urls import path
from rest_framework.routers import SimpleRouter

from . import views

router = SimpleRouter(trailing_slash=False)
router.register("fichas", views.FichaViewSet, basename="fichas")
urlpatterns = [path("simular", views.SimularView.as_view()), *router.urls]
