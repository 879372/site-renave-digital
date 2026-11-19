from rest_framework.routers import SimpleRouter

from .views import ComunicacaoViewSet

router = SimpleRouter(trailing_slash=False)
router.register("", ComunicacaoViewSet, basename="comunicacao")
urlpatterns = router.urls
