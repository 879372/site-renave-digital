from django.http import HttpResponse
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from audit.service import record
from organizations.models import ClientCompany
from organizations.tenancy import OrganizationPermission, resolve_membership

from . import service
from .models import StockVehicle
from .serializers import (
    AptidaoSerializer,
    AtpvAssinadaSerializer,
    EntradaSerializer,
    NotaFiscalSerializer,
    SaidaSerializer,
    StockVehicleDetailSerializer,
    StockVehicleSerializer,
)

DOC_KINDS = {"termo_entrada", "termo_saida", "crlve", "atpv"}


def _client(request, client_id):
    if not client_id:
        return None
    client = ClientCompany.objects.filter(organization=request.organization, public_id=client_id, is_active=True).first()
    if client is None:
        raise NotFound("Cliente não encontrado.")
    return client


class AptidaoView(APIView):
    permission_classes = [OrganizationPermission]
    required_perm = "renave.operate"

    def post(self, request):
        s = AptidaoSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        result = service.aptidao(
            organization=request.organization,
            client_company=_client(request, d.get("client_id")),
            user=request.user,
            placa=d["placa"],
            renavam=d["renavam"],
            crv=d["crv"],
            tipo_crv=d["tipo_crv"],
        )
        return Response({"veiculo": result})


class StockViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    permission_classes = [OrganizationPermission]
    required_perms = {
        "list": "view",
        "retrieve": "view",
        "documento": "view",
        "create": "renave.operate",
        "sync": "renave.operate",
        "saida": "renave.operate",
        "cancelar_entrada": "renave.operate",
        "cancelar_saida": "renave.operate",
        "nota_fiscal": "renave.operate",
        "atpv_assinada": "renave.operate",
    }
    lookup_field = "public_id"
    lookup_value_regex = "[0-9a-f-]{36}"
    filterset_fields = ["state"]

    def get_queryset(self):
        resolve_membership(self.request)
        qs = StockVehicle.objects.filter(organization=self.request.organization).select_related("client")
        if search := self.request.query_params.get("search"):
            qs = qs.filter(placa__icontains=search.replace("-", "").upper())
        if client_id := self.request.query_params.get("client"):
            qs = qs.filter(client__public_id=client_id)
        return qs

    def get_serializer_class(self):
        return StockVehicleDetailSerializer if self.action == "retrieve" else StockVehicleSerializer

    def create(self, request):
        s = EntradaSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        vehicle = service.entrada(
            organization=request.organization,
            client_company=_client(request, s.validated_data.get("client_id")),
            user=request.user,
            data=s.validated_data,
        )
        record("renave.entrada", request=request, target=vehicle, placa=vehicle.placa)
        return Response(StockVehicleDetailSerializer(vehicle).data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["post"])
    def sync(self, request):
        result = service.sync_stock(request.organization, _client(request, request.data.get("client_id")))
        return Response(result)

    @action(detail=True, methods=["post"])
    def saida(self, request, public_id=None):
        vehicle = self.get_object()
        s = SaidaSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        service.saida(vehicle=vehicle, user=request.user, data=s.validated_data)
        record("renave.saida", request=request, target=vehicle, tipo=s.validated_data["tipo_transferencia"])
        return Response(StockVehicleDetailSerializer(vehicle).data)

    @action(detail=True, methods=["post"], url_path="cancelar-entrada")
    def cancelar_entrada(self, request, public_id=None):
        vehicle = service.cancelar_entrada(vehicle=self.get_object(), user=request.user)
        record("renave.cancelar_entrada", request=request, target=vehicle)
        return Response(StockVehicleDetailSerializer(vehicle).data)

    @action(detail=True, methods=["post"], url_path="cancelar-saida")
    def cancelar_saida(self, request, public_id=None):
        vehicle = service.cancelar_saida(vehicle=self.get_object(), user=request.user)
        record("renave.cancelar_saida", request=request, target=vehicle)
        return Response(StockVehicleDetailSerializer(vehicle).data)

    @action(detail=True, methods=["post"], url_path="nota-fiscal")
    def nota_fiscal(self, request, public_id=None):
        vehicle = self.get_object()
        s = NotaFiscalSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        service.enviar_nota(vehicle=vehicle, user=request.user, **s.validated_data)
        record("renave.nota_fiscal", request=request, target=vehicle, evento=s.validated_data["evento"])
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["post"], url_path="atpv-assinada")
    def atpv_assinada(self, request, public_id=None):
        vehicle = self.get_object()
        s = AtpvAssinadaSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        service.enviar_atpv_assinada(
            vehicle=vehicle,
            user=request.user,
            tipo_assinatura=s.validated_data["tipo_assinatura"],
            arquivo=s.validated_data["arquivo"].read(),
        )
        record("renave.atpv_assinada", request=request, target=vehicle)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["get"], url_path=r"documentos/(?P<kind>[a-z_]+)")
    def documento(self, request, public_id=None, kind=None):
        if kind not in DOC_KINDS:
            raise ValidationError("Documento inválido.")
        content, content_type, filename = service.documento(vehicle=self.get_object(), kind=kind)
        response = HttpResponse(content, content_type=content_type)
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response
