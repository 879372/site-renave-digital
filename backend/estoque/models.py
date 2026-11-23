"""Estoque comercial da loja.

`Vehicle` é o carro como produto (preço, custos, fotos, situação). O espelho do
RENAVE continua em `renave.StockVehicle`, ligado aqui por um OneToOne opcional:
a loja pode cadastrar o carro antes (ou sem) dar entrada no RENAVE.
"""

import uuid

from django.db import models
from django.db.models import Sum

from core.models import TimeStampedModel


def _path(prefix, instance, filename):
    ext = (filename.rsplit(".", 1)[-1] if "." in filename else "bin").lower()[:5]
    return f"{prefix}/{instance.organization_id}/{uuid.uuid4().hex}.{ext}"


def vehicle_photo_path(instance, filename):
    return _path("veiculos", instance, filename)


def vehicle_document_path(instance, filename):
    return _path("documentos", instance, filename)


def avaliacao_photo_path(instance, filename):
    return _path("avaliacoes", instance, filename)


class Vehicle(TimeStampedModel):
    class Status(models.TextChoices):
        PREPARACAO = "preparacao", "Em preparação"
        DISPONIVEL = "disponivel", "Disponível"
        RESERVADO = "reservado", "Reservado"
        VENDIDO = "vendido", "Vendido"
        DEVOLVIDO = "devolvido", "Devolvido ao dono"
        TRANSFERIDO = "transferido", "Transferido para outra loja"

    class Ownership(models.TextChoices):
        PROPRIO = "proprio", "Próprio"
        CONSIGNADO = "consignado", "Consignado"

    class ConsignmentMode(models.TextChoices):
        COMISSAO = "comissao", "Comissão da loja (%)"
        LIQUIDO = "liquido", "Valor líquido garantido ao dono"

    class Kind(models.TextChoices):
        CARRO = "carro", "Carro"
        MOTO = "moto", "Moto"
        CAMINHAO = "caminhao", "Caminhão / utilitário"

    ACTIVE = (Status.PREPARACAO, Status.DISPONIVEL, Status.RESERVADO)

    organization = models.ForeignKey("organizations.Organization", on_delete=models.CASCADE, related_name="vehicles")
    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.CARRO)
    placa = models.CharField(max_length=7, blank=True, db_index=True)
    renavam = models.CharField(max_length=11, blank=True)
    chassi = models.CharField(max_length=17, blank=True)
    marca = models.CharField(max_length=60)
    modelo = models.CharField(max_length=80)
    versao = models.CharField(max_length=120, blank=True)
    ano_fabricacao = models.PositiveSmallIntegerField(null=True, blank=True)
    ano_modelo = models.PositiveSmallIntegerField(null=True, blank=True)
    cor = models.CharField(max_length=30, blank=True)
    combustivel = models.CharField(max_length=30, blank=True)
    cambio = models.CharField(max_length=30, blank=True)
    km = models.PositiveIntegerField(null=True, blank=True)
    portas = models.PositiveSmallIntegerField(null=True, blank=True)
    opcionais = models.JSONField(default=list, blank=True)
    descricao = models.TextField(blank=True)

    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PREPARACAO, db_index=True)
    ownership = models.CharField(max_length=10, choices=Ownership.choices, default=Ownership.PROPRIO)
    consignor = models.ForeignKey("pessoas.Pessoa", null=True, blank=True, on_delete=models.PROTECT, related_name="consignados")
    consignment_mode = models.CharField(max_length=10, choices=ConsignmentMode.choices, blank=True)
    consignment_value = models.PositiveIntegerField(
        default=0, help_text="Comissão em centésimos de % (500 = 5%) ou valor líquido em centavos, conforme o modo."
    )
    consignment_until = models.DateField(null=True, blank=True)

    supplier = models.ForeignKey("pessoas.Pessoa", null=True, blank=True, on_delete=models.PROTECT, related_name="vendidos_para_loja")
    purchase_date = models.DateField(null=True, blank=True)
    purchase_price_cents = models.BigIntegerField(default=0)
    entry_date = models.DateField(null=True, blank=True)
    price_cents = models.BigIntegerField(default=0, help_text="Preço anunciado.")
    min_price_cents = models.BigIntegerField(default=0, help_text="Menor preço aceito pelo gerente.")
    fipe_code = models.CharField(max_length=10, blank=True)
    fipe_price_cents = models.BigIntegerField(null=True, blank=True)
    fipe_reference = models.CharField(max_length=30, blank=True)
    sold_at = models.DateField(null=True, blank=True)

    renave = models.OneToOneField("renave.StockVehicle", null=True, blank=True, on_delete=models.SET_NULL, related_name="commercial")
    published = models.BooleanField("publicado no site", default=False)
    featured = models.BooleanField("destaque no site", default=False)
    location = models.CharField("localização / pátio", max_length=60, blank=True)
    keys = models.CharField("chaves", max_length=60, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["organization", "status", "-created_at"]),
            models.Index(fields=["organization", "published"]),
        ]

    def __str__(self):
        return f"{self.marca} {self.modelo} {self.placa}".strip()

    @property
    def title(self) -> str:
        year = f"{self.ano_fabricacao}/{self.ano_modelo}" if self.ano_fabricacao and self.ano_modelo else ""
        return " ".join(p for p in (self.marca, self.modelo, self.versao, year) if p)

    def costs_total(self) -> int:
        cached = getattr(self, "_prefetched_objects_cache", {}).get("costs")
        if cached is not None:
            return sum(c.amount_cents for c in cached)
        return self.costs.aggregate(v=Sum("amount_cents"))["v"] or 0

    def total_cost(self) -> int:
        """Custo total do carro para a loja (consignado não tem custo de compra)."""
        base = 0 if self.ownership == self.Ownership.CONSIGNADO else self.purchase_price_cents
        return base + self.costs_total()

    def consignor_payout(self, sale_cents: int) -> int:
        """Quanto vai para o dono do consignado numa venda por `sale_cents`."""
        if self.ownership != self.Ownership.CONSIGNADO:
            return 0
        if self.consignment_mode == self.ConsignmentMode.LIQUIDO:
            return min(self.consignment_value, sale_cents)
        return sale_cents - sale_cents * self.consignment_value // 10000


