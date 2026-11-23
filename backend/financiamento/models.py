"""Financiamento: ficha cadastral do cliente e propostas enviadas aos bancos."""

from django.db import models

from core.models import TimeStampedModel


class Ficha(TimeStampedModel):
    """Dados que os bancos pedem para analisar o crédito. Campos sensíveis ficam só aqui, nunca em logs."""

    class Occupation(models.TextChoices):
        CLT = "clt", "Assalariado (CLT)"
        AUTONOMO = "autonomo", "Autônomo"
        EMPRESARIO = "empresario", "Empresário"
        APOSENTADO = "aposentado", "Aposentado / pensionista"
        SERVIDOR = "servidor", "Servidor público"
        OUTRO = "outro", "Outro"

    organization = models.ForeignKey("organizations.Organization", on_delete=models.CASCADE, related_name="fichas")
    cliente = models.ForeignKey("pessoas.Pessoa", on_delete=models.PROTECT, related_name="fichas")
    vehicle = models.ForeignKey("estoque.Vehicle", null=True, blank=True, on_delete=models.SET_NULL, related_name="fichas")
    venda = models.ForeignKey("vendas.Venda", null=True, blank=True, on_delete=models.SET_NULL, related_name="fichas")
    mother_name = models.CharField("nome da mãe", max_length=150, blank=True)
    marital_status = models.CharField(max_length=30, blank=True)
    occupation = models.CharField(max_length=12, choices=Occupation.choices, default=Occupation.CLT)
    employer = models.CharField(max_length=120, blank=True)
    job_title = models.CharField(max_length=80, blank=True)
    employed_since = models.DateField(null=True, blank=True)
    monthly_income_cents = models.BigIntegerField(default=0)
    reference_name = models.CharField(max_length=120, blank=True)
    reference_phone = models.CharField(max_length=20, blank=True)
    vehicle_price_cents = models.BigIntegerField(default=0)
    down_payment_cents = models.BigIntegerField(default=0)
    term_months = models.PositiveSmallIntegerField(default=48)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]

    @property
    def financed_cents(self) -> int:
        return max(self.vehicle_price_cents - self.down_payment_cents, 0)


class Proposta(TimeStampedModel):
    class Status(models.TextChoices):
        ENVIADA = "enviada", "Enviada"
        ANALISE = "analise", "Em análise"
        APROVADA = "aprovada", "Aprovada"
        RECUSADA = "recusada", "Recusada"
        PAGA = "paga", "Paga ao lojista"
        CANCELADA = "cancelada", "Cancelada"

    organization = models.ForeignKey("organizations.Organization", on_delete=models.CASCADE, related_name="propostas")
    ficha = models.ForeignKey(Ficha, on_delete=models.CASCADE, related_name="propostas")
    bank = models.CharField(max_length=60)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ENVIADA)
    monthly_rate_bp = models.PositiveIntegerField("taxa ao mês (centésimos de %)", default=0)
    term_months = models.PositiveSmallIntegerField(default=48)
    financed_cents = models.BigIntegerField(default=0)
    installment_cents = models.BigIntegerField(default=0)
    cet_annual_bp = models.PositiveIntegerField("CET ao ano (centésimos de %)", default=0)
    dealer_return_cents = models.BigIntegerField("retorno da financeira para a loja", default=0)
    return_entry = models.OneToOneField("financeiro.Lancamento", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]
