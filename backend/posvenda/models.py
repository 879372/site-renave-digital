"""Garantia dos carros vendidos e ocorrências de pós-venda."""

from django.db import models
from django.utils import timezone

from core.models import TimeStampedModel


class Garantia(TimeStampedModel):
    organization = models.ForeignKey("organizations.Organization", on_delete=models.CASCADE, related_name="garantias")
    venda = models.OneToOneField("vendas.Venda", on_delete=models.CASCADE, related_name="garantia")
    starts_on = models.DateField()
    ends_on = models.DateField(db_index=True)
    km_limit = models.PositiveIntegerField(null=True, blank=True)
    coverage = models.TextField("cobertura", default="Motor e câmbio, conforme o Código de Defesa do Consumidor.")

    class Meta:
        ordering = ["-ends_on"]

    @property
    def is_active(self) -> bool:
        return self.ends_on >= timezone.localdate()


class Ocorrencia(TimeStampedModel):
    class Status(models.TextChoices):
        ABERTA = "aberta", "Aberta"
        ANDAMENTO = "andamento", "Em andamento"
        RESOLVIDA = "resolvida", "Resolvida"
        NEGADA = "negada", "Fora da garantia"

    organization = models.ForeignKey("organizations.Organization", on_delete=models.CASCADE, related_name="ocorrencias")
    garantia = models.ForeignKey(Garantia, on_delete=models.CASCADE, related_name="ocorrencias")
    description = models.TextField()
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ABERTA)
    cost_cents = models.BigIntegerField(default=0)
    resolution = models.TextField(blank=True)
    lancamento = models.OneToOneField("financeiro.Lancamento", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")

    class Meta:
        ordering = ["-created_at"]
