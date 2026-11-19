from django.utils import timezone
from rest_framework import serializers

from accounts.models import User
from audit.models import AuditEvent
from comunicacao.models import ComunicacaoVenda
from consultas.models import Consulta, Product
from fiscal.models import NotaFiscal
from integrations.models import IntegrationCall, WebhookDelivery
from organizations.models import Membership, Organization
from renave.models import RenaveOperation, StockVehicle
from vault.models import Certificate
from wallet.models import LedgerEntry, ServicePrice, TopUp


class OrgRefField(serializers.Field):
    """Representa uma empresa como {id, name, cnpj}."""

    def __init__(self, **kwargs):
        kwargs.setdefault("read_only", True)
        super().__init__(**kwargs)

    def to_representation(self, org):
        if org is None:
            return None
        return {"id": str(org.public_id), "name": str(org), "cnpj": org.cnpj}


class OrganizationListSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="public_id", read_only=True)
    balance_cents = serializers.IntegerField(source="wallet.balance_cents", default=0, read_only=True)
    members_count = serializers.IntegerField(read_only=True)
    owner = serializers.SerializerMethodField()

    class Meta:
        model = Organization
        fields = [
            "id",
            "cnpj",
            "legal_name",
            "trade_name",
            "kind",
            "uf",
            "city",
            "is_active",
            "balance_cents",
            "members_count",
            "owner",
            "created_at",
        ]

    def get_owner(self, obj):
        m = next((m for m in obj.memberships.all() if m.role == "owner"), None)
        return {"name": m.user.full_name, "email": m.user.email} if m else None


class OrganizationDetailSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="public_id", read_only=True)

    class Meta:
        model = Organization
        exclude = ["public_id"]
        read_only_fields = ["cnpj", "created_at", "updated_at"]


class MemberAdminSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="public_id", read_only=True)
    user_id = serializers.UUIDField(source="user.public_id", read_only=True)
    email = serializers.EmailField(source="user.email", read_only=True)
    full_name = serializers.CharField(source="user.full_name", read_only=True)
    organization = OrgRefField()

    class Meta:
        model = Membership
        fields = ["id", "user_id", "email", "full_name", "organization", "role", "is_active", "created_at"]


class UserAdminSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="public_id", read_only=True)
    organizations_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "full_name",
            "cpf",
            "phone",
            "is_active",
            "is_staff",
            "is_superuser",
            "totp_enabled",
            "email_verified",
            "marketing_opt_in",
            "legal_version",
            "terms_accepted_at",
            "last_login",
            "date_joined",
            "anonymized_at",
            "organizations_count",
        ]
        read_only_fields = [
            "email",
            "is_staff",
            "is_superuser",
            "totp_enabled",
            "legal_version",
            "terms_accepted_at",
            "last_login",
            "date_joined",
            "anonymized_at",
        ]


class StaffCreateSerializer(serializers.Serializer):
    email = serializers.EmailField()
    full_name = serializers.CharField(max_length=150)
    password = serializers.CharField(min_length=10, max_length=128, write_only=True)
    is_superuser = serializers.BooleanField(default=False)

    def validate_email(self, value):
        value = value.lower().strip()
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError("Já existe um usuário com este e-mail.")
        return value


class LedgerAdminSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="public_id", read_only=True)
    kind_display = serializers.CharField(source="get_kind_display", read_only=True)
    created_by = serializers.CharField(source="created_by.full_name", default=None)

    class Meta:
        model = LedgerEntry
        fields = [
            "id",
            "kind",
            "kind_display",
            "amount_cents",
            "balance_after_cents",
            "description",
            "reference_type",
            "created_by",
            "created_at",
        ]


class TopUpAdminSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="public_id", read_only=True)
    organization = OrgRefField()
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    requested_by = serializers.CharField(source="requested_by.full_name", default=None)

    class Meta:
        model = TopUp
        fields = [
            "id",
            "organization",
            "amount_cents",
            "status",
            "status_display",
            "provider",
            "provider_reference",
            "requested_by",
            "expires_at",
            "paid_at",
            "created_at",
        ]


class ProductAdminSerializer(serializers.ModelSerializer):
    margin_cents = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            "id",
            "code",
            "sku",
            "name",
            "description",
            "category",
            "input_type",
            "cost_cents",
            "price_cents",
            "margin_cents",
            "is_async",
            "is_active",
            "is_featured",
            "sort_order",
            "highlights",
        ]

    def get_margin_cents(self, obj) -> int:
        return obj.price_cents - obj.cost_cents


