from django.db import models

from core.models import TimeStampedModel


class Wallet(models.Model):
    organization = models.OneToOneField("organizations.Organization", on_delete=models.PROTECT, related_name="wallet")
    balance_cents = models.BigIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.CheckConstraint(condition=models.Q(balance_cents__gte=0), name="wallet_non_negative")]

    def __str__(self):
        return f"Carteira {self.organization}"


class LedgerEntry(TimeStampedModel):
    """Lançamento imutável. O saldo da carteira é sempre a soma dos lançamentos."""

    class Kind(models.TextChoices):
        TOPUP = "topup", "Recarga"
        ADJUSTMENT = "adjustment", "Ajuste"
        RESERVE = "reserve", "Reserva"
        RELEASE = "release", "Estorno"
        CAPTURE_ADJUST = "capture_adjust", "Ajuste de cobrança"

    wallet = models.ForeignKey(Wallet, on_delete=models.PROTECT, related_name="entries")
    kind = models.CharField(max_length=20, choices=Kind.choices)
    amount_cents = models.BigIntegerField()  # positivo = crédito, negativo = débito
    balance_after_cents = models.BigIntegerField()
    description = models.CharField(max_length=200)
    reference_type = models.CharField(max_length=40, blank=True)
    reference_id = models.CharField(max_length=64, blank=True, db_index=True)
    idempotency_key = models.CharField(max_length=128, unique=True, null=True, blank=True)
    created_by = models.ForeignKey("accounts.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["wallet", "-created_at"])]

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValueError("Lançamentos são imutáveis.")
        super().save(*args, **kwargs)


class Reservation(TimeStampedModel):
    class Status(models.TextChoices):
        HELD = "held", "Reservado"
        CAPTURED = "captured", "Cobrado"
        RELEASED = "released", "Estornado"

    wallet = models.ForeignKey(Wallet, on_delete=models.PROTECT, related_name="reservations")
    amount_cents = models.BigIntegerField()
    captured_cents = models.BigIntegerField(default=0)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.HELD, db_index=True)
    reference_type = models.CharField(max_length=40)
    reference_id = models.CharField(max_length=64)
    description = models.CharField(max_length=200)


class TopUp(TimeStampedModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Aguardando pagamento"
        PAID = "paid", "Pago"
        EXPIRED = "expired", "Expirado"
        CANCELED = "canceled", "Cancelado"

    organization = models.ForeignKey("organizations.Organization", on_delete=models.PROTECT, related_name="topups")
    amount_cents = models.BigIntegerField()
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING, db_index=True)
    provider = models.CharField(max_length=30, default="manual")
    provider_reference = models.CharField(max_length=120, blank=True, db_index=True)
    pix_copy_paste = models.TextField(blank=True)
    pix_qr_base64 = models.TextField(blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    requested_by = models.ForeignKey("accounts.User", null=True, on_delete=models.SET_NULL, related_name="+")

    class Meta:
        ordering = ["-created_at"]


class ServicePrice(models.Model):
    """Preço de venda das operações tarifadas (RENAVE, comunicação, NF-e)."""

    class Code(models.TextChoices):
        RENAVE_ENTRADA = "renave.entrada", "RENAVE — entrada em estoque"
        RENAVE_SAIDA = "renave.saida", "RENAVE — saída de estoque"
        RENAVE_CANCELAR_ENTRADA = "renave.cancelar_entrada", "RENAVE — cancelamento de entrada"
        RENAVE_CANCELAR_SAIDA = "renave.cancelar_saida", "RENAVE — cancelamento de saída"
        COMUNICACAO = "comunicacao.transmitir", "Comunicação de venda"
        NFE = "fiscal.nfe", "NF-e autorizada"

    code = models.CharField(max_length=40, choices=Code.choices, unique=True)
    price_cents = models.PositiveIntegerField()
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.get_code_display()


DEFAULT_PRICES = {
    ServicePrice.Code.RENAVE_ENTRADA: 2490,
    ServicePrice.Code.RENAVE_SAIDA: 2490,
    ServicePrice.Code.RENAVE_CANCELAR_ENTRADA: 990,
    ServicePrice.Code.RENAVE_CANCELAR_SAIDA: 990,
    ServicePrice.Code.COMUNICACAO: 1990,
    ServicePrice.Code.NFE: 190,
}
