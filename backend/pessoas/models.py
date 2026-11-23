from django.db import models

from core.documents import validate_document
from core.models import TimeStampedModel


class Pessoa(TimeStampedModel):
    """Cadastro único: cliente, fornecedor e/ou dono de veículo consignado."""

    organization = models.ForeignKey("organizations.Organization", on_delete=models.CASCADE, related_name="pessoas")
    documento = models.CharField("CPF/CNPJ", max_length=14, blank=True, validators=[validate_document], db_index=True)
    nome = models.CharField(max_length=150)
    email = models.EmailField(blank=True)
    telefone = models.CharField(max_length=20, blank=True)
    data_nascimento = models.DateField(null=True, blank=True)
    rg_ie = models.CharField("RG / inscrição estadual", max_length=20, blank=True)
    cep = models.CharField(max_length=8, blank=True)
    logradouro = models.CharField(max_length=120, blank=True)
    numero = models.CharField(max_length=10, blank=True)
    complemento = models.CharField(max_length=60, blank=True)
    bairro = models.CharField(max_length=60, blank=True)
    cidade = models.CharField(max_length=80, blank=True)
    cidade_ibge = models.CharField(max_length=7, blank=True)
    uf = models.CharField(max_length=2, blank=True)
    is_cliente = models.BooleanField(default=True)
    is_fornecedor = models.BooleanField(default=False)
    observacoes = models.TextField(blank=True)

    class Meta:
        ordering = ["nome"]
        constraints = [
            models.UniqueConstraint(fields=["organization", "documento"], condition=~models.Q(documento=""), name="uniq_pessoa_documento")
        ]
        indexes = [models.Index(fields=["organization", "nome"])]

    def __str__(self):
        return self.nome

    @property
    def endereco_completo(self) -> str:
        parts = [f"{self.logradouro}, {self.numero}".strip(", "), self.complemento, self.bairro, f"{self.cidade}/{self.uf}".strip("/")]
        return " — ".join(p for p in parts if p)
