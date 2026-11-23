from django.conf import settings
from django.db import models

from core.documents import validate_cnpj, validate_document
from core.models import TimeStampedModel


class Organization(TimeStampedModel):
    class Kind(models.TextChoices):
        REVENDA = "revenda", "Loja / revenda"
        CONCESSIONARIA = "concessionaria", "Concessionária"
        DESPACHANTE = "despachante", "Despachante"
        CONTADOR = "contador", "Contador"

    class TaxRegime(models.TextChoices):
        SIMPLES = "1", "Simples Nacional"
        SIMPLES_EXCESSO = "2", "Simples Nacional - excesso de sublimite"
        NORMAL = "3", "Regime normal"
        MEI = "4", "MEI"

    cnpj = models.CharField("CNPJ", max_length=14, unique=True, validators=[validate_cnpj])
    legal_name = models.CharField("razão social", max_length=150)
    trade_name = models.CharField("nome fantasia", max_length=150, blank=True)
    kind = models.CharField(max_length=20, choices=Kind.choices, default=Kind.REVENDA)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=20, blank=True)
    state_registration = models.CharField("inscrição estadual", max_length=20, blank=True)
    tax_regime = models.CharField(max_length=1, choices=TaxRegime.choices, blank=True)
    zip_code = models.CharField(max_length=8, blank=True)
    street = models.CharField(max_length=120, blank=True)
    number = models.CharField(max_length=10, blank=True)
    complement = models.CharField(max_length=60, blank=True)
    district = models.CharField(max_length=60, blank=True)
    city = models.CharField(max_length=80, blank=True)
    city_ibge = models.CharField("código IBGE", max_length=7, blank=True)
    uf = models.CharField(max_length=2, blank=True)
    is_active = models.BooleanField(default=True)
    mfa_required = models.BooleanField("exigir 2FA de todos os membros", default=False)

    class Meta:
        verbose_name = "empresa"

    def __str__(self):
        return self.trade_name or self.legal_name


class Role(models.TextChoices):
    OWNER = "owner", "Proprietário"
    ADMIN = "admin", "Administrador"
    OPERATOR = "operator", "Operador"
    FINANCE = "finance", "Financeiro"
    SELLER = "vendedor", "Vendedor"
    VIEWER = "viewer", "Somente leitura"


# Permissões por papel. "view" é implícito para todos os membros ativos.
ROLE_PERMISSIONS: dict[str, set[str]] = {
    Role.OWNER: {"*"},
    Role.ADMIN: {
        "org.manage",
        "members.manage",
        "vault.manage",
        "wallet.manage",
        "audit.view",
        "consultas.run",
        "renave.operate",
        "comunicacao.operate",
        "fiscal.emit",
        "fiscal.configure",
        "clients.manage",
        "billing.manage",
        "estoque.manage",
        "vendas.operate",
        "financeiro.manage",
    },
    Role.OPERATOR: {
        "consultas.run",
        "renave.operate",
        "comunicacao.operate",
        "fiscal.emit",
        "clients.manage",
        "estoque.manage",
        "vendas.operate",
    },
    Role.FINANCE: {"wallet.manage", "fiscal.emit", "audit.view", "billing.manage", "financeiro.manage"},
    # Vendedor: atende, negocia e vende; não mexe em custos, financeiro nem configurações.
    Role.SELLER: {"vendas.operate", "consultas.run"},
    Role.VIEWER: set(),
}


class Membership(TimeStampedModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="memberships")
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="memberships")
    role = models.CharField(max_length=10, choices=Role.choices, default=Role.OPERATOR)
    is_active = models.BooleanField(default=True)
    invited_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")

    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "organization"], name="uniq_membership")]

    def has_perm(self, perm: str) -> bool:
        if not self.is_active:
            return False
        if perm == "view":
            return True
        granted = ROLE_PERMISSIONS.get(self.role, set())
        return "*" in granted or perm in granted


class Invitation(TimeStampedModel):
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="invitations")
    email = models.EmailField()
    role = models.CharField(max_length=10, choices=Role.choices, default=Role.OPERATOR)
    token_hash = models.CharField(max_length=64, unique=True)
    expires_at = models.DateTimeField()
    accepted_at = models.DateTimeField(null=True, blank=True)
    invited_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")


class ClientCompany(TimeStampedModel):
    """Cliente atendido pela empresa (ex.: lojas de um despachante) para operar o RENAVE em nome dele."""

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="clients")
    document = models.CharField("CPF/CNPJ", max_length=14, validators=[validate_document])
    name = models.CharField(max_length=150)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=20, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["organization", "document"], name="uniq_client_doc")]
        ordering = ["name"]

    def __str__(self):
        return self.name
