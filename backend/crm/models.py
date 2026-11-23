"""CRM: leads, funil, interações e tarefas de retorno."""

from django.conf import settings
from django.db import models

from core.models import TimeStampedModel


class Lead(TimeStampedModel):
    class Stage(models.TextChoices):
        NOVO = "novo", "Novo"
        CONTATO = "contato", "Em contato"
        VISITA = "visita", "Visita agendada"
        PROPOSTA = "proposta", "Proposta"
        GANHO = "ganho", "Vendido"
        PERDIDO = "perdido", "Perdido"

    class Source(models.TextChoices):
        LOJA = "loja", "Loja física"
        SITE = "site", "Site da loja"
        WHATSAPP = "whatsapp", "WhatsApp"
        INSTAGRAM = "instagram", "Instagram"
        FACEBOOK = "facebook", "Facebook"
        OLX = "olx", "OLX"
        WEBMOTORS = "webmotors", "Webmotors"
        MERCADOLIVRE = "mercadolivre", "Mercado Livre"
        ICARROS = "icarros", "iCarros"
        INDICACAO = "indicacao", "Indicação"
        OUTRO = "outro", "Outro"

    organization = models.ForeignKey("organizations.Organization", on_delete=models.CASCADE, related_name="leads")
    name = models.CharField(max_length=150)
    phone = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    source = models.CharField(max_length=15, choices=Source.choices, default=Source.LOJA)
    stage = models.CharField(max_length=10, choices=Stage.choices, default=Stage.NOVO, db_index=True)
    vehicle = models.ForeignKey("estoque.Vehicle", null=True, blank=True, on_delete=models.SET_NULL, related_name="leads")
    interest = models.CharField("interesse", max_length=200, blank=True)
    budget_cents = models.BigIntegerField(null=True, blank=True)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="leads")
    pessoa = models.ForeignKey("pessoas.Pessoa", null=True, blank=True, on_delete=models.SET_NULL, related_name="leads")
    lost_reason = models.CharField(max_length=200, blank=True)
    message = models.TextField(blank=True)
    position = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["position", "-created_at"]
        indexes = [models.Index(fields=["organization", "stage"])]

    def __str__(self):
        return self.name


class Interacao(TimeStampedModel):
    class Kind(models.TextChoices):
        NOTA = "nota", "Anotação"
        LIGACAO = "ligacao", "Ligação"
        WHATSAPP = "whatsapp", "WhatsApp"
        EMAIL = "email", "E-mail"
        VISITA = "visita", "Visita"
        ETAPA = "etapa", "Mudança de etapa"

    lead = models.ForeignKey(Lead, on_delete=models.CASCADE, related_name="interacoes")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.NOTA)
    text = models.TextField()

    class Meta:
        ordering = ["-created_at"]


class Tarefa(TimeStampedModel):
    organization = models.ForeignKey("organizations.Organization", on_delete=models.CASCADE, related_name="tarefas")
    lead = models.ForeignKey(Lead, null=True, blank=True, on_delete=models.CASCADE, related_name="tarefas")
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="tarefas")
    title = models.CharField(max_length=200)
    due_at = models.DateTimeField(db_index=True)
    done_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["done_at", "due_at"]
