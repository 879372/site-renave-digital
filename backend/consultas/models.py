import json

from django.db import models

from core.models import TimeStampedModel
from vault.crypto import decrypt_bytes, encrypt_bytes


class InputType(models.TextChoices):
    PLACA = "PLACA", "Placa"
    CHASSI = "CHASSI", "Chassi"
    RENAVAM = "RENAVAM", "RENAVAM"
    MOTOR = "MOTOR", "Motor"
    CPF = "CPF", "CPF"
    CNPJ = "CNPJ", "CNPJ"


class Product(models.Model):
    """Produto vendido na plataforma. `sku` é o código interno do fornecedor e nunca vai para o front;
    o front usa `code`."""

    class Category(models.TextChoices):
        COMPLETA = "completa", "Pacotes completos"
        RESTRICOES = "restricoes", "Restrições e riscos"
        HISTORICO = "historico", "Histórico"
        PRECO = "preco", "Preço e FIPE"
        CADASTRO = "cadastro", "Dados cadastrais"
        DEBITOS = "debitos", "Débitos e documentos"
        EMPRESA = "empresa", "Empresas"

    code = models.SlugField(max_length=60, unique=True, help_text="Código público do produto (exibido no app).")
    sku = models.CharField(max_length=80, unique=True, help_text="Código do produto no fornecedor (interno).")
    name = models.CharField(max_length=120)
    description = models.CharField(max_length=300, blank=True)
    category = models.CharField(max_length=20, choices=Category.choices, default=Category.CADASTRO)
    input_type = models.CharField(max_length=10, choices=InputType.choices, default=InputType.PLACA)
    cost_cents = models.PositiveIntegerField(default=0, help_text="Custo no fornecedor.")
    price_cents = models.PositiveIntegerField(help_text="Preço de venda ao cliente.")
    is_async = models.BooleanField(default=False, help_text="Produtos que terminam depois (ex.: CRLV-e).")
    is_active = models.BooleanField(default=False)
    is_featured = models.BooleanField(default=False)
    sort_order = models.PositiveSmallIntegerField(default=100)
    highlights = models.JSONField(default=list, blank=True, help_text="Itens exibidos no card do produto.")

    class Meta:
        ordering = ["sort_order", "name"]
        verbose_name = "produto de consulta"

    def __str__(self):
        return f"{self.name} ({self.sku})"


class Consulta(TimeStampedModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Na fila"
        PROCESSING = "processing", "Processando"
        SUCCESS = "success", "Concluída"
        NOT_FOUND = "not_found", "Nada consta"
        FAILED = "failed", "Falhou"

    class Purpose(models.TextChoices):
        COMPRA = "compra", "Avaliação para compra"
        VENDA = "venda", "Preparação para venda"
        FINANCIAMENTO = "financiamento", "Análise de crédito/financiamento"
        DOCUMENTACAO = "documentacao", "Regularização documental"
        OUTRO = "outro", "Outro"

    organization = models.ForeignKey("organizations.Organization", on_delete=models.PROTECT, related_name="consultas")
    user = models.ForeignKey("accounts.User", null=True, on_delete=models.SET_NULL, related_name="+")
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="consultas")
    sku = models.CharField(max_length=80)
    input_type = models.CharField(max_length=10, choices=InputType.choices)
    input_value = models.CharField(max_length=30, db_index=True)
    purpose = models.CharField(max_length=20, choices=Purpose.choices, default=Purpose.COMPRA)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING, db_index=True)
    price_cents = models.PositiveIntegerField()
    charged_cents = models.PositiveIntegerField(default=0)
    provider_cost_cents = models.PositiveIntegerField(default=0)
    provider_consulta_id = models.CharField(max_length=80, blank=True, db_index=True)
    reservation = models.OneToOneField("wallet.Reservation", null=True, blank=True, on_delete=models.PROTECT, related_name="consulta")
    result_encrypted = models.BinaryField(null=True, blank=True, editable=False)
    message = models.CharField(max_length=300, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["organization", "-created_at"]), models.Index(fields=["status", "created_at"])]

    @property
    def idempotency_key(self) -> str:
        return f"rd-consulta-{self.public_id}"

    def set_result(self, data: dict) -> None:
        self.result_encrypted = encrypt_bytes(json.dumps(data, ensure_ascii=False).encode(), f"consulta:{self.public_id}".encode())

    def get_result(self) -> dict | None:
        if not self.result_encrypted:
            return None
        return json.loads(decrypt_bytes(bytes(self.result_encrypted), f"consulta:{self.public_id}".encode()))
