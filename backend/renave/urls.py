from django.urls import path
from rest_framework.routers import SimpleRouter

from .views import AptidaoView, StockViewSet

router = SimpleRouter(trailing_slash=False)
router.register("stock", StockViewSet, basename="stock")
urlpatterns = [path("aptidao", AptidaoView.as_view()), *router.urls]
