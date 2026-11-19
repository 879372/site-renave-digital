from rest_framework import serializers

from .models import Certificate


class CertificateSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="public_id", read_only=True)
    client_id = serializers.UUIDField(source="client.public_id", read_only=True, allow_null=True)
    client_name = serializers.CharField(source="client.name", read_only=True, allow_null=True)
    days_to_expire = serializers.SerializerMethodField()
    renave_ready = serializers.SerializerMethodField()
    renave_error = serializers.CharField(source="carven_sync_error", read_only=True)

    def get_renave_ready(self, obj) -> bool:
        return obj.carven_synced_at is not None

    class Meta:
        model = Certificate
        fields = [
            "id",
            "client_id",
            "client_name",
            "holder_document",
            "holder_name",
            "not_before",
            "not_after",
            "days_to_expire",
            "is_active",
            "renave_ready",
            "renave_error",
            "created_at",
        ]

    def get_days_to_expire(self, obj) -> int:
        from django.utils import timezone

        return (obj.not_after - timezone.now()).days


class CertificateUploadSerializer(serializers.Serializer):
    file = serializers.FileField()
    password = serializers.CharField(max_length=255, trim_whitespace=False)
    client_id = serializers.UUIDField(required=False, allow_null=True)

    def validate_file(self, value):
        name = value.name.lower()
        if not name.endswith((".pfx", ".p12")):
            raise serializers.ValidationError("Envie o certificado A1 no formato .pfx ou .p12.")
        return value
