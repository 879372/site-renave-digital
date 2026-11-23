from django.conf import settings
from django.db.models import Prefetch, Q
from rest_framework import serializers, status
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from audit.service import record
from billing.entitlements import require_feature
from billing.permissions import PlanFeaturePermission
from core import documents
from core.exceptions import ProviderUnavailable
from core.viewsets import OrgViewSet
from integrations.fipe import TYPES, FipeClient
from integrations.http import ProviderError
from organizations.tenancy import OrganizationPermission

from . import service
from .models import Avaliacao, AvaliacaoFoto, Vehicle, VehicleDocument, VehiclePhoto
from .serializers import (
    AvaliacaoSerializer,
    CostSerializer,
    DocumentSerializer,
    PhotoSerializer,
    VehicleListSerializer,
    VehicleSerializer,
)

DOC_TYPES = {"application/pdf", "image/jpeg", "image/png", "image/webp"}


class RenaveEntrySerializer(serializers.Serializer):
    renavam = serializers.CharField(max_length=11)
    crv = serializers.CharField(max_length=20)
    codigo_seguranca_crv = serializers.CharField(max_length=20)
    tipo_crv = serializers.ChoiceField(choices=[("DIGITAL", "Digital"), ("FISICO", "Físico")], default="DIGITAL")
    km = serializers.IntegerField(min_value=0)
    data_hora_km = serializers.DateTimeField()
    data_compra = serializers.DateField()
    tipo_operacao = serializers.ChoiceField(choices=["compra_veiculo", "entrada_veiculo_proprio"], default="compra_veiculo")
    vendedor_tipo = serializers.ChoiceField(choices=["fisica", "juridica"], required=False)
    vendedor_documento = serializers.CharField(max_length=18, required=False, allow_blank=True)
    valor_compra_cents = serializers.IntegerField(min_value=1, required=False)

    def validate(self, attrs):
        attrs["renavam"] = documents.only_digits(attrs["renavam"]).zfill(11)
        if attrs["tipo_operacao"] == "compra_veiculo":
            doc = documents.normalize_document(attrs.get("vendedor_documento", ""))
            if not documents.is_valid_document(doc):
                raise serializers.ValidationError({"vendedor_documento": "CPF/CNPJ do vendedor inválido."})
            if not attrs.get("valor_compra_cents"):
                raise serializers.ValidationError({"valor_compra_cents": "Informe o valor de compra."})
            attrs["vendedor_documento"] = doc
            attrs["vendedor_tipo"] = "fisica" if len(doc) == 11 else "juridica"
        return attrs


