from django.db import models


class IntegrationCall(models.Model):
    """Registro de cada chamada a provedor (corpo sempre mascarado)."""

    class Provider(models.TextChoices):
        BUSCARS = "buscars", "BusCars"
        CARVEN = "carven", "Carven"
        GERANET = "geranet", "Geranet"

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    provider = models.CharField(max_length=10, choices=Provider.choices, db_index=True)
    organization = models.ForeignKey("organizations.Organization", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    method = models.CharField(max_length=8)
    path = models.CharField(max_length=255)
    status_code = models.PositiveSmallIntegerField(null=True)
    duration_ms = models.PositiveIntegerField(default=0)
    success = models.BooleanField(default=False)
    error = models.CharField(max_length=300, blank=True)
    request_id = models.CharField(max_length=64, blank=True)
    request_body = models.JSONField(null=True, blank=True)
    response_body = models.JSONField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["provider", "-created_at"])]


class WebhookDelivery(models.Model):
    """Deduplicação de webhooks recebidos (o provedor pode reenviar)."""

    provider = models.CharField(max_length=10)
    delivery_id = models.CharField(max_length=120)
    event = models.CharField(max_length=60)
    received_at = models.DateTimeField(auto_now_add=True)
    payload = models.JSONField(default=dict)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["provider", "delivery_id"], name="uniq_webhook_delivery")]
