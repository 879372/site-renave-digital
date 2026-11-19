from django.http import HttpResponse
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from audit.service import record
from core.pagination import CreatedCursorPagination
from organizations.tenancy import OrganizationPermission, resolve_membership
from renave.models import StockVehicle

from . import service
from .models import ComunicacaoVenda
from .serializers import ComunicacaoCreateSerializer, ComunicacaoSerializer


class ComunicacaoViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    serializer_class = ComunicacaoSerializer
    permission_classes = [OrganizationPermission]
    required_perms = {
        "list": "view",
        "retrieve": "view",
        "comprovante": "view",
        "motivos": "view",
        "refresh": "view",
        "create": "comunicacao.operate",
        "transmitir": "comunicacao.operate",
        "cancelar": "comunicacao.operate",
    }
    pagination_class = CreatedCursorPagination
    lookup_field = "public_id"
    lookup_value_regex = "[0-9a-f-]{36}"
    filterset_fields = ["situacao"]

    def get_queryset(self):
        resolve_membership(self.request)
        qs = ComunicacaoVenda.objects.filter(organization=self.request.organization).select_related("user")
        if search := self.request.query_params.get("search"):
            qs = qs.filter(placa__icontains=search.replace("-", "").upper())
        return qs

    def create(self, request):
        s = ComunicacaoCreateSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        vehicle = None
        if vid := s.validated_data.get("vehicle_id"):
            vehicle = StockVehicle.objects.filter(organization=request.organization, public_id=vid).first()
        cv = service.criar(organization=request.organization, user=request.user, data=s.validated_data, vehicle=vehicle)
        record("comunicacao.criada", request=request, target=cv, placa=cv.placa)
        return Response(ComunicacaoSerializer(cv).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def transmitir(self, request, public_id=None):
        cv = service.transmitir(self.get_object(), request.user)
        record("comunicacao.transmitida", request=request, target=cv)
        return Response(ComunicacaoSerializer(cv).data)

    @action(detail=True, methods=["post"])
    def refresh(self, request, public_id=None):
        return Response(ComunicacaoSerializer(service.refresh(self.get_object())).data)

    @action(detail=True, methods=["get"])
    def motivos(self, request, public_id=None):
        return Response(service.motivos_cancelamento(self.get_object()))

    @action(detail=True, methods=["post"])
    def cancelar(self, request, public_id=None):
        cv = service.cancelar(self.get_object(), str(request.data.get("id_motivo_cancelamento", "")))
        record("comunicacao.cancelada", request=request, target=cv)
        return Response(ComunicacaoSerializer(cv).data)

    @action(detail=True, methods=["get"])
    def comprovante(self, request, public_id=None):
        cv = self.get_object()
        response = HttpResponse(service.comprovante(cv), content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="comprovante_{cv.placa}.pdf"'
        return response
