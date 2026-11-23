"""Modelos de contrato e documentos gerados (com assinatura eletrônica opcional)."""

from django.db import models

from core.models import TimeStampedModel


class Modelo(TimeStampedModel):
    class Kind(models.TextChoices):
        COMPRA_VENDA = "compra_venda", "Contrato de compra e venda"
        CONSIGNACAO = "consignacao", "Contrato de consignação"
        PROCURACAO = "procuracao", "Procuração"
        GARANTIA = "garantia", "Termo de garantia"
        RECIBO = "recibo", "Recibo"
        COMPRA = "compra", "Contrato de compra (loja comprando)"

    organization = models.ForeignKey("organizations.Organization", on_delete=models.CASCADE, related_name="modelos_contrato")
    kind = models.CharField(max_length=15, choices=Kind.choices)
    title = models.CharField(max_length=120)
    body = models.TextField(help_text="Texto com variáveis entre chaves duplas, ex.: {{cliente.nome}}.")
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["kind", "title"]

    def __str__(self):
        return self.title


class Documento(TimeStampedModel):
    class Signature(models.TextChoices):
        NONE = "", "Sem assinatura eletrônica"
        PENDING = "pending", "Aguardando assinaturas"
        SIGNED = "signed", "Assinado"
        REFUSED = "refused", "Recusado"

    organization = models.ForeignKey("organizations.Organization", on_delete=models.CASCADE, related_name="documentos")
    modelo = models.ForeignKey(Modelo, null=True, on_delete=models.SET_NULL, related_name="documentos")
    kind = models.CharField(max_length=15, choices=Modelo.Kind.choices)
    title = models.CharField(max_length=160)
    content = models.TextField()
    vehicle = models.ForeignKey("estoque.Vehicle", null=True, blank=True, on_delete=models.SET_NULL, related_name="documentos_gerados")
    venda = models.ForeignKey("vendas.Venda", null=True, blank=True, on_delete=models.SET_NULL, related_name="documentos")
    pessoa = models.ForeignKey("pessoas.Pessoa", null=True, blank=True, on_delete=models.SET_NULL, related_name="documentos")
    created_by = models.ForeignKey("accounts.User", null=True, on_delete=models.SET_NULL, related_name="+")
    signature_status = models.CharField(max_length=10, choices=Signature.choices, blank=True)
    signature_provider_id = models.CharField(max_length=80, blank=True, db_index=True)
    signature_links = models.JSONField(default=list, blank=True)
    signed_file_url = models.URLField(blank=True, max_length=500)

    class Meta:
        ordering = ["-created_at"]
