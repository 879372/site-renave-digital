from django.urls import path

from . import views

urlpatterns = [
    path("consultas", views.buscars_webhook),
    path("comunicacao/<str:token>", views.carven_webhook),
    path("asaas", views.asaas_webhook),
    path("zapsign/<str:token>", views.zapsign_webhook),
]
