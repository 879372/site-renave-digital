"""Planos, assinaturas e faturas do Revenda Digital.

Cada empresa revenda tem uma `Subscription`. A fatura é gerada pela plataforma
(mensalidade + consumo pós-pago do mês) e cobrada por uma cobrança avulsa no
gateway, que devolve o link de pagamento (Pix, boleto ou cartão).
"""

from django.db import models

from core.models import TimeStampedModel


class Feature(models.TextChoices):
    RENAVE = "renave", "RENAVE"
    ESTOQUE = "estoque", "Estoque e vendas"
    FISCAL = "fiscal", "Nota fiscal"
    FINANCEIRO = "financeiro", "Financeiro"
    CUSTOS = "custos", "Custos por veículo"
    CONTRATOS = "contratos", "Contratos"
    AVALIACAO = "avaliacao", "Compra e avaliação"
    CRM = "crm", "CRM e leads"
    COMISSOES = "comissoes", "Vendedores e comissões"
    CONSIGNACAO = "consignacao", "Consignação"
    VITRINE = "vitrine", "Site da loja e anúncios"
    FINANCIAMENTO = "financiamento", "Financiamento"
    MULTILOJA = "multiloja", "Multi-loja"
    RELATORIOS = "relatorios", "Relatórios avançados"
    POSVENDA = "posvenda", "Pós-venda e garantia"
    ASSINATURA = "assinatura", "Assinatura eletrônica"
    CONCILIACAO = "conciliacao", "Conciliação bancária"


class Plan(models.Model):
    class Code(models.TextChoices):
        GRATIS = "gratis", "Grátis"
        ESSENCIAL = "essencial", "Essencial"
        PROFISSIONAL = "profissional", "Profissional"
        PREMIUM = "premium", "Premium"

    code = models.CharField(max_length=20, choices=Code.choices, unique=True)
    name = models.CharField(max_length=60)
    monthly_price_cents = models.PositiveIntegerField(default=0)
    annual_price_cents = models.PositiveIntegerField(default=0, help_text="Valor cobrado de uma vez no ciclo anual.")
    vehicle_limit = models.PositiveIntegerField(null=True, blank=True, help_text="Vazio = ilimitado.")
    user_limit = models.PositiveIntegerField(null=True, blank=True, help_text="Vazio = ilimitado.")
    plate_queries_included = models.PositiveIntegerField(default=0)
    features = models.JSONField(default=list, blank=True)
    postpaid = models.BooleanField(default=False, help_text="Operações cobradas por uso entram na fatura do mês.")
    credit_limit_cents = models.PositiveIntegerField(default=0, help_text="Limite de consumo pós-pago por mês.")
    extra_store_price_cents = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["sort_order"]
        verbose_name = "plano"

    def __str__(self):
        return self.name

    @property
    def is_free(self) -> bool:
        return self.monthly_price_cents == 0

    def price_for(self, cycle: str) -> int:
        return self.annual_price_cents if cycle == Subscription.Cycle.ANNUAL else self.monthly_price_cents

    def has_feature(self, feature: str) -> bool:
        return feature in self.features


class Subscription(TimeStampedModel):
    class Status(models.TextChoices):
        TRIALING = "trialing", "Em teste"
        ACTIVE = "active", "Ativa"
        PAST_DUE = "past_due", "Pagamento atrasado"
        SUSPENDED = "suspended", "Suspensa por falta de pagamento"

    class Cycle(models.TextChoices):
        MONTHLY = "monthly", "Mensal"
        ANNUAL = "annual", "Anual"

    organization = models.OneToOneField("organizations.Organization", on_delete=models.CASCADE, related_name="subscription")
    plan = models.ForeignKey(Plan, on_delete=models.PROTECT, related_name="subscriptions")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE, db_index=True)
    cycle = models.CharField(max_length=10, choices=Cycle.choices, default=Cycle.MONTHLY)
    trial_ends_at = models.DateTimeField(null=True, blank=True)
    paid_through = models.DateField(null=True, blank=True, help_text="Mensalidade paga até esta data.")
    next_billing_date = models.DateField(null=True, blank=True, db_index=True, help_text="Próximo fechamento mensal.")
    scheduled_plan = models.ForeignKey(
        Plan, null=True, blank=True, on_delete=models.PROTECT, related_name="+", help_text="Plano que entra no fim do período pago."
    )
    scheduled_cycle = models.CharField(max_length=10, choices=Cycle.choices, blank=True)

    class Meta:
        verbose_name = "assinatura"

    def __str__(self):
        return f"{self.organization} — {self.plan}"


class GatewayCustomer(models.Model):
    """Cadastro da empresa no gateway de pagamento (usado em faturas e recargas)."""

    organization = models.ForeignKey("organizations.Organization", on_delete=models.CASCADE, related_name="gateway_customers")
    provider = models.CharField(max_length=20)
    customer_id = models.CharField(max_length=60)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["organization", "provider"], name="uniq_gateway_customer")]


class Invoice(TimeStampedModel):
    class Status(models.TextChoices):
        OPEN = "open", "Em aberto"
        PAID = "paid", "Paga"
        OVERDUE = "overdue", "Vencida"
        CANCELED = "canceled", "Cancelada"

    class Kind(models.TextChoices):
        PLAN_CHANGE = "plan_change", "Contratação ou troca de plano"
        RENEWAL = "renewal", "Fechamento mensal"

    organization = models.ForeignKey("organizations.Organization", on_delete=models.PROTECT, related_name="invoices")
    subscription = models.ForeignKey(Subscription, on_delete=models.PROTECT, related_name="invoices")
    kind = models.CharField(max_length=12, choices=Kind.choices)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.OPEN, db_index=True)
    total_cents = models.BigIntegerField(default=0)
    due_date = models.DateField()
    # Contratação/troca: o plano só muda quando esta fatura é paga.
    target_plan = models.ForeignKey(Plan, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    target_cycle = models.CharField(max_length=10, choices=Subscription.Cycle.choices, blank=True)
    provider = models.CharField(max_length=20, blank=True)
    provider_payment_id = models.CharField(max_length=60, blank=True, db_index=True)
    payment_url = models.URLField(blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    canceled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "fatura"
        indexes = [models.Index(fields=["organization", "-created_at"])]

    def __str__(self):
        return f"Fatura {self.public_id.hex[:8]} — {self.organization}"


class InvoiceItem(models.Model):
    class Kind(models.TextChoices):
        PLAN = "plan", "Mensalidade"
        PRORATION = "proration", "Crédito do plano anterior"
        USAGE = "usage", "Consumo do período"
        EXTRA_STORE = "extra_store", "Loja extra"
        ADJUSTMENT = "adjustment", "Ajuste"

    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name="items")
    kind = models.CharField(max_length=12, choices=Kind.choices)
    description = models.CharField(max_length=200)
    quantity = models.PositiveIntegerField(default=1)
    total_cents = models.BigIntegerField()

    class Meta:
        ordering = ["id"]
