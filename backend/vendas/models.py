"""Vendas de veículos, formas de pagamento, comissões e metas."""

from django.conf import settings
from django.db import models

from core.models import TimeStampedModel


class Venda(TimeStampedModel):
    vehicle_was_published = models.BooleanField(default=False, editable=False)

    class Status(models.TextChoices):
        PROPOSTA = "proposta", "Proposta"
        RESERVADA = "reservada", "Reservada (com sinal)"
        FECHADA = "fechada", "Fechada"
        CANCELADA = "cancelada", "Cancelada"

    organization = models.ForeignKey("organizations.Organization", on_delete=models.CASCADE, related_name="vendas")
    vehicle = models.ForeignKey("estoque.Vehicle", on_delete=models.PROTECT, related_name="vendas")
    cliente = models.ForeignKey("pessoas.Pessoa", on_delete=models.PROTECT, related_name="compras")
    seller = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="vendas")
    lead = models.ForeignKey("crm.Lead", null=True, blank=True, on_delete=models.SET_NULL, related_name="vendas")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PROPOSTA, db_index=True)
    price_cents = models.BigIntegerField(help_text="Valor de venda negociado.")
    notes = models.TextField(blank=True)
    reserved_until = models.DateField(null=True, blank=True)
    closed_at = models.DateField(null=True, blank=True, db_index=True)
    canceled_at = models.DateTimeField(null=True, blank=True)
    cancel_reason = models.CharField(max_length=200, blank=True)
    # Calculados no fechamento (ficam congelados para relatórios).
    cost_cents = models.BigIntegerField(default=0)
    consignor_payout_cents = models.BigIntegerField(default=0)
    profit_cents = models.BigIntegerField(default=0)
    commission_cents = models.BigIntegerField(default=0)
    commission_paid = models.BooleanField(default=False)
    nota = models.ForeignKey("fiscal.NotaFiscal", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["organization", "status", "-closed_at"])]

    def __str__(self):
        return f"Venda {self.vehicle} para {self.cliente}"

    def paid_total(self) -> int:
        return sum(p.amount_cents for p in self.pagamentos.all())


class Pagamento(models.Model):
    class Method(models.TextChoices):
        DINHEIRO = "dinheiro", "Dinheiro"
        PIX = "pix", "Pix"
        TRANSFERENCIA = "transferencia", "Transferência"
        DEBITO = "debito", "Cartão de débito"
        CREDITO = "credito", "Cartão de crédito"
        BOLETO = "boleto", "Boleto / promissória"
        FINANCIAMENTO = "financiamento", "Financiamento bancário"
        TROCA = "troca", "Veículo na troca"
        SINAL = "sinal", "Sinal"

    venda = models.ForeignKey(Venda, on_delete=models.CASCADE, related_name="pagamentos")
    method = models.CharField(max_length=15, choices=Method.choices)
    amount_cents = models.BigIntegerField()
    installments = models.PositiveSmallIntegerField(default=1)
    first_due = models.DateField(null=True, blank=True)
    bank = models.CharField(max_length=60, blank=True, help_text="Banco do financiamento.")
    trade_in = models.OneToOneField("estoque.Avaliacao", null=True, blank=True, on_delete=models.PROTECT, related_name="pagamento_troca")

    class Meta:
        ordering = ["id"]


class RegraComissao(models.Model):
    class Mode(models.TextChoices):
        SOBRA = "sobra", "Percentual sobre o lucro (sobra)"
        PRECO = "preco", "Percentual sobre o valor da venda"
        FIXO = "fixo", "Valor fixo por carro"

    organization = models.OneToOneField("organizations.Organization", on_delete=models.CASCADE, related_name="regra_comissao")
    mode = models.CharField(max_length=10, choices=Mode.choices, default=Mode.SOBRA)
    value = models.PositiveIntegerField(default=1000, help_text="Centésimos de % (1000 = 10%) ou centavos, se fixo.")
    min_cents = models.PositiveIntegerField(default=0, help_text="Comissão mínima por carro.")

    def compute(self, *, price_cents: int, profit_cents: int) -> int:
        if self.mode == self.Mode.FIXO:
            amount = self.value
        elif self.mode == self.Mode.PRECO:
            amount = price_cents * self.value // 10000
        else:
            amount = max(profit_cents, 0) * self.value // 10000
        return max(amount, self.min_cents)


class Meta(models.Model):
    organization = models.ForeignKey("organizations.Organization", on_delete=models.CASCADE, related_name="metas")
    seller = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="metas")
    month = models.DateField(help_text="Primeiro dia do mês.")
    units = models.PositiveSmallIntegerField(default=0)
    revenue_cents = models.BigIntegerField(default=0)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["organization", "seller", "month"], name="uniq_meta_mes")]
