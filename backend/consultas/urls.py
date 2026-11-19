from rest_framework.routers import SimpleRouter

from .views import ConsultaViewSet, ProductViewSet

router = SimpleRouter(trailing_slash=False)
router.register("products", ProductViewSet, basename="products")
router.register("", ConsultaViewSet, basename="consultas")
urlpatterns = router.urls
