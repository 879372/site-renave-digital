import json

from django.db import models

from core.models import TimeStampedModel
from vault.crypto import decrypt_bytes, encrypt_bytes


class FiscalSettings(models.Model):
    """Parâmetros fiscais do emitente. Confira com o contador da empresa."""

    organization = models.OneToOneField("organizations.Organization", on_delete=models.CASCADE, related_name="fiscal_settings")
    serie = models.PositiveSmallIntegerField(default=1)
    next_number = models.PositiveIntegerField(default=1)
    natureza_venda = models.CharField(max_length=60, default="Venda de veiculo usado")
    natureza_compra = models.CharField(max_length=60, default="Compra de veiculo usado")
    ncm_padrao = models.CharField(max_length=8, default="87032310")
    cfop_venda_estadual = models.CharField(max_length=4, default="5102")
    cfop_venda_interestadual = models.CharField(max_length=4, default="6102")
    cfop_compra_estadual = models.CharField(max_length=4, default="1102")
    cfop_compra_interestadual = models.CharField(max_length=4, default="2102")
    icms_csosn = models.CharField(max_length=3, default="102")
    pis_cst = models.CharField(max_length=2, default="49")
    cofins_cst = models.CharField(max_length=2, default="49")
    informacao_complementar = models.TextField(blank=True)
    enviar_chave_renave = models.BooleanField(
        default=True, help_text="Enviar a chave ao RENAVE quando a nota estiver ligada a um veículo do estoque."
    )
    updated_at = models.DateTimeField(auto_now=True)


class NotaFiscal(TimeStampedModel):
    class Tipo(models.TextChoices):
        ENTRADA = "0", "Entrada (compra)"
        SAIDA = "1", "Saída (venda)"

    class Status(models.TextChoices):
        QUEUED = "queued", "Na fila"
        PROCESSING = "processing", "Transmitindo"
        AUTHORIZED = "authorized", "Autorizada"
        REJECTED = "rejected", "Rejeitada"
        CANCELED = "canceled", "Cancelada"
        ERROR = "error", "Erro de comunicação"

    organization = models.ForeignKey("organizations.Organization", on_delete=models.PROTECT, related_name="notas")
    user = models.ForeignKey("accounts.User", null=True, on_delete=models.SET_NULL, related_name="+")
    vehicle = models.ForeignKey("renave.StockVehicle", null=True, blank=True, on_delete=models.SET_NULL, related_name="notas")
    tipo = models.CharField(max_length=1, choices=Tipo.choices)
    ambiente = models.CharField(max_length=1, default="2")
    serie = models.PositiveSmallIntegerField()
    numero = models.PositiveIntegerField()
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.QUEUED, db_index=True)
    chave = models.CharField(max_length=44, blank=True, db_index=True)
    protocolo = models.CharField(max_length=20, blank=True)
    cstat = models.CharField(max_length=10, blank=True)
    message = models.CharField(max_length=500, blank=True)
    destinatario_nome = models.CharField(max_length=150)
    destinatario_documento = models.CharField(max_length=14)
    total_cents = models.BigIntegerField()
    payload_encrypted = models.BinaryField(editable=False)
    xml = models.BinaryField(null=True, blank=True, editable=False)
    pdf = models.BinaryField(null=True, blank=True, editable=False)
    cce_count = models.PositiveSmallIntegerField(default=0)
    price_cents = models.PositiveIntegerField(default=0)
    reservation = models.OneToOneField("wallet.Reservation", null=True, blank=True, on_delete=models.PROTECT, related_name="nota")
    authorized_at = models.DateTimeField(null=True, blank=True)
    canceled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["organization", "ambiente", "serie", "numero"], name="uniq_nfe_numero"),
        ]
        indexes = [models.Index(fields=["organization", "-created_at"])]

    def set_payload(self, data: dict):
        self.payload_encrypted = encrypt_bytes(json.dumps(data, ensure_ascii=False).encode(), f"nfe:{self.public_id}".encode())

    def get_payload(self) -> dict:
        return json.loads(decrypt_bytes(bytes(self.payload_encrypted), f"nfe:{self.public_id}".encode()))
