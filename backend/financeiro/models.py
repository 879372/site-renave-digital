"""Financeiro da loja: contas a pagar e a receber, caixa/bancos e categorias."""

from django.db import models
from django.utils import timezone

from core.models import TimeStampedModel


class Conta(TimeStampedModel):
    """Conta bancária ou caixa da loja."""

    class Kind(models.TextChoices):
        CAIXA = "caixa", "Caixa"
        BANCO = "banco", "Conta bancária"
        CARTAO = "cartao", "Maquininha / recebíveis"

    organization = models.ForeignKey("organizations.Organization", on_delete=models.CASCADE, related_name="contas")
    name = models.CharField(max_length=60)
    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.BANCO)
    bank = models.CharField(max_length=60, blank=True)
    opening_balance_cents = models.BigIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Categoria(TimeStampedModel):
    class Kind(models.TextChoices):
        RECEITA = "receita", "Receita"
        DESPESA = "despesa", "Despesa"

    organization = models.ForeignKey("organizations.Organization", on_delete=models.CASCADE, related_name="categorias")
    name = models.CharField(max_length=60)
    kind = models.CharField(max_length=10, choices=Kind.choices)
    # Categorias criadas pelo sistema (venda de veículo, custo de preparação…) não podem ser apagadas.
    system_code = models.CharField(max_length=30, blank=True)

    class Meta:
        ordering = ["kind", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "system_code"], condition=~models.Q(system_code=""), name="uniq_categoria_system"
            )
        ]

    def __str__(self):
        return self.name


class Lancamento(TimeStampedModel):
    class Kind(models.TextChoices):
        RECEBER = "receber", "A receber"
        PAGAR = "pagar", "A pagar"

    class Origin(models.TextChoices):
        MANUAL = "manual", "Manual"
        COMPRA = "compra", "Compra de veículo"
        CUSTO = "custo", "Custo de veículo"
        VENDA = "venda", "Venda de veículo"
        COMISSAO = "comissao", "Comissão de vendedor"
        CONSIGNACAO = "consignacao", "Repasse de consignado"
        GARANTIA = "garantia", "Garantia"

    organization = models.ForeignKey("organizations.Organization", on_delete=models.CASCADE, related_name="lancamentos")
    kind = models.CharField(max_length=8, choices=Kind.choices, db_index=True)
    origin = models.CharField(max_length=12, choices=Origin.choices, default=Origin.MANUAL)
    description = models.CharField(max_length=200)
    categoria = models.ForeignKey(Categoria, null=True, blank=True, on_delete=models.SET_NULL, related_name="lancamentos")
    pessoa = models.ForeignKey("pessoas.Pessoa", null=True, blank=True, on_delete=models.SET_NULL, related_name="lancamentos")
    vehicle = models.ForeignKey("estoque.Vehicle", null=True, blank=True, on_delete=models.SET_NULL, related_name="lancamentos")
    venda = models.ForeignKey("vendas.Venda", null=True, blank=True, on_delete=models.CASCADE, related_name="lancamentos")
    amount_cents = models.BigIntegerField()
    due_date = models.DateField(db_index=True)
    installment = models.PositiveSmallIntegerField(default=1)
    installments = models.PositiveSmallIntegerField(default=1)
    paid_at = models.DateField(null=True, blank=True)
    paid_cents = models.BigIntegerField(null=True, blank=True)
    conta = models.ForeignKey(Conta, null=True, blank=True, on_delete=models.SET_NULL, related_name="lancamentos")
    canceled = models.BooleanField(default=False)
    notes = models.TextField(blank=True)
    bank_ref = models.CharField("identificador do extrato", max_length=80, blank=True, db_index=True)

    class Meta:
        ordering = ["due_date", "id"]
        indexes = [models.Index(fields=["organization", "kind", "due_date"])]

    def __str__(self):
        return self.description

    @property
    def status(self) -> str:
        if self.canceled:
            return "cancelado"
        if self.paid_at:
            return "pago"
        if self.due_date < timezone.localdate():
            return "vencido"
        return "aberto"

    @property
    def signed_cents(self) -> int:
        value = self.paid_cents if self.paid_cents is not None else self.amount_cents
        return value if self.kind == self.Kind.RECEBER else -value
