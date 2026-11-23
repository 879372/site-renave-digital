from django.urls import path

from . import views

urlpatterns = [
    path("dashboard", views.DashboardView.as_view()),
    path("relatorios", views.RelatoriosView.as_view()),
]
