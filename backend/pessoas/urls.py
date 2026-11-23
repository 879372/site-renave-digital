from rest_framework.routers import SimpleRouter

from .views import PessoaViewSet

router = SimpleRouter(trailing_slash=False)
router.register("", PessoaViewSet, basename="pessoas")
urlpatterns = router.urls
