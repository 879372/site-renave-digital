"""Regras do estoque: limite do plano, fotos, custos, consulta de placa/FIPE, compra pela avaliação e RENAVE."""

import io
from datetime import timedelta

from django.conf import settings
from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone
from PIL import Image, ImageOps, UnidentifiedImageError

from audit.service import record
from billing.entitlements import check_limit, has_feature, limit
from core.exceptions import BusinessError, InsufficientBalance, ProviderUnavailable
from integrations.http import ProviderError
from wallet import service as wallet
from wallet.models import ServicePrice

from .models import Avaliacao, PlateQuery, Vehicle, VehicleCost

MAX_SIDE = 1600
PLATE_CACHE_DAYS = 30


# --- limite do plano -------------------------------------------------------------------------


def active_count(organization) -> int:
    return Vehicle.objects.filter(organization=organization, status__in=Vehicle.ACTIVE).count()


def check_vehicle_limit(organization) -> None:
    check_limit(organization, "vehicles", active_count(organization), "veículos em estoque")


# --- fotos -----------------------------------------------------------------------------------


def process_image(upload) -> ContentFile:
    """Valida que é imagem, corrige a rotação do celular, reduz para no máximo 1600 px e salva em JPEG."""
    if upload.size > settings.MAX_PHOTO_BYTES:
        raise BusinessError("A foto deve ter no máximo 8 MB.")
    try:
        img = Image.open(upload)
        img.verify()
        upload.seek(0)
        img = ImageOps.exif_transpose(Image.open(upload))
    except (UnidentifiedImageError, OSError, SyntaxError):
        raise BusinessError("Arquivo de imagem inválido. Envie JPG, PNG ou WEBP.")
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    img.thumbnail((MAX_SIDE, MAX_SIDE))
    out = io.BytesIO()
    img.save(out, format="JPEG", quality=82, optimize=True)
    return ContentFile(out.getvalue(), name="foto.jpg")


def add_photos(vehicle: Vehicle, files) -> list:
    from .models import VehiclePhoto

    if vehicle.photos.count() + len(files) > 40:
        raise BusinessError("Cada veículo pode ter até 40 fotos.")
    start = (vehicle.photos.order_by("-position").values_list("position", flat=True).first() or 0) + 1
    created = []
    for i, f in enumerate(files):
        photo = VehiclePhoto(organization=vehicle.organization, vehicle=vehicle, position=start + i)
        photo.image.save("foto.jpg", process_image(f), save=False)
        photo.save()
        created.append(photo)
    return created


# --- custos ----------------------------------------------------------------------------------


@transaction.atomic
def add_cost(vehicle: Vehicle, *, category, description, amount_cents, date, supplier=None, paid=False, user=None) -> VehicleCost:
    """Lança um custo no carro e, se a loja usa o financeiro, a conta a pagar correspondente."""
    if amount_cents <= 0:
        raise BusinessError("Informe um valor maior que zero.")
    cost = VehicleCost.objects.create(
        organization=vehicle.organization,
        vehicle=vehicle,
        category=category,
        description=description,
        amount_cents=amount_cents,
        date=date,
        supplier=supplier,
    )
    if has_feature(vehicle.organization, "financeiro"):
        from financeiro import service as fin

        lanc = fin.create(
            vehicle.organization,
            kind="pagar",
            origin="custo",
            description=f"{cost.get_category_display()}: {description} — {vehicle.title}",
            amount_cents=amount_cents,
            due_date=date,
            category_code="custo_veiculo",
            paid=paid,
            pessoa=supplier,
            vehicle=vehicle,
        )[0]
        cost.payable = lanc
        cost.save(update_fields=["payable"])
    record("estoque.custo", actor=user, organization=vehicle.organization, target=vehicle, amount_cents=amount_cents)
    return cost


def remove_cost(cost: VehicleCost) -> None:
    if cost.payable_id:
        if cost.payable.paid_at:
            raise BusinessError("Este custo já foi pago no financeiro. Estorne a baixa antes de remover.")
        cost.payable.delete()
    cost.delete()


# --- placa e FIPE ----------------------------------------------------------------------------


def plate_lookup(organization, placa: str, *, user=None) -> dict:
    """Consulta a placa. Repetir a mesma placa em 30 dias não conta; acima da franquia do plano, cobra da carteira."""
    from integrations.placa import PlacaClient

    since = timezone.now() - timedelta(days=PLATE_CACHE_DAYS)
    cached = PlateQuery.objects.filter(organization=organization, placa=placa, created_at__gte=since).order_by("-created_at").first()
    if cached:
        return {**cached.data, "cached": True}
    client = PlacaClient(organization)
    if not client.configured:
        raise BusinessError("Consulta de placa ainda não está disponível. Preencha os dados do veículo manualmente.", code="placa_off")

    month_start = timezone.localdate().replace(day=1)
    used = PlateQuery.objects.filter(organization=organization, created_at__date__gte=month_start).count()
    quota = limit(organization, "plate_queries") or 0
    price = 0 if used < quota else wallet.price_for(ServicePrice.Code.PLACA, organization)
    reservation = None
    if price:
        try:
            reservation = wallet.reserve(organization, price, f"Consulta de placa {placa}", ref_type="placa", ref_id=placa, user=user)
        except InsufficientBalance:
            raise InsufficientBalance("Sua franquia de consultas do mês acabou. Recarregue a carteira para continuar.")
    try:
        data = client.lookup(placa)
    except ProviderError as exc:
        if reservation:
            wallet.release(reservation, "consulta sem resultado")
        if exc.status_code == 404:
            raise BusinessError("Placa não encontrada na base. Preencha os dados manualmente.", code="placa_not_found")
        raise ProviderUnavailable("A consulta de placa não respondeu. Tente de novo ou preencha manualmente.")
    if reservation:
        wallet.capture(reservation)
    PlateQuery.objects.create(organization=organization, placa=placa, charged_cents=price, data=data)
    return {**data, "cached": False, "charged_cents": price}