class VehicleViewSet(OrgViewSet):
    queryset = Vehicle.objects.all()
    required_feature = "estoque"
    write_perm = "estoque.manage"
    extra_perms = {
        "photos": "estoque.manage",
        "photo": "estoque.manage",
        "reorder_photos": "estoque.manage",
        "costs": "estoque.manage",
        "cost": "estoque.manage",
        "documents": "estoque.manage",
        "document": "view",
        "set_status": "estoque.manage",
        "renave_entry": "renave.operate",
        "link_renave": "estoque.manage",
        "plate": "view",
        "plate_usage": "view",
    }

    def get_serializer_class(self):
        return VehicleListSerializer if self.action == "list" else VehicleSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        if self.action == "list":
            qs = qs.prefetch_related(Prefetch("photos", queryset=VehiclePhoto.objects.order_by("position"), to_attr="prefetched_photos"))
            p = self.request.query_params
            if st := p.get("status"):
                qs = qs.filter(status__in=st.split(","))
            elif p.get("active") != "false":
                qs = qs.filter(status__in=Vehicle.ACTIVE)
            if own := p.get("ownership"):
                qs = qs.filter(ownership=own)
            if term := p.get("search", "").strip():
                plate = documents.normalize_plate(term)
                qs = qs.filter(
                    Q(marca__icontains=term) | Q(modelo__icontains=term) | Q(versao__icontains=term) | Q(placa__startswith=plate)
                )
            order = p.get("order", "-created_at")
            if order in {"-created_at", "created_at", "price_cents", "-price_cents", "entry_date", "-entry_date"}:
                qs = qs.order_by(order)
        else:
            qs = qs.select_related("consignor", "supplier", "renave").prefetch_related(
                "photos", "costs__supplier", "costs__payable", "documents"
            )
        return qs

    def perform_create(self, serializer):
        org = self.request.organization
        service.check_vehicle_limit(org)
        if serializer.validated_data.get("ownership") == Vehicle.Ownership.CONSIGNADO:
            require_feature(org, "consignacao")
        vehicle = serializer.save(organization=org)
        if not vehicle.entry_date:
            from django.utils import timezone

            vehicle.entry_date = vehicle.purchase_date or timezone.localdate()
            vehicle.save(update_fields=["entry_date"])
        record("estoque.criado", request=self.request, target=vehicle)

    def perform_update(self, serializer):
        if serializer.validated_data.get("ownership") == Vehicle.Ownership.CONSIGNADO:
            require_feature(self.request.organization, "consignacao")
        if serializer.instance.status == Vehicle.Status.VENDIDO and {"price_cents", "purchase_price_cents"} & set(
            serializer.validated_data
        ):
            raise ValidationError({"price_cents": "Veículo vendido: valores ficam congelados na venda."})
        serializer.save()

    def perform_destroy(self, instance):
        if instance.vendas.exists():
            raise ValidationError({"vehicle": "Veículo com vendas registradas não pode ser apagado."})
        if instance.lancamentos.filter(paid_at__isnull=False).exists():
            raise ValidationError({"vehicle": "Veículo com pagamentos no financeiro não pode ser apagado."})
        instance.lancamentos.filter(paid_at__isnull=True).delete()
        record("estoque.apagado", request=self.request, target=instance)
        instance.delete()

    # --- fotos ---

    @action(detail=True, methods=["post"])
    def photos(self, request, public_id=None):
        vehicle = self.get_object()
        files = request.FILES.getlist("files")
        if not files:
            raise ValidationError({"files": "Envie ao menos uma foto."})
        created = service.add_photos(vehicle, files)
        return Response(PhotoSerializer(created, many=True, context={"request": request}).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["delete"], url_path=r"photos/(?P<photo_id>[0-9a-f-]{36})")
    def photo(self, request, public_id=None, photo_id=None):
        vehicle = self.get_object()
        photo = vehicle.photos.filter(public_id=photo_id).first()
        if photo is None:
            raise NotFound("Foto não encontrada.")
        photo.image.delete(save=False)
        photo.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["post"], url_path="photos/reorder")
    def reorder_photos(self, request, public_id=None):
        vehicle = self.get_object()
        order = request.data.get("order") or []
        by_id = {str(p.public_id): p for p in vehicle.photos.all()}
        for pos, pid in enumerate(order):
            if photo := by_id.get(str(pid)):
                photo.position = pos
                photo.save(update_fields=["position"])
        return Response(PhotoSerializer(vehicle.photos.order_by("position"), many=True, context={"request": request}).data)

    # --- custos ---

    @action(detail=True, methods=["get", "post"])
    def costs(self, request, public_id=None):
        vehicle = self.get_object()
        if request.method == "GET":
            return Response(CostSerializer(vehicle.costs.select_related("supplier", "payable"), many=True).data)
        require_feature(request.organization, "custos")
        s = CostSerializer(data=request.data, context=self.get_serializer_context())
        s.is_valid(raise_exception=True)
        d = s.validated_data
        cost = service.add_cost(
            vehicle,
            category=d["category"],
            description=d["description"],
            amount_cents=d["amount_cents"],
            date=d["date"],
            supplier=d.get("supplier"),
            paid=d.get("paid", False),
            user=request.user,
        )
        return Response(CostSerializer(cost).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["delete"], url_path=r"costs/(?P<cost_id>[0-9a-f-]{36})")
    def cost(self, request, public_id=None, cost_id=None):
        vehicle = self.get_object()
        cost = vehicle.costs.filter(public_id=cost_id).select_related("payable").first()
        if cost is None:
            raise NotFound("Custo não encontrado.")
        service.remove_cost(cost)
        return Response(status=status.HTTP_204_NO_CONTENT)

    # --- documentos ---

    @action(detail=True, methods=["post"])
    def documents(self, request, public_id=None):
        vehicle = self.get_object()
        upload = request.FILES.get("file")
        if upload is None:
            raise ValidationError({"file": "Envie o arquivo."})
        if upload.size > settings.MAX_DOCUMENT_BYTES:
            raise ValidationError({"file": "Arquivo maior que 10 MB."})
        if upload.content_type not in DOC_TYPES:
            raise ValidationError({"file": "Envie PDF ou imagem."})
        kind = request.data.get("kind", VehicleDocument.Kind.OUTRO)
        if kind not in VehicleDocument.Kind.values:
            raise ValidationError({"kind": "Tipo de documento inválido."})
        doc = VehicleDocument.objects.create(
            organization=vehicle.organization, vehicle=vehicle, kind=kind, name=(request.data.get("name") or upload.name)[:120], file=upload
        )
        return Response(DocumentSerializer(doc, context={"request": request}).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["get", "delete"], url_path=r"documents/(?P<doc_id>[0-9a-f-]{36})")
    def document(self, request, public_id=None, doc_id=None):
        vehicle = self.get_object()
        doc = vehicle.documents.filter(public_id=doc_id).first()
        if doc is None:
            raise NotFound("Documento não encontrado.")
        if request.method == "GET":
            import mimetypes

            from django.http import FileResponse

            ctype = mimetypes.guess_type(doc.file.name)[0] or "application/octet-stream"
            resp = FileResponse(doc.file.open("rb"), content_type=ctype, as_attachment=False, filename=doc.name)
            resp["Cache-Control"] = "private, no-store"
            return resp
        if not request._membership.has_perm("estoque.manage"):
            from rest_framework.exceptions import PermissionDenied

            raise PermissionDenied("Seu perfil não tem permissão para esta ação.")
        doc.file.delete(save=False)
        doc.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    # --- situação e RENAVE ---

    @action(detail=True, methods=["post"], url_path="status")
    def set_status(self, request, public_id=None):
        vehicle = service.set_status(self.get_object(), str(request.data.get("status", "")), user=request.user)
        return Response(VehicleSerializer(vehicle, context=self.get_serializer_context()).data)

    @action(detail=True, methods=["post"], url_path="renave-entry")
    def renave_entry(self, request, public_id=None):
        vehicle = self.get_object()
        if not vehicle.placa:
            raise ValidationError({"placa": "Cadastre a placa do veículo antes de dar entrada no RENAVE."})
        s = RenaveEntrySerializer(data=request.data)
        s.is_valid(raise_exception=True)
        service.enter_renave(vehicle, user=request.user, data={**s.validated_data, "placa": vehicle.placa})
        vehicle.refresh_from_db()
        return Response(VehicleSerializer(vehicle, context=self.get_serializer_context()).data)

    @action(detail=True, methods=["post"], url_path="link-renave")
    def link_renave(self, request, public_id=None):
        """Liga a um registro do RENAVE já existente (ex.: entrada feita antes do cadastro comercial)."""
        from renave.models import StockVehicle

        vehicle = self.get_object()
        stock = StockVehicle.objects.filter(organization=request.organization, public_id=request.data.get("renave_id")).first()
        if stock is None:
            raise NotFound("Registro do RENAVE não encontrado.")
        if hasattr(stock, "commercial") and stock.commercial.pk != vehicle.pk:
            raise ValidationError({"renave_id": "Este registro já está ligado a outro veículo."})
        vehicle.renave = stock
        vehicle.save(update_fields=["renave", "updated_at"])
        return Response(VehicleSerializer(vehicle, context=self.get_serializer_context()).data)

    # --- placa ---

    @action(detail=False, methods=["get"], url_path=r"plate/(?P<placa>[A-Za-z0-9-]{7,8})")
    def plate(self, request, placa=None):
        placa = documents.normalize_plate(placa)
        if not documents.is_valid_plate(placa):
            raise ValidationError({"placa": "Placa inválida."})
        return Response(service.plate_lookup(request.organization, placa, user=request.user))

    @action(detail=False, methods=["get"], url_path="plate-usage")
    def plate_usage(self, request):
        return Response(service.plate_usage(request.organization))


