from rest_framework import serializers

from core import documents

from .models import ComunicacaoVenda

UFS = "AC AL AP AM BA CE DF ES GO MA MT MS MG PA PB PR PE PI RJ RN RS RO RR SC SP SE TO".split()


class ComunicacaoCreateSerializer(serializers.Serializer):
    vehicle_id = serializers.UUIDField(required=False, allow_null=True)
    vendedor_tipo = serializers.ChoiceField(choices=["F", "J"])
    vendedor_documento = serializers.CharField(max_length=18)
    vendedor_nome = serializers.CharField(max_length=150)
    comprador_tipo = serializers.ChoiceField(choices=["F", "J"])
    comprador_documento = serializers.CharField(max_length=18)
    comprador_nome = serializers.CharField(max_length=150)
    cep = serializers.CharField(max_length=9)
    logradouro = serializers.CharField(max_length=120)
    numero = serializers.CharField(max_length=10)
    bairro = serializers.CharField(max_length=60)
    complemento = serializers.CharField(max_length=60, required=False, allow_blank=True)
    cidade_comprador = serializers.IntegerField(help_text="Código IBGE7 da cidade do comprador")
    cidade_venda = serializers.IntegerField(help_text="Código IBGE7 da cidade da venda")
    data_venda = serializers.DateField()
    valor_cents = serializers.IntegerField(min_value=1)
    comprador_solicitante = serializers.BooleanField(default=False)
    placa = serializers.CharField(max_length=8)
    renavam = serializers.CharField(max_length=11)
    ano_fabricacao = serializers.IntegerField(min_value=1900)
    ano_modelo = serializers.IntegerField(min_value=1900)
    crv_numero = serializers.CharField(max_length=20)
    crv_codigo_seguranca = serializers.CharField(max_length=20)
    crv_via = serializers.IntegerField(min_value=1)
    crv_data_emissao = serializers.DateField()
    crv_uf = serializers.ChoiceField(choices=UFS)

    def validate(self, attrs):
        for prefix in ("vendedor", "comprador"):
            doc = documents.normalize_document(attrs[f"{prefix}_documento"])
            ok = documents.is_valid_cpf(doc) if attrs[f"{prefix}_tipo"] == "F" else documents.is_valid_cnpj(doc)
            if not ok:
                raise serializers.ValidationError({f"{prefix}_documento": "Documento inválido."})
            attrs[f"{prefix}_documento"] = doc
        attrs["placa"] = documents.normalize_plate(attrs["placa"])
        if not documents.is_valid_plate(attrs["placa"]):
            raise serializers.ValidationError({"placa": "Placa inválida."})
        attrs["renavam"] = documents.only_digits(attrs["renavam"]).zfill(11)
        if not documents.is_valid_renavam(attrs["renavam"]):
            raise serializers.ValidationError({"renavam": "RENAVAM inválido."})
        attrs["cep"] = documents.only_digits(attrs["cep"])
        if attrs["ano_modelo"] < attrs["ano_fabricacao"]:
            raise serializers.ValidationError({"ano_modelo": "Ano modelo não pode ser menor que o de fabricação."})
        return attrs


class ComunicacaoSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="public_id", read_only=True)
    situacao_display = serializers.CharField(source="get_situacao_display", read_only=True, default=None)
    user_name = serializers.CharField(source="user.full_name", default=None)

    class Meta:
        model = ComunicacaoVenda
        fields = [
            "id",
            "protocolo",
            "situacao",
            "situacao_display",
            "placa",
            "renavam",
            "comprador_nome",
            "valor_cents",
            "data_venda",
            "message",
            "price_cents",
            "user_name",
            "transmitted_at",
            "created_at",
        ]
