from rest_framework.routers import SimpleRouter

from . import views

router = SimpleRouter(trailing_slash=False)
router.register("modelos", views.ModeloViewSet, basename="modelos")
router.register("documentos", views.DocumentoViewSet, basename="documentos")
urlpatterns = router.urls