def plate_usage(organization) -> dict:
    month_start = timezone.localdate().replace(day=1)
    return {
        "used": PlateQuery.objects.filter(organization=organization, created_at__date__gte=month_start).count(),
        "quota": limit(organization, "plate_queries") or 0,
        "price_cents": wallet.price_for(ServicePrice.Code.PLACA, organization),
    }


# --- compra a partir da avaliação ------------------------------------------------------------


@transaction.atomic
def buy_from_evaluation(av: Avaliacao, *, user=None, price_cents=None, purchase_date=None, paid=False, as_trade_in=False) -> Vehicle:
    """Transforma a avaliação aprovada em veículo do estoque (compra direta ou entrada na troca)."""
    av = Avaliacao.objects.select_for_update().get(pk=av.pk)
    if av.status == Avaliacao.Status.COMPRADA:
        raise BusinessError("Esta avaliação já virou veículo do estoque.")
    if av.status == Avaliacao.Status.RECUSADA:
        raise BusinessError("Avaliação recusada não pode ser comprada.")
    org = av.organization
    check_vehicle_limit(org)
    price = av.offer_cents if price_cents is None else price_cents
    day = purchase_date or timezone.localdate()
    vehicle = Vehicle.objects.create(
        organization=org,
        kind=av.kind,
        placa=av.placa,
        marca=av.marca,
        modelo=av.modelo,
        versao=av.versao,
        ano_fabricacao=av.ano_fabricacao,
        ano_modelo=av.ano_modelo,
        cor=av.cor,
        km=av.km,
        supplier=av.cliente,
        purchase_date=day,
        purchase_price_cents=price,
        entry_date=day,
        fipe_code=av.fipe_code,
        fipe_price_cents=av.fipe_price_cents,
        status=Vehicle.Status.PREPARACAO,
    )
    for photo in av.photos.all():
        from .models import VehiclePhoto

        copied = VehiclePhoto(organization=org, vehicle=vehicle, position=photo.pk)
        with photo.image.open("rb") as original:
            copied.image.save("avaliacao.jpg", ContentFile(original.read()), save=False)
        copied.save()
    av.status = Avaliacao.Status.COMPRADA
    av.vehicle = vehicle
    av.save(update_fields=["status", "vehicle", "updated_at"])
    # Na troca, o valor do carro abate da venda: não gera conta a pagar.
    if not as_trade_in and price > 0 and has_feature(org, "financeiro"):
        from financeiro import service as fin

        fin.create(
            org,
            kind="pagar",
            origin="compra",
            description=f"Compra de {vehicle.title}",
            amount_cents=price,
            due_date=day,
            category_code="compra_veiculo",
            paid=paid,
            pessoa=av.cliente,
            vehicle=vehicle,
        )
    record("estoque.compra", actor=user, organization=org, target=vehicle, amount_cents=price, trade_in=as_trade_in)
    return vehicle


# --- RENAVE ----------------------------------------------------------------------------------


def enter_renave(vehicle: Vehicle, *, user, data: dict):
    """Dá entrada no RENAVE com os dados do carro e liga o registro ao veículo comercial."""
    from renave import service as renave

    if vehicle.renave_id:
        raise BusinessError("Este veículo já está ligado a um registro do RENAVE.")
    stock = renave.entrada(organization=vehicle.organization, client_company=None, user=user, data=data)
    vehicle.renave = stock
    if not vehicle.renavam:
        vehicle.renavam = data["renavam"]
    vehicle.save(update_fields=["renave", "renavam", "updated_at"])
    return stock


def set_status(vehicle: Vehicle, status: str, *, user=None) -> Vehicle:
    allowed = {
        Vehicle.Status.PREPARACAO: {Vehicle.Status.DISPONIVEL, Vehicle.Status.DEVOLVIDO},
        Vehicle.Status.DISPONIVEL: {Vehicle.Status.PREPARACAO, Vehicle.Status.DEVOLVIDO},
        Vehicle.Status.RESERVADO: {Vehicle.Status.DISPONIVEL},
        Vehicle.Status.DEVOLVIDO: {Vehicle.Status.DISPONIVEL, Vehicle.Status.PREPARACAO},
    }
    if status == vehicle.status:
        return vehicle
    if status not in allowed.get(vehicle.status, set()):
        raise BusinessError("Mudança de situação não permitida. Vendas e reservas mudam a situação pela tela de vendas.")
    if status == Vehicle.Status.DEVOLVIDO and vehicle.ownership != Vehicle.Ownership.CONSIGNADO:
        raise BusinessError("Só veículos consignados podem ser devolvidos ao dono.")
    if vehicle.status == Vehicle.Status.DEVOLVIDO:
        check_vehicle_limit(vehicle.organization)
    vehicle.status = status
    vehicle.save(update_fields=["status", "updated_at"])
    record("estoque.situacao", actor=user, organization=vehicle.organization, target=vehicle, status=status)
    return vehicle
