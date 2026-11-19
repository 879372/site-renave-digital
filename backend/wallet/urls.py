from django.urls import path
from rest_framework.routers import SimpleRouter

from . import views

router = SimpleRouter(trailing_slash=False)
router.register("entries", views.LedgerViewSet, basename="ledger")
router.register("topups", views.TopUpViewSet, basename="topups")

urlpatterns = [path("", views.WalletView.as_view()), path("prices", views.PriceListView.as_view()), *router.urls]
