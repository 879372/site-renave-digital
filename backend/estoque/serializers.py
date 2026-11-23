from django.utils import timezone
from rest_framework import serializers

from core import documents
from core.fields import OrgRelatedField
from pessoas.models import Pessoa

from .models import Avaliacao, AvaliacaoFoto, Vehicle, VehicleCost, VehicleDocument, VehiclePhoto


def file_url(request, field) -> str | None:
    if not field:
        return None
    url = field.url
    return request.build_absolute_uri(url) if request and url.startswith("/") else url


class PhotoSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="public_id", read_only=True)
    url = serializers.SerializerMethodField()

    class Meta:
        model = VehiclePhoto
        fields = ["id", "url", "position"]

    def get_url(self, obj):
        return file_url(self.context.get("request"), obj.image)


class CostSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="public_id", read_only=True)
    supplier = OrgRelatedField(Pessoa, required=False, allow_null=True)
    supplier_name = serializers.CharField(source="supplier.nome", read_only=True, default=None)
    category_display = serializers.CharField(source="get_category_display", read_only=True)
    paid = serializers.BooleanField(write_only=True, default=False)
    payable_status = serializers.CharField(source="payable.status", read_only=True, default=None)

    class Meta:
        model = VehicleCost
        fields = [
            "id",
            "category",
            "category_display",
            "description",
            "supplier",
            "supplier_name",
            "amount_cents",
            "date",
            "paid",
            "payable_status",
            "created_at",
        ]


class DocumentSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="public_id", read_only=True)
    url = serializers.SerializerMethodField()
    kind_display = serializers.CharField(source="get_kind_display", read_only=True)

    class Meta:
        model = VehicleDocument
        fields = ["id", "kind", "kind_display", "name", "url", "created_at"]

    def get_url(self, obj):
        # Documento sai só pela API autenticada (nunca link direto do arquivo).
        return f"/api/estoque/veiculos/{obj.vehicle.public_id}/documents/{obj.public_id}"


def _clean_vehicle(attrs):
    if "placa" in attrs and attrs["placa"]:
        attrs["placa"] = documents.normalize_plate(attrs["placa"])
        if not documents.is_valid_plate(attrs["placa"]):
            raise serializers.ValidationError({"placa": "Placa inválida."})
    if attrs.get("chassi"):
        attrs["chassi"] = attrs["chassi"].replace(" ", "").upper()
        if not documents.is_valid_vin(attrs["chassi"]):
            raise serializers.ValidationError({"chassi": "Chassi inválido."})
    if attrs.get("renavam"):
        attrs["renavam"] = documents.only_digits(attrs["renavam"]).zfill(11)
        if not documents.is_valid_renavam(attrs["renavam"]):
            raise serializers.ValidationError({"renavam": "RENAVAM inválido."})
    year = timezone.localdate().year + 1
    for f in ("ano_fabricacao", "ano_modelo"):
        if attrs.get(f) and not 1950 <= attrs[f] <= year:
            raise serializers.ValidationError({f: "Ano inválido."})
    return attrs


class VehicleListSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="public_id", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    cover = serializers.SerializerMethodField()
    days_in_stock = serializers.SerializerMethodField()
    total_cost_cents = serializers.IntegerField(read_only=True, source="total_cost_annot", default=None)

    class Meta:
        model = Vehicle
        fields = [
            "id",
            "title",
            "marca",
            "modelo",
            "versao",
            "placa",
            "ano_fabricacao",
            "ano_modelo",
            "cor",
            "km",
            "status",
            "status_display",
            "ownership",
            "price_cents",
            "fipe_price_cents",
            "purchase_price_cents",
            "total_cost_cents",
            "cover",
            "days_in_stock",
            "published",
            "entry_date",
            "sold_at",
        ]

    def get_cover(self, obj):
        photos = getattr(obj, "prefetched_photos", None)
        photo = photos[0] if photos else None
        return file_url(self.context.get("request"), photo.image) if photo else None

    def get_days_in_stock(self, obj):
        if not obj.entry_date:
            return None
        end = obj.sold_at or timezone.localdate()
        return (end - obj.entry_date).days


class VehicleSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="public_id", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    consignor = OrgRelatedField(Pessoa, required=False, allow_null=True)
    consignor_name = serializers.CharField(source="consignor.nome", read_only=True, default=None)
    supplier = OrgRelatedField(Pessoa, required=False, allow_null=True)
    supplier_name = serializers.CharField(source="supplier.nome", read_only=True, default=None)
    photos = PhotoSerializer(many=True, read_only=True)
    costs = CostSerializer(many=True, read_only=True)
    documents = DocumentSerializer(many=True, read_only=True)
    renave = serializers.SerializerMethodField()
    summary = serializers.SerializerMethodField()

    class Meta:
        model = Vehicle
        fields = [
            "id",
            "title",
            "kind",
            "placa",
            "renavam",
            "chassi",
            "marca",
            "modelo",
            "versao",
            "ano_fabricacao",
            "ano_modelo",
            "cor",
            "combustivel",
            "cambio",
            "km",
            "portas",
            "opcionais",
            "descricao",
            "status",
            "status_display",
            "ownership",
            "consignor",
            "consignor_name",
            "consignment_mode",
            "consignment_value",
            "consignment_until",
            "supplier",
            "supplier_name",
            "purchase_date",
            "purchase_price_cents",
            "entry_date",
            "price_cents",
            "min_price_cents",
            "fipe_code",
            "fipe_price_cents",
            "fipe_reference",
            "sold_at",
            "published",
            "featured",
            "location",
            "keys",
            "photos",
            "costs",
            "documents",
            "renave",
            "summary",
            "created_at",
        ]
        read_only_fields = ["status", "sold_at"]

    def validate(self, attrs):
        attrs = _clean_vehicle(attrs)
        ownership = attrs.get("ownership", getattr(self.instance, "ownership", Vehicle.Ownership.PROPRIO))
        if ownership == Vehicle.Ownership.CONSIGNADO:
            consignor = attrs.get("consignor", getattr(self.instance, "consignor", None))
            mode = attrs.get("consignment_mode", getattr(self.instance, "consignment_mode", ""))
            if not consignor:
                raise serializers.ValidationError({"consignor": "Informe o dono do veículo consignado."})
            if mode not in Vehicle.ConsignmentMode.values:
                raise serializers.ValidationError({"consignment_mode": "Escolha como a loja ganha no consignado."})
        if not isinstance(attrs.get("opcionais", []), list):
            raise serializers.ValidationError({"opcionais": "Lista de opcionais inválida."})
        return attrs

    def get_renave(self, obj):
        if not obj.renave_id:
            return None
        r = obj.renave
        return {"id": str(r.public_id), "state": r.state, "state_display": r.get_state_display()}

    def get_summary(self, obj):
        costs = obj.costs_total()
        total = obj.total_cost()
        price = obj.price_cents or 0
        payout = obj.consignor_payout(price)
        return {
            "costs_cents": costs,
            "total_cost_cents": total,
            "expected_profit_cents": price - total - payout if price else None,
            "consignor_payout_cents": payout,
            "days_in_stock": (timezone.localdate() - obj.entry_date).days if obj.entry_date and not obj.sold_at else None,
        }


class AvaliacaoFotoSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="public_id", read_only=True)
    url = serializers.SerializerMethodField()

    class Meta:
        model = AvaliacaoFoto
        fields = ["id", "url", "label"]

    def get_url(self, obj):
        return file_url(self.context.get("request"), obj.image)


class AvaliacaoSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="public_id", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    cliente = OrgRelatedField(Pessoa, required=False, allow_null=True)
    cliente_name = serializers.CharField(source="cliente.nome", read_only=True, default=None)
    evaluator_name = serializers.CharField(source="evaluator.full_name", read_only=True, default=None)
    photos = AvaliacaoFotoSerializer(many=True, read_only=True)
    vehicle_id = serializers.UUIDField(source="vehicle.public_id", read_only=True, default=None)
    max_offer_cents = serializers.SerializerMethodField()

    class Meta:
        model = Avaliacao
        fields = [
            "id",
            "status",
            "status_display",
            "cliente",
            "cliente_name",
            "evaluator_name",
            "kind",
            "placa",
            "marca",
            "modelo",
            "versao",
            "ano_fabricacao",
            "ano_modelo",
            "cor",
            "km",
            "checklist",
            "notes",
            "fipe_code",
            "fipe_price_cents",
            "estimated_repairs_cents",
            "offer_cents",
            "max_offer_cents",
            "photos",
            "vehicle_id",
            "created_at",
        ]
        read_only_fields = ["status"]

    def validate(self, attrs):
        attrs = _clean_vehicle(attrs)
        if not isinstance(attrs.get("checklist", {}), dict):
            raise serializers.ValidationError({"checklist": "Checklist inválido."})
        if self.instance and self.instance.status == Avaliacao.Status.COMPRADA:
            raise serializers.ValidationError({"status": "Avaliação já virou veículo: não pode ser alterada."})
        return attrs

    def get_max_offer_cents(self, obj):
        """Sugestão: 85% da FIPE menos os reparos estimados (margem para revenda)."""
        if not obj.fipe_price_cents:
            return None
        return max(obj.fipe_price_cents * 85 // 100 - obj.estimated_repairs_cents, 0)
