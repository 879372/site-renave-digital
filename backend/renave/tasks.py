from celery import shared_task

from integrations.http import ProviderError
from organizations.models import ClientCompany, Organization
from vault.models import Certificate

from . import service
from .models import StockVehicle


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def sync_certificate_to_carven(self, certificate_id: int):
    cert = Certificate.objects.select_related("organization").filter(pk=certificate_id, is_active=True).first()
    if cert is None:
        return
    try:
        service.sync_certificate(cert)
    except ProviderError as exc:
        raise self.retry(exc=exc)
    except Exception:
        return  # erro de negócio já gravado em carven_sync_error


@shared_task(bind=True, max_retries=6, default_retry_delay=30)
def resolve_stock_id(self, vehicle_id: int):
    vehicle = StockVehicle.objects.select_related("organization").filter(pk=vehicle_id).first()
    if vehicle is None or vehicle.id_estoque:
        return
    try:
        if service.resolve_id(vehicle):
            return
    except ProviderError:
        pass
    raise self.retry()


@shared_task
def sync_stock_task(organization_id: int, client_id: int | None = None):
    org = Organization.objects.get(pk=organization_id)
    client = ClientCompany.objects.filter(pk=client_id).first() if client_id else None
    return service.sync_stock(org, client)
