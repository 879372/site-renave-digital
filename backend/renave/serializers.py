from rest_framework import serializers

from core import documents

from .models import RenaveOperation, StockVehicle

TIPO_CRV = ["DIGITAL", "VERDE", "BRANCO", "AZUL"]


class ClientRefMixin(serializers.Serializer):
    client_id = serializers.UUIDField(required=False, allow_null=True)


def _plate(value):
    value = documents.normalize_plate(value)
    if not documents.is_valid_plate(value):
        raise serializers.ValidationError("Placa inválida.")
    return value


def _renavam(value):
    value = documents.only_digits(value).zfill(11)
    if not documents.is_valid_renavam(value):
        raise serializers.ValidationError("RENAVAM inválido.")
    return value


class AptidaoSerializer(ClientRefMixin):
    placa = serializers.CharField(max_length=8)
    renavam = serializers.CharField(max_length=11)
    crv = serializers.CharField(max_length=12)
    tipo_crv = serializers.ChoiceField(choices=TIPO_CRV)

    validate_placa = staticmethod(_plate)
    validate_renavam = staticmethod(_renavam)


class EntradaSerializer(ClientRefMixin):
    tipo_operacao = serializers.ChoiceField(choices=["compra_veiculo", "entrada_veiculo_proprio"])
    placa = serializers.CharField(max_length=8)
    renavam = serializers.CharField(max_length=11)
    crv = serializers.CharField(max_length=20)
    codigo_seguranca_crv = serializers.CharField(max_length=20)
    tipo_crv = serializers.ChoiceField(choices=TIPO_CRV)
    km = serializers.IntegerField(min_value=0, max_value=9_999_999)
    data_hora_km = serializers.DateTimeField()
    data_compra = serializers.DateField()
    vendedor_tipo = serializers.ChoiceField(choices=["fisica", "juridica"], required=False)
    vendedor_documento = serializers.CharField(max_length=18, required=False, allow_blank=True)
    valor_compra_cents = serializers.IntegerField(min_value=0, required=False)

    validate_placa = staticmethod(_plate)
    validate_renavam = staticmethod(_renavam)

    def validate(self, attrs):
        if attrs["tipo_operacao"] == "compra_veiculo":
            errors = {}
            for field in ("vendedor_tipo", "vendedor_documento", "valor_compra_cents"):
                if attrs.get(field) in (None, ""):
                    errors[field] = "Obrigatório na compra de terceiro."
            if errors:
                raise serializers.ValidationError(errors)
            doc = documents.normalize_document(attrs["vendedor_documento"])
            valid = documents.is_valid_cpf(doc) if attrs["vendedor_tipo"] == "fisica" else documents.is_valid_cnpj(doc)
            if not valid:
                raise serializers.ValidationError({"vendedor_documento": "Documento do vendedor inválido."})
            attrs["vendedor_documento"] = doc
        return attrs


class SaidaSerializer(serializers.Serializer):
    tipo_transferencia = serializers.ChoiceField(choices=[1, 2, 3])
    data_venda = serializers.DateField()
    cod_seguranca_crv = serializers.CharField(max_length=20)
    comprador_nome = serializers.CharField(max_length=100)
    comprador_documento = serializers.CharField(max_length=18)
    valor_venda_cents = serializers.IntegerField(min_value=0, required=False)
    municipio = serializers.CharField(max_length=7, required=False, allow_blank=True)
    email = serializers.EmailField(required=False, allow_blank=True)
    cep = serializers.CharField(max_length=9, required=False, allow_blank=True)
    logradouro = serializers.CharField(max_length=100, required=False, allow_blank=True)
    numero = serializers.CharField(max_length=10, required=False, allow_blank=True)
    complemento = serializers.CharField(max_length=50, required=False, allow_blank=True)
    bairro = serializers.CharField(max_length=50, required=False, allow_blank=True)
    km = serializers.IntegerField(min_value=0, required=False)
    data_hora_km = serializers.DateTimeField(required=False)

    def validate(self, attrs):
        doc = documents.normalize_document(attrs["comprador_documento"])
        if attrs["tipo_transferencia"] == 1:
            if not documents.is_valid_cpf(doc):
                raise serializers.ValidationError({"comprador_documento": "Na venda, informe o CPF do comprador."})
            missing = {f: "Obrigatório na venda." for f in ("valor_venda_cents", "municipio") if attrs.get(f) in (None, "")}
            if missing:
                raise serializers.ValidationError(missing)
            if attrs.get("cep"):
                attrs["cep"] = documents.only_digits(attrs["cep"])
        elif not documents.is_valid_cnpj(doc):
            raise serializers.ValidationError({"comprador_documento": "Informe o CNPJ do estabelecimento de destino."})
        attrs["comprador_documento"] = doc
        return attrs


class NotaFiscalSerializer(serializers.Serializer):
    chave = serializers.RegexField(r"^[0-9A-Z]{44}$", error_messages={"invalid": "A chave deve ter 44 caracteres."})
    evento = serializers.ChoiceField(choices=["COMPRA", "VENDA"])


class AtpvAssinadaSerializer(serializers.Serializer):
    tipo_assinatura = serializers.ChoiceField(choices=["cartorio", "certificado"])
    arquivo = serializers.FileField()

    def validate_arquivo(self, value):
        if value.size > 8 * 1024 * 1024:
            raise serializers.ValidationError("Arquivo acima de 8 MB.")
        return value


class OperationSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="public_id", read_only=True)
    kind_display = serializers.CharField(source="get_kind_display", read_only=True)
    user_name = serializers.CharField(source="user.full_name", default=None)

    class Meta:
        model = RenaveOperation
        fields = ["id", "kind", "kind_display", "success", "message", "price_cents", "user_name", "created_at"]


class StockVehicleSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="public_id", read_only=True)
    state_display = serializers.CharField(source="get_state_display", read_only=True)
    client_name = serializers.CharField(source="client.name", default=None)

    class Meta:
        model = StockVehicle
        fields = [
            "id",
            "id_estoque",
            "protocolo",
            "placa",
            "renavam",
            "state",
            "state_display",
            "situacao",
            "marca_modelo",
            "ano_fabricacao",
            "ano_modelo",
            "cor",
            "client_name",
            "owner_document",
            "entry_date",
            "entry_value_cents",
            "entry_km",
            "exit_date",
            "exit_value_cents",
            "last_synced_at",
            "created_at",
        ]


class StockVehicleDetailSerializer(StockVehicleSerializer):
    operations = OperationSerializer(many=True, read_only=True)

    class Meta(StockVehicleSerializer.Meta):
        fields = StockVehicleSerializer.Meta.fields + ["operations"]
