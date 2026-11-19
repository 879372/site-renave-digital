from rest_framework import serializers

from core import documents

from .models import FiscalSettings, NotaFiscal

UFS = "AC AL AP AM BA CE DF ES GO MA MT MS MG PA PB PR PE PI RJ RN RS RO RR SC SP SE TO".split()


class FiscalSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = FiscalSettings
        exclude = ["id", "organization", "updated_at"]


class NotaCreateSerializer(serializers.Serializer):
    tipo = serializers.ChoiceField(choices=NotaFiscal.Tipo.choices)
    vehicle_id = serializers.UUIDField(required=False, allow_null=True)
    # destinatário (comprador na venda / vendedor na compra)
    documento = serializers.CharField(max_length=18)
    nome = serializers.CharField(max_length=150)
    inscricao_estadual = serializers.CharField(max_length=20, required=False, allow_blank=True)
    email = serializers.EmailField(required=False, allow_blank=True)
    telefone = serializers.CharField(max_length=20, required=False, allow_blank=True)
    cep = serializers.CharField(max_length=9)
    logradouro = serializers.CharField(max_length=120)
    numero = serializers.CharField(max_length=10)
    complemento = serializers.CharField(max_length=60, required=False, allow_blank=True)
    bairro = serializers.CharField(max_length=60)
    cidade = serializers.CharField(max_length=80)
    cidade_ibge = serializers.RegexField(r"^\d{7}$", error_messages={"invalid": "Código IBGE com 7 dígitos."})
    uf = serializers.ChoiceField(choices=UFS)
    # veículo
    placa = serializers.CharField(max_length=8)
    chassi = serializers.CharField(max_length=17)
    renavam = serializers.CharField(max_length=11)
    marca_modelo = serializers.CharField(max_length=80)
    ano_fabricacao = serializers.IntegerField(min_value=1900)
    ano_modelo = serializers.IntegerField(min_value=1900)
    cor = serializers.CharField(max_length=30)
    km = serializers.IntegerField(min_value=0, required=False)
    ncm = serializers.RegexField(r"^\d{8}$", required=False, allow_blank=True)
    valor_cents = serializers.IntegerField(min_value=1)
    forma_pagamento = serializers.ChoiceField(
        choices=[
            ("01", "Dinheiro"),
            ("03", "Cartão de crédito"),
            ("04", "Cartão de débito"),
            ("15", "Boleto"),
            ("16", "Depósito"),
            ("17", "PIX"),
            ("18", "Transferência"),
            ("90", "Sem pagamento"),
            ("99", "Outros"),
        ],
        default="99",
    )
    observacoes = serializers.CharField(max_length=1000, required=False, allow_blank=True)

    def validate(self, attrs):
        doc = documents.normalize_document(attrs["documento"])
        if not documents.is_valid_document(doc):
            raise serializers.ValidationError({"documento": "CPF/CNPJ inválido."})
        attrs["documento"] = doc
        attrs["placa"] = documents.normalize_plate(attrs["placa"])
        if not documents.is_valid_plate(attrs["placa"]):
            raise serializers.ValidationError({"placa": "Placa inválida."})
        attrs["chassi"] = attrs["chassi"].replace(" ", "").upper()
        if not documents.is_valid_vin(attrs["chassi"]):
            raise serializers.ValidationError({"chassi": "Chassi inválido."})
        attrs["renavam"] = documents.only_digits(attrs["renavam"]).zfill(11)
        if not documents.is_valid_renavam(attrs["renavam"]):
            raise serializers.ValidationError({"renavam": "RENAVAM inválido."})
        attrs["cep"] = documents.only_digits(attrs["cep"])
        return attrs


class NotaSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="public_id", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    tipo_display = serializers.CharField(source="get_tipo_display", read_only=True)
    has_pdf = serializers.SerializerMethodField()
    placa = serializers.CharField(source="vehicle.placa", default=None)

    class Meta:
        model = NotaFiscal
        fields = [
            "id",
            "tipo",
            "tipo_display",
            "ambiente",
            "serie",
            "numero",
            "status",
            "status_display",
            "chave",
            "protocolo",
            "cstat",
            "message",
            "destinatario_nome",
            "destinatario_documento",
            "total_cents",
            "price_cents",
            "cce_count",
            "has_pdf",
            "placa",
            "authorized_at",
            "canceled_at",
            "created_at",
        ]

    def get_has_pdf(self, obj) -> bool:
        return bool(obj.pdf)
