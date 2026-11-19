from django.urls import path
from rest_framework.routers import SimpleRouter

from .views import FiscalSettingsView, NotaViewSet

router = SimpleRouter(trailing_slash=False)
router.register("notas", NotaViewSet, basename="notas")
urlpatterns = [path("settings", FiscalSettingsView.as_view()), *router.urls]