class ServicePriceAdminSerializer(serializers.ModelSerializer):
    label = serializers.CharField(source="get_code_display", read_only=True)

    class Meta:
        model = ServicePrice
        fields = ["id", "code", "label", "price_cents", "is_active"]
        read_only_fields = ["code"]


class ConsultaAdminSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="public_id", read_only=True)
    organization = OrgRefField()
    product_name = serializers.CharField(source="product.name", read_only=True)
    user_name = serializers.CharField(source="user.full_name", default=None)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    purpose_display = serializers.CharField(source="get_purpose_display", read_only=True)

    class Meta:
        model = Consulta
        fields = [
            "id",
            "organization",
            "product_name",
            "sku",
            "input_type",
            "input_value",
            "purpose_display",
            "status",
            "status_display",
            "price_cents",
            "charged_cents",
            "provider_cost_cents",
            "provider_consulta_id",
            "message",
            "user_name",
            "created_at",
            "completed_at",
        ]


class NotaAdminSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="public_id", read_only=True)
    organization = OrgRefField()
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    tipo_display = serializers.CharField(source="get_tipo_display", read_only=True)

    class Meta:
        model = NotaFiscal
        fields = [
            "id",
            "organization",
            "tipo_display",
            "ambiente",
            "serie",
            "numero",
            "status",
            "status_display",
            "chave",
            "cstat",
            "message",
            "destinatario_nome",
            "total_cents",
            "price_cents",
            "created_at",
        ]


class StockAdminSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="public_id", read_only=True)
    organization = OrgRefField()
    state_display = serializers.CharField(source="get_state_display", read_only=True)
    client_name = serializers.CharField(source="client.name", default=None)

    class Meta:
        model = StockVehicle
        fields = [
            "id",
            "organization",
            "client_name",
            "placa",
            "renavam",
            "id_estoque",
            "state",
            "state_display",
            "entry_date",
            "entry_value_cents",
            "exit_date",
            "exit_value_cents",
            "created_at",
        ]


class RenaveOperationAdminSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="public_id", read_only=True)
    organization = OrgRefField()
    kind_display = serializers.CharField(source="get_kind_display", read_only=True)
    placa = serializers.CharField(source="vehicle.placa", default=None)
    user_name = serializers.CharField(source="user.full_name", default=None)

    class Meta:
        model = RenaveOperation
        fields = ["id", "organization", "kind", "kind_display", "placa", "success", "message", "price_cents", "user_name", "created_at"]


class ComunicacaoAdminSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="public_id", read_only=True)
    organization = OrgRefField()
    situacao_display = serializers.CharField(source="get_situacao_display", default=None)

    class Meta:
        model = ComunicacaoVenda
        fields = [
            "id",
            "organization",
            "protocolo",
            "situacao",
            "situacao_display",
            "placa",
            "comprador_nome",
            "valor_cents",
            "data_venda",
            "message",
            "price_cents",
            "created_at",
        ]


class CertificateAdminSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="public_id", read_only=True)
    organization = OrgRefField()
    client_name = serializers.CharField(source="client.name", default=None)
    days_to_expire = serializers.SerializerMethodField()

    class Meta:
        model = Certificate
        fields = [
            "id",
            "organization",
            "client_name",
            "holder_name",
            "holder_document",
            "not_after",
            "days_to_expire",
            "is_active",
            "carven_synced_at",
            "carven_sync_error",
            "created_at",
        ]

    def get_days_to_expire(self, obj) -> int:
        return (obj.not_after - timezone.now()).days


class IntegrationCallAdminSerializer(serializers.ModelSerializer):
    organization = OrgRefField()

    class Meta:
        model = IntegrationCall
        fields = [
            "id",
            "created_at",
            "provider",
            "organization",
            "method",
            "path",
            "status_code",
            "duration_ms",
            "success",
            "error",
            "request_id",
        ]


class IntegrationCallDetailSerializer(IntegrationCallAdminSerializer):
    class Meta(IntegrationCallAdminSerializer.Meta):
        fields = IntegrationCallAdminSerializer.Meta.fields + ["request_body", "response_body"]


class WebhookAdminSerializer(serializers.ModelSerializer):
    class Meta:
        model = WebhookDelivery
        fields = ["id", "received_at", "provider", "event", "delivery_id"]


class AuditAdminSerializer(serializers.ModelSerializer):
    actor = serializers.SerializerMethodField()
    organization = OrgRefField()

    class Meta:
        model = AuditEvent
        fields = [
            "id",
            "created_at",
            "action",
            "actor",
            "organization",
            "target_type",
            "target_id",
            "ip",
            "user_agent",
            "request_id",
            "metadata",
        ]

    def get_actor(self, obj):
        return {"name": obj.actor.full_name, "email": obj.actor.email} if obj.actor else None