class FipeView(APIView):
    """Navegação na tabela FIPE: /fipe/<tipo>/marcas, .../modelos, .../anos, .../preco."""

    permission_classes = [OrganizationPermission, PlanFeaturePermission]
    required_perm = "view"
    required_feature = "estoque"

    def get(self, request, kind, brand=None, model=None, year=None, code=None):
        if kind not in TYPES:
            raise NotFound("Tipo de veículo inválido.")
        client = FipeClient(request.organization)
        try:
            if code and year:
                return Response(client.price_by_code(kind, code, year))
            if code:
                return Response(client.years_by_code(kind, code))
            if year:
                return Response(client.price(kind, brand, model, year))
            if model:
                return Response(client.years(kind, brand, model))
            if brand:
                return Response(client.models(kind, brand))
            return Response(client.brands(kind))
        except ProviderError:
            raise ProviderUnavailable("A tabela FIPE não respondeu agora. Tente de novo em instantes.")


class AvaliacaoViewSet(OrgViewSet):
    queryset = Avaliacao.objects.select_related("cliente", "evaluator", "vehicle").prefetch_related("photos")
    serializer_class = AvaliacaoSerializer
    required_feature = "avaliacao"
    write_perm = "vendas.operate"
    extra_perms = {"approve": "estoque.manage", "refuse": "estoque.manage", "buy": "estoque.manage", "photos": "vendas.operate"}

    def get_queryset(self):
        qs = super().get_queryset()
        if st := self.request.query_params.get("status"):
            qs = qs.filter(status=st)
        if term := self.request.query_params.get("search", "").strip():
            qs = qs.filter(
                Q(marca__icontains=term) | Q(modelo__icontains=term) | Q(placa__icontains=term) | Q(cliente__nome__icontains=term)
            )
        return qs

    def perform_create(self, serializer):
        serializer.save(organization=self.request.organization, evaluator=self.request.user)

    def perform_destroy(self, instance):
        if instance.status == Avaliacao.Status.COMPRADA:
            raise ValidationError({"status": "Avaliação comprada não pode ser apagada."})
        instance.delete()

    def _set(self, request, status_value):
        av = self.get_object()
        if av.status == Avaliacao.Status.COMPRADA:
            raise ValidationError({"status": "Avaliação já comprada."})
        if "offer_cents" in request.data:
            av.offer_cents = int(request.data["offer_cents"])
        av.status = status_value
        av.approved_by = request.user if status_value == Avaliacao.Status.APROVADA else None
        av.save(update_fields=["status", "approved_by", "offer_cents", "updated_at"])
        record(f"avaliacao.{status_value}", request=request, target=av, offer_cents=av.offer_cents)
        return Response(self.get_serializer(av).data)

    @action(detail=True, methods=["post"])
    def approve(self, request, public_id=None):
        return self._set(request, Avaliacao.Status.APROVADA)

    @action(detail=True, methods=["post"])
    def refuse(self, request, public_id=None):
        return self._set(request, Avaliacao.Status.RECUSADA)

    @action(detail=True, methods=["post"])
    def buy(self, request, public_id=None):
        av = self.get_object()
        if av.status != Avaliacao.Status.APROVADA:
            raise ValidationError({"status": "Aprove a avaliação antes de comprar."})
        price = request.data.get("price_cents")
        vehicle = service.buy_from_evaluation(
            av, user=request.user, price_cents=int(price) if price not in (None, "") else None, paid=bool(request.data.get("paid"))
        )
        return Response({"vehicle_id": str(vehicle.public_id)}, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def photos(self, request, public_id=None):
        av = self.get_object()
        files = request.FILES.getlist("files")
        if not files:
            raise ValidationError({"files": "Envie ao menos uma foto."})
        if av.photos.count() + len(files) > 30:
            raise ValidationError({"files": "Até 30 fotos por avaliação."})
        for f in files:
            photo = AvaliacaoFoto(organization=av.organization, avaliacao=av, label=str(request.data.get("label", ""))[:60])
            photo.image.save("foto.jpg", service.process_image(f), save=False)
            photo.save()
        return Response(self.get_serializer(av).data, status=status.HTTP_201_CREATED)
