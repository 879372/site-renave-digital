from rest_framework import serializers

from .models import Consulta, Product


class ProductSerializer(serializers.ModelSerializer):
    class Meta:
        model = Product
        fields = ["code", "name", "description", "category", "input_type", "price_cents", "is_async", "is_featured", "highlights"]


class ConsultaCreateSerializer(serializers.Serializer):
    product = serializers.SlugField(max_length=60)
    value = serializers.CharField(max_length=30)
    purpose = serializers.ChoiceField(choices=Consulta.Purpose.choices, default=Consulta.Purpose.COMPRA)


class ConsultaSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="public_id", read_only=True)
    product_name = serializers.CharField(source="product.name", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    user_name = serializers.CharField(source="user.full_name", default=None, read_only=True)
    product = serializers.CharField(source="product.code", read_only=True)

    class Meta:
        model = Consulta
        fields = [
            "id",
            "product",
            "product_name",
            "input_type",
            "input_value",
            "purpose",
            "status",
            "status_display",
            "price_cents",
            "charged_cents",
            "message",
            "user_name",
            "created_at",
            "completed_at",
        ]


class ConsultaDetailSerializer(ConsultaSerializer):
    result = serializers.SerializerMethodField()

    class Meta(ConsultaSerializer.Meta):
        fields = ConsultaSerializer.Meta.fields + ["result"]

    def get_result(self, obj):
        return obj.get_result()
