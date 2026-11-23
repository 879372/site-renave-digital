from django.urls import path
from rest_framework.routers import SimpleRouter

from . import views

router = SimpleRouter(trailing_slash=False)
router.register("invoices", views.InvoiceViewSet, basename="invoices")

urlpatterns = [
    path("plans", views.PlanListView.as_view()),
    path("me", views.BillingMeView.as_view()),
    path("change-plan", views.ChangePlanView.as_view()),
    *router.urls,
]
