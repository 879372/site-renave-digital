from django.http import HttpResponse
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound
from rest_framework.response import Response
from rest_framework.views import APIView

from audit.service import record
from core.pagination import CreatedCursorPagination
from organizations.tenancy import OrganizationPermission, resolve_membership
from renave.models import StockVehicle

from . import service
from .models import NotaFiscal
from .serializers import FiscalSettingsSerializer, NotaCreateSerializer, NotaSerializer


class FiscalSettingsView(APIView):
    permission_classes = [OrganizationPermission]
    required_perms = {"get": "view", "put": "fiscal.configure", "patch": "fiscal.configure"}

    def get(self, request):
        return Response(FiscalSettingsSerializer(service.get_settings(request.organization)).data)

    def patch(self, request):
        s = FiscalSettingsSerializer(service.get_settings(request.organization), data=request.data, partial=True)
        s.is_valid(raise_exception=True)
        s.save()
        record("fiscal.settings_updated", request=request, fields=list(request.data))
        return Response(s.data)


class NotaViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    serializer_class = NotaSerializer
    permission_classes = [OrganizationPermission]
    required_perms = {
        "list": "view",
        "retrieve": "view",
        "xml": "view",
        "pdf": "view",
        "create": "fiscal.emit",
        "reenviar": "fiscal.emit",
        "cancelar": "fiscal.emit",
        "carta_correcao": "fiscal.emit",
    }
    pagination_class = CreatedCursorPagination
    lookup_field = "public_id"
    lookup_value_regex = "[0-9a-f-]{36}"
    filterset_fields = ["status", "tipo"]

    def get_queryset(self):
        resolve_membership(self.request)
        qs = NotaFiscal.objects.filter(organization=self.request.organization).select_related("vehicle")
        if search := self.request.query_params.get("search"):
            qs = qs.filter(destinatario_nome__icontains=search) | qs.filter(chave__startswith=search)
        return qs

    def create(self, request):
        s = NotaCreateSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        vehicle = None
        if vid := s.validated_data.get("vehicle_id"):
            vehicle = StockVehicle.objects.filter(organization=request.organization, public_id=vid).first()
            if vehicle is None:
                raise NotFound("Veículo não encontrado no estoque.")
        nota = service.criar(organization=request.organization, user=request.user, data=s.validated_data, vehicle=vehicle)
        record("fiscal.nfe_criada", request=request, target=nota, numero=nota.numero, tipo=nota.tipo)
        return Response(NotaSerializer(nota).data, status=status.HTTP_202_ACCEPTED)

    @action(detail=True, methods=["post"])
    def reenviar(self, request, public_id=None):
        nota = service.reenviar(self.get_object(), request.user)
        return Response(NotaSerializer(nota).data, status=status.HTTP_202_ACCEPTED)

    @action(detail=True, methods=["post"])
    def cancelar(self, request, public_id=None):
        nota = service.cancelar(self.get_object(), str(request.data.get("justificativa", "")))
        record("fiscal.nfe_cancelada", request=request, target=nota)
        return Response(NotaSerializer(nota).data)

    @action(detail=True, methods=["post"], url_path="carta-correcao")
    def carta_correcao(self, request, public_id=None):
        nota = service.carta_correcao(self.get_object(), str(request.data.get("texto", "")))
        record("fiscal.nfe_cce", request=request, target=nota, sequencia=nota.cce_count)
        return Response(NotaSerializer(nota).data)

    @action(detail=True, methods=["get"])
    def xml(self, request, public_id=None):
        nota = self.get_object()
        if not nota.xml:
            raise NotFound("XML indisponível.")
        response = HttpResponse(bytes(nota.xml), content_type="application/xml")
        response["Content-Disposition"] = f'attachment; filename="{nota.chave or nota.numero}.xml"'
        return response

    @action(detail=True, methods=["get"])
    def pdf(self, request, public_id=None):
        nota = self.get_object()
        if not nota.pdf:
            raise NotFound("DANFE indisponível.")
        response = HttpResponse(bytes(nota.pdf), content_type="application/pdf")
        response["Content-Disposition"] = f'inline; filename="danfe_{nota.numero}.pdf"'
        return response
