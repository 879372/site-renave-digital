from django.urls import path
from rest_framework.routers import SimpleRouter

from . import views

router = SimpleRouter(trailing_slash=False)
router.register("anuncios", views.AnuncioViewSet, basename="anuncios")

urlpatterns = [path("", views.SiteView.as_view()), *router.urls]
