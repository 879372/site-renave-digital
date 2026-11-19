from rest_framework import serializers

from core.documents import is_valid_document, normalize_document, only_digits

from .models import ClientCompany, Invitation, Membership, Organization, Role


class OrganizationSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="public_id", read_only=True)

    class Meta:
        model = Organization
        fields = [
            "id",
            "cnpj",
            "legal_name",
            "trade_name",
            "kind",
            "email",
            "phone",
            "state_registration",
            "tax_regime",
            "zip_code",
            "street",
            "number",
            "complement",
            "district",
            "city",
            "city_ibge",
            "uf",
            "mfa_required",
            "created_at",
        ]
        read_only_fields = ["cnpj", "created_at"]

    def validate_zip_code(self, value):
        return only_digits(value)[:8]

    def validate_uf(self, value):
        return value.upper()


class MemberSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="public_id", read_only=True)
    email = serializers.EmailField(source="user.email", read_only=True)
    full_name = serializers.CharField(source="user.full_name", read_only=True)
    totp_enabled = serializers.BooleanField(source="user.totp_enabled", read_only=True)

    class Meta:
        model = Membership
        fields = ["id", "email", "full_name", "role", "is_active", "totp_enabled", "created_at"]
        read_only_fields = ["created_at"]


class InvitationSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="public_id", read_only=True)

    class Meta:
        model = Invitation
        fields = ["id", "email", "role", "expires_at", "accepted_at", "created_at"]
        read_only_fields = ["expires_at", "accepted_at", "created_at"]

    def validate_role(self, value):
        if value == Role.OWNER:
            raise serializers.ValidationError("O papel de proprietário não pode ser atribuído por convite.")
        return value


class ClientCompanySerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="public_id", read_only=True)
    has_certificate = serializers.SerializerMethodField()

    class Meta:
        model = ClientCompany
        fields = ["id", "document", "name", "email", "phone", "is_active", "has_certificate", "created_at"]
        read_only_fields = ["created_at"]

    def get_has_certificate(self, obj) -> bool:
        return obj.certificates.filter(is_active=True).exists()

    def validate_document(self, value):
        value = normalize_document(value)
        if not is_valid_document(value):
            raise serializers.ValidationError("CPF/CNPJ inválido.")
        return value
