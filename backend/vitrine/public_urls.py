from django.urls import path

from . import views

S = "lojas/<str:slug>"
urlpatterns = [
    path(S, views.PublicSiteView.as_view()),
    path(f"{S}/veiculos", views.PublicVehiclesView.as_view()),
    path(f"{S}/veiculos/<uuid:vehicle_id>", views.PublicVehiclesView.as_view()),
    path(f"{S}/contato", views.PublicContactView.as_view()),
    path("feed/<str:slug>/<str:token>.xml", views.FeedView.as_view()),
]
