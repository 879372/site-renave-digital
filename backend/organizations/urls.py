from django.urls import path
from rest_framework.routers import SimpleRouter

from . import views

router = SimpleRouter(trailing_slash=False)
router.register("members", views.MemberViewSet, basename="members")
router.register("invitations", views.InvitationViewSet, basename="invitations")
router.register("clients", views.ClientCompanyViewSet, basename="clients")

urlpatterns = [
    path("", views.OrganizationCreateView.as_view()),
    path("current", views.CurrentOrganizationView.as_view()),
    path("invitations/accept", views.AcceptInvitationView.as_view()),
    *router.urls,
]
