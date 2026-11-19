from django.db import models

from core.models import TimeStampedModel


class StockVehicle(TimeStampedModel):
    """Espelho local do estoque RENAVE (fonte da verdade: RENAVE via Carven)."""

    class State(models.TextChoices):
        SOLICITADO = "SOLICITADO", "Entrada solicitada"
        CONFIRMADO = "CONFIRMADO", "Em estoque"
        NEGADO = "NEGADO", "Entrada negada"
        FINALIZADO = "FINALIZADO", "Vendido"
        TRANSFERIDO = "TRANSFERIDO", "Transferido"
        CANCELADO = "CANCELADO", "Entrada cancelada"

    organization = models.ForeignKey("organizations.Organization", on_delete=models.PROTECT, related_name="stock")
    client = models.ForeignKey("organizations.ClientCompany", null=True, blank=True, on_delete=models.PROTECT, related_name="stock")
    owner_document = models.CharField(max_length=14, db_index=True)
    id_estoque = models.BigIntegerField(null=True, blank=True, db_index=True)
    protocolo = models.CharField(max_length=40, blank=True)
    placa = models.CharField(max_length=7, db_index=True)
    renavam = models.CharField(max_length=11)
    crv = models.CharField(max_length=20, blank=True)
    tipo_crv = models.CharField(max_length=10, blank=True)
    state = models.CharField(max_length=12, choices=State.choices, default=State.SOLICITADO, db_index=True)
    situacao = models.CharField(max_length=80, blank=True)
    marca_modelo = models.CharField(max_length=120, blank=True)
    ano_fabricacao = models.PositiveSmallIntegerField(null=True, blank=True)
    ano_modelo = models.PositiveSmallIntegerField(null=True, blank=True)
    cor = models.CharField(max_length=40, blank=True)
    chassi = models.CharField(max_length=17, blank=True)
    entry_date = models.DateField(null=True, blank=True)
    entry_value_cents = models.BigIntegerField(null=True, blank=True)
    entry_km = models.PositiveIntegerField(null=True, blank=True)
    exit_date = models.DateField(null=True, blank=True)
    exit_value_cents = models.BigIntegerField(null=True, blank=True)
    raw = models.JSONField(default=dict, blank=True)
    last_synced_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "id_estoque"], condition=models.Q(id_estoque__isnull=False), name="uniq_org_id_estoque"
            )
        ]
        indexes = [models.Index(fields=["organization", "state", "-created_at"])]

    def __str__(self):
        return f"{self.placa} ({self.get_state_display()})"


class RenaveOperation(TimeStampedModel):
    class Kind(models.TextChoices):
        APTIDAO = "aptidao", "Consulta de aptidão"
        ENTRADA_COMPRA = "entrada_compra", "Entrada por compra"
        ENTRADA_PROPRIO = "entrada_proprio", "Entrada de veículo próprio"
        SAIDA_VENDA = "saida_venda", "Saída por venda"
        TRANSF_FILIAIS = "transf_filiais", "Transferência entre filiais"
        TRANSF_ESTAB = "transf_estab", "Transferência entre estabelecimentos"
        CANCELAR_ENTRADA = "cancelar_entrada", "Cancelamento de entrada"
        CANCELAR_SAIDA = "cancelar_saida", "Cancelamento de saída"
        NOTA_FISCAL = "nota_fiscal", "Envio de nota fiscal"
        ATPV_ASSINADA = "atpv_assinada", "Envio de ATPV-e assinada"

    organization = models.ForeignKey("organizations.Organization", on_delete=models.PROTECT, related_name="renave_operations")
    vehicle = models.ForeignKey(StockVehicle, null=True, blank=True, on_delete=models.PROTECT, related_name="operations")
    user = models.ForeignKey("accounts.User", null=True, on_delete=models.SET_NULL, related_name="+")
    kind = models.CharField(max_length=20, choices=Kind.choices)
    success = models.BooleanField(default=False)
    message = models.CharField(max_length=500, blank=True)
    price_cents = models.PositiveIntegerField(default=0)
    reservation = models.OneToOneField(
        "wallet.Reservation", null=True, blank=True, on_delete=models.PROTECT, related_name="renave_operation"
    )
    response = models.JSONField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
