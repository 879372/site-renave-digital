from rest_framework.routers import SimpleRouter

from . import views

router = SimpleRouter(trailing_slash=False)
router.register("garantias", views.GarantiaViewSet, basename="garantias")
router.register("ocorrencias", views.OcorrenciaViewSet, basename="ocorrencias")
urlpatterns = router.urls
