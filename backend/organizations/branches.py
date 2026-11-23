"""Multi-loja (Premium): filiais ligadas à loja principal, que paga a assinatura de todas.

Cada filial é uma empresa (CNPJ próprio) com equipe, estoque e financeiro próprios.
O plano e os limites vêm da loja principal; cada filial ativa soma o valor de "loja extra"
na mensalidade. Veículos podem ser transferidos entre lojas do grupo.
"""

from django.db import transaction
from rest_framework import serializers, status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from audit.service import record
from billing.entitlements import require_feature
from core.documents import is_valid_cnpj, normalize_cnpj
from core.exceptions import BusinessError

from .models import Membership, Organization, Role
from .service import create_organization
from .tenancy import OrganizationPermission


def root_of(org: Organization) -> Organization:
    return org.parent or org


def group(org: Organization) -> list[Organization]:
    root = root_of(org)
    return [root, *root.branches.filter(is_active=True).order_by("legal_name")]


class BranchSerializer(serializers.Serializer):
    cnpj = serializers.CharField(max_length=18)
    legal_name = serializers.CharField(max_length=150)
    trade_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    uf = serializers.CharField(max_length=2)
    city = serializers.CharField(max_length=80)

    def validate_cnpj(self, value):
        value = normalize_cnpj(value)
        if not is_valid_cnpj(value):
            raise serializers.ValidationError("CNPJ inválido.")
        if Organization.objects.filter(cnpj=value).exists():
            raise serializers.ValidationError("Este CNPJ já está cadastrado.")
        return value


class BranchesView(APIView):
    permission_classes = [OrganizationPermission]
    required_perms = {"get": "view", "post": "org.manage"}

    def get(self, request):
        org = request.organization
        member_of = set(Membership.objects.filter(user=request.user, is_active=True).values_list("organization_id", flat=True))
        return Response(
            {
                "root_id": str(root_of(org).public_id),
                "stores": [
                    {
                        "id": str(o.public_id),
                        "name": str(o),
                        "cnpj": o.cnpj,
                        "is_root": o.parent_id is None,
                        "is_member": o.pk in member_of,
                        "vehicles": o.vehicles.filter(status__in=("preparacao", "disponivel", "reservado")).count(),
                    }
                    for o in group(org)
                ],
            }
        )

    def post(self, request):
        org = request.organization
        require_feature(org, "multiloja")
        root = root_of(org)
        if not Membership.objects.filter(user=request.user, organization=root, role=Role.OWNER, is_active=True).exists():
            raise PermissionDenied("Só o proprietário da loja principal pode abrir filiais.")
        s = BranchSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        with transaction.atomic():
            branch = create_organization(
                request.user,
                **{
                    **s.validated_data,
                    "uf": s.validated_data["uf"].upper(),
                    "kind": Organization.Kind.REVENDA,
                    "parent": root,
                    "email": root.email,
                },
            )
        from billing.entitlements import get_subscription
        from billing.service import sync_credit_limit

        sync_credit_limit(get_subscription(root))
        record("organization.branch_created", request=request, organization=root, target=branch)
        return Response({"id": str(branch.public_id), "name": str(branch)}, status=status.HTTP_201_CREATED)


class TransferVehicleView(APIView):
    """Move um veículo para outra loja do grupo (a saída/entrada no RENAVE entre filiais é feita à parte)."""

    permission_classes = [OrganizationPermission]
    required_perm = "estoque.manage"

    @transaction.atomic
    def post(self, request):
        from estoque.models import Vehicle, VehicleCost, VehicleDocument, VehiclePhoto

        org = request.organization
        require_feature(org, "multiloja")
        vehicle = Vehicle.objects.select_for_update().filter(organization=org, public_id=request.data.get("vehicle")).first()
        target = Organization.objects.filter(public_id=request.data.get("target")).first()
        if vehicle is None or target is None:
            raise ValidationError({"vehicle": "Veículo ou loja de destino não encontrados."})
        if target.pk == org.pk or root_of(target).pk != root_of(org).pk:
            raise ValidationError({"target": "Escolha outra loja do mesmo grupo."})
        if not Membership.objects.filter(user=request.user, organization=target, is_active=True).exists():
            raise PermissionDenied("Você não tem acesso à loja de destino.")
        if vehicle.status not in (Vehicle.Status.PREPARACAO, Vehicle.Status.DISPONIVEL):
            raise BusinessError("Só veículos em preparação ou disponíveis podem ser transferidos.")
        if vehicle.renave_id:
            raise BusinessError("Este veículo está no RENAVE desta loja. Faça a transferência entre filiais no RENAVE e desvincule antes.")
        if not target.is_active:
            raise BusinessError("A loja de destino está desativada.")
        costs = list(vehicle.costs.select_for_update(of=("self",)).select_related("payable"))
        if any(c.payable and not c.payable.paid_at and not c.payable.canceled for c in costs):
            raise BusinessError("Quite ou cancele as contas dos custos antes de transferir o veículo.")

        from pessoas.models import Pessoa

        def copy_person(person):
            if person is None:
                return None
            found = Pessoa.objects.filter(organization=target, documento=person.documento).first() if person.documento else None
            if found:
                return found
            data = {
                f.name: getattr(person, f.name)
                for f in Pessoa._meta.fields
                if f.name not in {"id", "public_id", "created_at", "updated_at", "organization"}
            }
            return Pessoa.objects.create(organization=target, **data)

        vehicle.organization = target
        vehicle.consignor = copy_person(vehicle.consignor)
        vehicle.supplier = copy_person(vehicle.supplier)
        # Obrigações e pagamentos são históricos da loja de origem, e não migram.
        # Os custos seguem como composição do valor do carro, sem controlar contas da outra empresa.
        vehicle.lancamentos.all().update(vehicle=None)
        for cost in costs:
            cost.supplier = copy_person(cost.supplier)
            cost.payable = None
            cost.save(update_fields=["supplier", "payable"])
        vehicle.save()
        for model in (VehiclePhoto, VehicleCost, VehicleDocument):
            model.objects.filter(vehicle=vehicle).update(organization=target)
        record("estoque.transferido", request=request, target=vehicle, destino=str(target.public_id))
        return Response({"ok": True})
