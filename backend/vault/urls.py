from rest_framework.routers import SimpleRouter

from .views import CertificateViewSet

router = SimpleRouter(trailing_slash=False)
router.register("certificates", CertificateViewSet, basename="certificates")
urlpatterns = router.urls
