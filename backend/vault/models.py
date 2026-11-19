from django.db import models

from core.models import TimeStampedModel


class Certificate(TimeStampedModel):
    """Certificado A1 cifrado. Arquivo e senha nunca saem do servidor."""

    organization = models.ForeignKey("organizations.Organization", on_delete=models.CASCADE, related_name="certificates")
    client = models.ForeignKey("organizations.ClientCompany", null=True, blank=True, on_delete=models.CASCADE, related_name="certificates")
    holder_document = models.CharField(max_length=14, db_index=True)
    holder_name = models.CharField(max_length=200)
    subject = models.CharField(max_length=500)
    serial = models.CharField(max_length=80)
    fingerprint = models.CharField(max_length=64)
    not_before = models.DateTimeField()
    not_after = models.DateTimeField(db_index=True)
    pfx_encrypted = models.BinaryField(editable=False)
    password_encrypted = models.BinaryField(editable=False)
    is_active = models.BooleanField(default=True)
    uploaded_by = models.ForeignKey("accounts.User", null=True, on_delete=models.SET_NULL, related_name="+")
    carven_synced_at = models.DateTimeField(null=True, blank=True)
    carven_sync_error = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["organization", "client", "is_active"])]

    def __str__(self):
        return f"{self.holder_name} ({self.holder_document})"

    @property
    def aad(self) -> bytes:
        return f"cert:{self.public_id}".encode()
