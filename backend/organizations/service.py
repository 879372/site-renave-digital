from integrations import lookups

from .models import Membership, Organization, Role

ADDRESS_FIELDS = ("zip_code", "street", "number", "complement", "district", "city_ibge")


def create_organization(user, **data) -> Organization:
    """Cria a empresa com o usuário como proprietário e completa o endereço pelos dados públicos do CNPJ."""
    info = lookups.company(data["cnpj"]) or {}
    for field in ADDRESS_FIELDS:
        data.setdefault(field, info.get(field, ""))
    if info.get("city") and info.get("uf") == data.get("uf"):
        data.setdefault("city", info["city"])
    org = Organization.objects.create(**data)
    Membership.objects.create(user=user, organization=org, role=Role.OWNER)
    from billing.service import on_organization_created

    on_organization_created(org)
    return org
