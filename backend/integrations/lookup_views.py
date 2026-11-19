from rest_framework import permissions
from rest_framework.exceptions import NotFound
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from . import lookups


class LookupView(APIView):
    permission_classes = [permissions.AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "lookup"


class CompanyLookupView(LookupView):
    def get(self, request, cnpj: str):
        result = lookups.company(cnpj)
        if not result:
            raise NotFound("Não encontramos dados para este CNPJ. Preencha manualmente.")
        return Response(result)


class AddressLookupView(LookupView):
    def get(self, request, cep: str):
        result = lookups.address(cep)
        if not result:
            raise NotFound("CEP não encontrado.")
        return Response(result)
