from rest_framework import serializers, status
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from audit.service import record
from billing.entitlements import require_feature
from core.exceptions import ProviderUnavailable
from core.fields import OrgRelatedField
from core.viewsets import OrgViewSet
from estoque.models import Vehicle
from integrations.http import ProviderError
from pessoas.models import Pessoa
from vendas.models import Venda

from . import service
from .models import Documento, Modelo


class ModeloSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="public_id", read_only=True)
    kind_display = serializers.CharField(source="get_kind_display", read_only=True)

    class Meta:
        model = Modelo
        fields = ["id", "kind", "kind_display", "title", "body", "is_active"]


class DocumentoSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="public_id", read_only=True)
    kind_display = serializers.CharField(source="get_kind_display", read_only=True)
    signature_display = serializers.CharField(source="get_signature_status_display", read_only=True)
    vehicle_id = serializers.UUIDField(source="vehicle.public_id", read_only=True, default=None)
    venda_id = serializers.UUIDField(source="venda.public_id", read_only=True, default=None)
    pessoa_name = serializers.CharField(source="pessoa.nome", read_only=True, default=None)

    class Meta:
        model = Documento
        fields = [
            "id",
            "kind",
            "kind_display",
            "title",
            "content",
            "vehicle_id",
            "venda_id",
            "pessoa_name",
            "signature_status",
            "signature_display",
            "signature_links",
            "signed_file_url",
            "created_at",
        ]
        read_only_fields = [f for f in fields if f not in ("title", "content")]


class GenerateSerializer(serializers.Serializer):
    modelo = OrgRelatedField(Modelo)
    venda = OrgRelatedField(Venda, required=False, allow_null=True)
    vehicle = OrgRelatedField(Vehicle, required=False, allow_null=True)
    pessoa = OrgRelatedField(Pessoa, required=False, allow_null=True)


class SignerSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=150)
    email = serializers.EmailField(required=False, allow_blank=True)
    phone = serializers.CharField(max_length=20, required=False, allow_blank=True)


class ModeloViewSet(OrgViewSet):
    queryset = Modelo.objects.all()
    serializer_class = ModeloSerializer
    required_feature = "contratos"
    write_perm = "org.manage"
    pagination_class = None

    def get_queryset(self):
        service.ensure_defaults(self.request.organization)
        return super().get_queryset()


class DocumentoViewSet(OrgViewSet):
    queryset = Documento.objects.select_related("vehicle", "venda", "pessoa")
    serializer_class = DocumentoSerializer
    required_feature = "contratos"
    write_perm = "vendas.operate"
    extra_perms = {"generate": "vendas.operate", "sign": "vendas.operate"}
    http_method_names = ["get", "post", "patch", "delete"]

    def get_queryset(self):
        qs = super().get_queryset()
        p = self.request.query_params
        if v := p.get("venda"):
            qs = qs.filter(venda__public_id=v)
        if v := p.get("vehicle"):
            qs = qs.filter(vehicle__public_id=v)
        return qs

    def create(self, request, *args, **kwargs):
        raise ValidationError({"detail": "Use /generate para criar um documento a partir de um modelo."})

    def perform_update(self, serializer):
        if serializer.instance.signature_status in (Documento.Signature.PENDING, Documento.Signature.SIGNED):
            raise ValidationError({"content": "Documento enviado para assinatura não pode ser editado."})
        serializer.save()

    @action(detail=False, methods=["post"])
    def generate(self, request):
        s = GenerateSerializer(data=request.data, context=self.get_serializer_context())
        s.is_valid(raise_exception=True)
        d = s.validated_data
        if not (d.get("venda") or d.get("vehicle") or d.get("pessoa")):
            raise ValidationError({"venda": "Escolha a venda, o veículo ou a pessoa do documento."})
        doc = service.generate(d["modelo"], user=request.user, venda=d.get("venda"), vehicle=d.get("vehicle"), pessoa=d.get("pessoa"))
        record("contratos.gerado", request=request, target=doc, kind=doc.kind)
        return Response(self.get_serializer(doc).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def sign(self, request, public_id=None):
        require_feature(request.organization, "assinatura")
        doc = self.get_object()
        s = SignerSerializer(data=request.data.get("signers", []), many=True)
        s.is_valid(raise_exception=True)
        try:
            doc = service.send_for_signature(doc, s.validated_data)
        except ProviderError as exc:
            raise ProviderUnavailable(f"A assinatura eletrônica recusou o envio: {exc}")
        record("contratos.assinatura_enviada", request=request, target=doc)
        return Response(self.get_serializer(doc).data)
