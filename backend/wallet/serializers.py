from rest_framework import serializers

from .models import LedgerEntry, TopUp

MIN_TOPUP_CENTS = 2_000
MAX_TOPUP_CENTS = 5_000_000


class LedgerEntrySerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="public_id", read_only=True)
    kind_display = serializers.CharField(source="get_kind_display", read_only=True)

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
            "reference_id",
            "created_at",
        ]


class TopUpSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="public_id", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = TopUp
        fields = [
            "id",
            "amount_cents",
            "status",
            "status_display",
            "provider",
            "provider_reference",
            "payment_url",
            "pix_copy_paste",
            "pix_qr_base64",
            "expires_at",
            "paid_at",
            "created_at",
        ]
        read_only_fields = [f for f in fields if f != "amount_cents"]

    def validate_amount_cents(self, value):
        if not MIN_TOPUP_CENTS <= value <= MAX_TOPUP_CENTS:
            raise serializers.ValidationError("A recarga deve ser entre R$ 20,00 e R$ 50.000,00.")
        return value
