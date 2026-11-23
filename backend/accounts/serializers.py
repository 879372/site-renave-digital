from django.contrib.auth import password_validation
from rest_framework import serializers

from core.documents import is_valid_cnpj, is_valid_cpf, normalize_cnpj, only_digits
from organizations.models import Organization

from .models import User


class UserSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="public_id", read_only=True)

    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "full_name",
            "cpf",
            "phone",
            "email_verified",
            "totp_enabled",
            "date_joined",
            "legal_version",
            "terms_accepted_at",
            "marketing_opt_in",
        ]
        read_only_fields = ["email", "email_verified", "totp_enabled", "date_joined", "legal_version", "terms_accepted_at"]

    def validate_cpf(self, value):
        value = only_digits(value)
        if value and not is_valid_cpf(value):
            raise serializers.ValidationError("CPF inválido.")
        return value


class RegisterSerializer(serializers.Serializer):
    full_name = serializers.CharField(max_length=150)
    email = serializers.EmailField()
    phone = serializers.CharField(max_length=20)
    cpf = serializers.CharField(max_length=14)
    password = serializers.CharField(write_only=True, min_length=10, max_length=128)
    password_confirm = serializers.CharField(write_only=True, max_length=128)
    cnpj = serializers.CharField(max_length=18)
    legal_name = serializers.CharField(max_length=150)
    trade_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    uf = serializers.CharField(max_length=2)
    city = serializers.CharField(max_length=80)
    accept_terms = serializers.BooleanField()
    marketing_opt_in = serializers.BooleanField(default=False)

    def validate_email(self, value):
        value = value.lower().strip()
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError("Já existe uma conta com este e-mail.")
        return value

    def validate_cpf(self, value):
        value = only_digits(value)
        if not is_valid_cpf(value):
            raise serializers.ValidationError("CPF inválido.")
        return value

    def validate_cnpj(self, value):
        value = normalize_cnpj(value)
        if not is_valid_cnpj(value):
            raise serializers.ValidationError("CNPJ inválido.")
        if Organization.objects.filter(cnpj=value).exists():
            raise serializers.ValidationError("Esta empresa já está cadastrada. Peça ao responsável um convite para participar.")
        return value

    def validate_uf(self, value):
        return value.upper()

    def validate_accept_terms(self, value):
        if not value:
            raise serializers.ValidationError("É preciso aceitar os termos de uso e a política de privacidade.")
        return value

    def validate(self, attrs):
        if attrs["password"] != attrs["password_confirm"]:
            raise serializers.ValidationError({"password_confirm": "As senhas não conferem."})
        user = User(email=attrs["email"], full_name=attrs["full_name"])
        password_validation.validate_password(attrs["password"], user)
        return attrs


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, max_length=128)


class MfaLoginSerializer(serializers.Serializer):
    mfa_token = serializers.CharField()
    code = serializers.CharField(max_length=20)


class PasswordChangeSerializer(serializers.Serializer):
    current_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True, min_length=10, max_length=128)
    new_password_confirm = serializers.CharField(write_only=True, max_length=128)

    def validate(self, attrs):
        if attrs["new_password"] != attrs["new_password_confirm"]:
            raise serializers.ValidationError({"new_password_confirm": "As senhas não conferem."})
        user = self.context["request"].user
        if not user.check_password(attrs["current_password"]):
            raise serializers.ValidationError({"current_password": "Senha atual incorreta."})
        password_validation.validate_password(attrs["new_password"], user)
        return attrs


class PasswordResetSerializer(serializers.Serializer):
    email = serializers.EmailField()


class PasswordResetConfirmSerializer(serializers.Serializer):
    uid = serializers.CharField()
    token = serializers.CharField()
    new_password = serializers.CharField(write_only=True, min_length=10, max_length=128)
    new_password_confirm = serializers.CharField(write_only=True, max_length=128)

    def validate(self, attrs):
        if attrs["new_password"] != attrs["new_password_confirm"]:
            raise serializers.ValidationError({"new_password_confirm": "As senhas não conferem."})
        return attrs


class MfaCodeSerializer(serializers.Serializer):
    code = serializers.CharField(max_length=20)


class MfaDisableSerializer(serializers.Serializer):
    password = serializers.CharField(write_only=True)
    code = serializers.CharField(max_length=20)


class AccountDeleteSerializer(serializers.Serializer):
    password = serializers.CharField(write_only=True)
    confirmation = serializers.CharField()

    def validate_confirmation(self, value):
        if value.strip().upper() != "EXCLUIR":
            raise serializers.ValidationError("Digite EXCLUIR para confirmar.")
        return value


class EmailCodeSerializer(serializers.Serializer):
    code = serializers.RegexField(r"^\s*\d{6}\s*$", error_messages={"invalid": "Digite os 6 números do código."})
