from django.urls import path

from . import branches

urlpatterns = [
    path("", branches.BranchesView.as_view()),
    path("transferir", branches.TransferVehicleView.as_view()),
]
