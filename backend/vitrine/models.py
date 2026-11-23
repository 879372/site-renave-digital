"""Site público da loja (<slug>.STOREFRONT_DOMAIN) e anúncios em portais."""

from django.core.validators import RegexValidator
from django.db import models

from core.models import TimeStampedModel

RESERVED = {"www", "app", "api", "admin", "painel", "mail", "static", "media", "blog", "suporte", "loja"}

slug_validator = RegexValidator(r"^[a-z0-9](?:[a-z0-9-]{1,38}[a-z0-9])$", "Use de 3 a 40 letras minúsculas, números ou hífen.")


class Site(TimeStampedModel):
    organization = models.OneToOneField("organizations.Organization", on_delete=models.CASCADE, related_name="site")
    slug = models.CharField(max_length=40, unique=True, validators=[slug_validator])
    is_published = models.BooleanField(default=False)
    title = models.CharField(max_length=80)
    about = models.TextField(blank=True)
    whatsapp = models.CharField(max_length=20, blank=True)
    phone = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    address = models.CharField(max_length=200, blank=True)
    instagram = models.CharField(max_length=60, blank=True)
    accent_color = models.CharField(max_length=7, default="#047857")
    logo = models.ImageField(upload_to="sites/", blank=True)
    # Token secreto do feed XML para portais (o portal busca o estoque por esta URL).
    feed_token = models.CharField(max_length=40, blank=True)

    def __str__(self):
        return self.slug


class Anuncio(TimeStampedModel):
    """Situação de um veículo em um portal (publicação pelo feed ou integração do portal)."""

    class Portal(models.TextChoices):
        OLX = "olx", "OLX"
        WEBMOTORS = "webmotors", "Webmotors"
        MERCADOLIVRE = "mercadolivre", "Mercado Livre"
        ICARROS = "icarros", "iCarros"
        MOBIAUTO = "mobiauto", "Mobiauto"

    class Status(models.TextChoices):
        ATIVO = "ativo", "No feed"
        PAUSADO = "pausado", "Pausado"
        ERRO = "erro", "Erro no portal"

    organization = models.ForeignKey("organizations.Organization", on_delete=models.CASCADE, related_name="anuncios")
    vehicle = models.ForeignKey("estoque.Vehicle", on_delete=models.CASCADE, related_name="anuncios")
    portal = models.CharField(max_length=15, choices=Portal.choices)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ATIVO)
    external_id = models.CharField(max_length=80, blank=True)
    url = models.URLField(blank=True)
    message = models.CharField(max_length=300, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["vehicle", "portal"], name="uniq_anuncio_portal")]
