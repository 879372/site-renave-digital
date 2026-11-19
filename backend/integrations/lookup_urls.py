from django.urls import path

from .lookup_views import AddressLookupView, CompanyLookupView

urlpatterns = [
    path("cnpj/<str:cnpj>", CompanyLookupView.as_view()),
    path("cep/<str:cep>", AddressLookupView.as_view()),
]
