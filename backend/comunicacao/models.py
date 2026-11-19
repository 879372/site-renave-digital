import json
import secrets

from django.db import models

from core.models import TimeStampedModel
from vault.crypto import decrypt_bytes, encrypt_bytes


def _token():
    return secrets.token_urlsafe(24)


class ComunicacaoVenda(TimeStampedModel):
    class Situacao(models.IntegerChoices):
        CADASTRADA = 1, "Cadastrada"
        COMUNICADA = 2, "Comunicada"
        CERTIDAO = 3, "Certidão gerada"
        CANCELADA = 4, "Cancelada"
        ERRO = 5, "Comunicação com erro"
        EXCLUIDA = 6, "Excluída sem enviar"
        BLOQUEADA = 7, "Bloqueada"
        NAO_DESBLOQUEADA = 8, "Não desbloqueada"

    organization = models.ForeignKey("organizations.Organization", on_delete=models.PROTECT, related_name="comunicacoes")
    user = models.ForeignKey("accounts.User", null=True, on_delete=models.SET_NULL, related_name="+")
    vehicle = models.ForeignKey("renave.StockVehicle", null=True, blank=True, on_delete=models.SET_NULL, related_name="comunicacoes")
    protocolo = models.CharField(max_length=40, blank=True, db_index=True)
    situacao = models.PositiveSmallIntegerField(choices=Situacao.choices, null=True, blank=True)
    placa = models.CharField(max_length=7, db_index=True)
    renavam = models.CharField(max_length=11)
    comprador_nome = models.CharField(max_length=150)
    valor_cents = models.BigIntegerField()
    data_venda = models.DateField()
    payload_encrypted = models.BinaryField(editable=False)
    notify_token = models.CharField(max_length=64, unique=True, default=_token, editable=False)
    message = models.CharField(max_length=500, blank=True)
    price_cents = models.PositiveIntegerField(default=0)
    reservation = models.OneToOneField("wallet.Reservation", null=True, blank=True, on_delete=models.PROTECT, related_name="comunicacao")
    transmitted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["organization", "-created_at"])]

    def set_payload(self, data: dict):
        self.payload_encrypted = encrypt_bytes(json.dumps(data, ensure_ascii=False).encode(), f"cv:{self.public_id}".encode())

    def get_payload(self) -> dict:
        return json.loads(decrypt_bytes(bytes(self.payload_encrypted), f"cv:{self.public_id}".encode()))