class VehiclePhoto(TimeStampedModel):
    organization = models.ForeignKey("organizations.Organization", on_delete=models.CASCADE, related_name="+")
    vehicle = models.ForeignKey(Vehicle, on_delete=models.CASCADE, related_name="photos")
    image = models.ImageField(upload_to=vehicle_photo_path)
    position = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["position", "id"]


class VehicleCost(TimeStampedModel):
    class Category(models.TextChoices):
        MECANICA = "mecanica", "Mecânica"
        FUNILARIA = "funilaria", "Funilaria e pintura"
        ESTETICA = "estetica", "Estética e higienização"
        PNEUS = "pneus", "Pneus"
        DOCUMENTACAO = "documentacao", "Documentação e taxas"
        DESPACHANTE = "despachante", "Despachante"
        TRANSPORTE = "transporte", "Transporte / guincho"
        COMISSAO = "comissao", "Comissão de compra"
        GARANTIA = "garantia", "Garantia / pós-venda"
        OUTROS = "outros", "Outros"

    organization = models.ForeignKey("organizations.Organization", on_delete=models.CASCADE, related_name="+")
    vehicle = models.ForeignKey(Vehicle, on_delete=models.CASCADE, related_name="costs")
    category = models.CharField(max_length=15, choices=Category.choices)
    description = models.CharField(max_length=200)
    supplier = models.ForeignKey("pessoas.Pessoa", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    amount_cents = models.BigIntegerField()
    date = models.DateField()
    payable = models.OneToOneField("financeiro.Lancamento", null=True, blank=True, on_delete=models.SET_NULL, related_name="vehicle_cost")

    class Meta:
        ordering = ["-date", "-id"]


class VehicleDocument(TimeStampedModel):
    class Kind(models.TextChoices):
        CRLV = "crlv", "CRLV"
        ATPV = "atpv", "ATPV / recibo"
        LAUDO = "laudo", "Laudo cautelar"
        VISTORIA = "vistoria", "Vistoria"
        NOTA = "nota", "Nota fiscal"
        OUTRO = "outro", "Outro"

    organization = models.ForeignKey("organizations.Organization", on_delete=models.CASCADE, related_name="+")
    vehicle = models.ForeignKey(Vehicle, on_delete=models.CASCADE, related_name="documents")
    kind = models.CharField(max_length=10, choices=Kind.choices)
    name = models.CharField(max_length=120)
    file = models.FileField(upload_to=vehicle_document_path)

    class Meta:
        ordering = ["-created_at"]


class Avaliacao(TimeStampedModel):
    """Avaliação de um carro que a loja pode comprar (de particular ou na troca)."""

    class Status(models.TextChoices):
        ABERTA = "aberta", "Em avaliação"
        APROVADA = "aprovada", "Aprovada"
        RECUSADA = "recusada", "Recusada"
        COMPRADA = "comprada", "Comprada"

    organization = models.ForeignKey("organizations.Organization", on_delete=models.CASCADE, related_name="avaliacoes")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ABERTA, db_index=True)
    cliente = models.ForeignKey("pessoas.Pessoa", null=True, blank=True, on_delete=models.SET_NULL, related_name="avaliacoes")
    evaluator = models.ForeignKey("accounts.User", null=True, on_delete=models.SET_NULL, related_name="+")
    kind = models.CharField(max_length=10, choices=Vehicle.Kind.choices, default=Vehicle.Kind.CARRO)
    placa = models.CharField(max_length=7, blank=True)
    marca = models.CharField(max_length=60)
    modelo = models.CharField(max_length=80)
    versao = models.CharField(max_length=120, blank=True)
    ano_fabricacao = models.PositiveSmallIntegerField(null=True, blank=True)
    ano_modelo = models.PositiveSmallIntegerField(null=True, blank=True)
    cor = models.CharField(max_length=30, blank=True)
    km = models.PositiveIntegerField(null=True, blank=True)
    checklist = models.JSONField(default=dict, blank=True, help_text="{item: 'ok' | 'atencao' | 'ruim'}")
    notes = models.TextField(blank=True)
    fipe_code = models.CharField(max_length=10, blank=True)
    fipe_price_cents = models.BigIntegerField(null=True, blank=True)
    estimated_repairs_cents = models.BigIntegerField(default=0)
    offer_cents = models.BigIntegerField(default=0)
    approved_by = models.ForeignKey("accounts.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    vehicle = models.OneToOneField(Vehicle, null=True, blank=True, on_delete=models.SET_NULL, related_name="avaliacao")

    class Meta:
        ordering = ["-created_at"]


class AvaliacaoFoto(TimeStampedModel):
    organization = models.ForeignKey("organizations.Organization", on_delete=models.CASCADE, related_name="+")
    avaliacao = models.ForeignKey(Avaliacao, on_delete=models.CASCADE, related_name="photos")
    image = models.ImageField(upload_to=avaliacao_photo_path)
    label = models.CharField(max_length=60, blank=True)


class PlateQuery(models.Model):
    """Consulta de placa (para a franquia mensal do plano e para não cobrar duas vezes a mesma placa)."""

    organization = models.ForeignKey("organizations.Organization", on_delete=models.CASCADE, related_name="plate_queries")
    placa = models.CharField(max_length=7)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    charged_cents = models.PositiveIntegerField(default=0)
    data = models.JSONField(default=dict)

    class Meta:
        indexes = [models.Index(fields=["organization", "placa", "-created_at"])]
