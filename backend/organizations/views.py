import hashlib
import secrets
from datetime import timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.verification import mark_verified
from audit.service import record
from core import email as mailer
from core.documents import is_valid_cnpj, normalize_cnpj

from .models import ClientCompany, Invitation, Membership, Organization, Role
from .serializers import ClientCompanySerializer, InvitationSerializer, MemberSerializer, OrganizationSerializer
from .service import create_organization
from .tenancy import OrganizationPermission, resolve_membership


def check_seats(org, *, include_pending: bool) -> None:
    """Respeita o limite de usuários do plano (membros ativos + convites pendentes)."""
    from billing.entitlements import check_limit

    used = Membership.objects.filter(organization=org, is_active=True).count()
    if include_pending:
        used += Invitation.objects.filter(organization=org, accepted_at__isnull=True, expires_at__gt=timezone.now()).count()
    check_limit(org, "users", used, "usuários")


class CreateOrganizationSerializer(serializers.Serializer):
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
            raise serializers.ValidationError("Esta empresa já está cadastrada. Peça um convite ao responsável.")
        return value


class OrganizationCreateView(APIView):
    """O lojista cadastra outra empresa (outro CNPJ) na mesma conta."""

    def post(self, request):
        s = CreateOrganizationSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        if Membership.objects.filter(user=request.user, role=Role.OWNER).count() >= 20:
            raise PermissionDenied("Limite de empresas por conta atingido. Fale com o suporte.")
        data = {
            **s.validated_data,
            "kind": Organization.Kind.REVENDA,
            "uf": s.validated_data["uf"].upper(),
            "email": request.user.email,
            "phone": request.user.phone,
        }
        with transaction.atomic():
            org = create_organization(request.user, **data)
        record("organization.created", request=request, actor=request.user, organization=org, target=org)
        return Response({"id": str(org.public_id), "name": str(org)}, status=status.HTTP_201_CREATED)


class CurrentOrganizationView(APIView):
    permission_classes = [OrganizationPermission]
    required_perms = {"get": "view", "patch": "org.manage"}

    def get(self, request):
        return Response(OrganizationSerializer(request.organization).data)

    def patch(self, request):
        serializer = OrganizationSerializer(request.organization, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        record("organization.updated", request=request, target=request.organization, fields=list(request.data))
        return Response(serializer.data)


class MemberViewSet(mixins.ListModelMixin, mixins.UpdateModelMixin, mixins.DestroyModelMixin, viewsets.GenericViewSet):
    serializer_class = MemberSerializer
    permission_classes = [OrganizationPermission]
    required_perms = {"list": "view", "partial_update": "members.manage", "update": "members.manage", "destroy": "members.manage"}
    lookup_field = "public_id"
    lookup_value_regex = "[0-9a-f-]{36}"
    http_method_names = ["get", "patch", "delete"]

    def get_queryset(self):
        resolve_membership(self.request)
        return Membership.objects.filter(organization=self.request.organization).select_related("user").order_by("user__full_name")

    def perform_update(self, serializer):
        target = serializer.instance
        new_role = serializer.validated_data.get("role", target.role)
        if target.role == Role.OWNER or new_role == Role.OWNER:
            raise PermissionDenied("A titularidade só pode ser transferida pelo suporte.")
        if target.user_id == self.request.user.id:
            raise PermissionDenied("Você não pode alterar o próprio papel.")
        if not target.is_active and serializer.validated_data.get("is_active"):
            check_seats(self.request.organization, include_pending=True)
        serializer.save()
        record("member.updated", request=self.request, target=target, role=new_role, active=serializer.instance.is_active)

    def perform_destroy(self, instance):
        if instance.role == Role.OWNER:
            raise PermissionDenied("O proprietário não pode ser removido.")
        record("member.removed", request=self.request, target=instance)
        instance.delete()


class InvitationViewSet(mixins.ListModelMixin, mixins.CreateModelMixin, mixins.DestroyModelMixin, viewsets.GenericViewSet):
    serializer_class = InvitationSerializer
    permission_classes = [OrganizationPermission]
    required_perms = {"list": "members.manage", "create": "members.manage", "destroy": "members.manage"}
    lookup_field = "public_id"
    lookup_value_regex = "[0-9a-f-]{36}"

    def get_queryset(self):
        resolve_membership(self.request)
        return Invitation.objects.filter(organization=self.request.organization, accepted_at__isnull=True)

    def perform_create(self, serializer):
        email = serializer.validated_data["email"].lower()
        org = self.request.organization
        if Membership.objects.filter(organization=org, user__email=email).exists():
            raise ValidationError({"email": "Este usuário já faz parte da empresa."})
        check_seats(org, include_pending=True)
        token = secrets.token_urlsafe(32)
        invitation = serializer.save(
            organization=org,
            email=email,
            token_hash=hashlib.sha256(token.encode()).hexdigest(),
            expires_at=timezone.now() + timedelta(days=7),
            invited_by=self.request.user,
        )
        link = f"{settings.CORS_ALLOWED_ORIGINS[0]}/convite?token={token}"
        mailer.send(
            f"Convite para {org} — REVENDA DIGITAL",
            f"{self.request.user.full_name} convidou você para acessar {org} na REVENDA DIGITAL.\n\nAceite o convite em até 7 dias:\n{link}",
            [email],
        )
        record("member.invited", request=self.request, target=invitation, role=invitation.role)


class AcceptInvitationView(APIView):
    """O usuário autenticado aceita um convite enviado para o próprio e-mail."""

    allow_unverified_email = True  # o convite chegou na caixa de entrada: aceitar confirma o e-mail

    def post(self, request):
        token = str(request.data.get("token", ""))
        invitation = (
            Invitation.objects.select_related("organization")
            .filter(token_hash=hashlib.sha256(token.encode()).hexdigest(), accepted_at__isnull=True)
            .first()
        )
        if invitation is None or invitation.expires_at < timezone.now():
            raise NotFound("Convite inválido ou expirado.")
        if invitation.email != request.user.email:
            raise PermissionDenied("Este convite foi enviado para outro e-mail.")
        if not Membership.objects.filter(user=request.user, organization=invitation.organization).exists():
            check_seats(invitation.organization, include_pending=False)
        with transaction.atomic():
            try:
                Membership.objects.create(
                    user=request.user, organization=invitation.organization, role=invitation.role, invited_by=invitation.invited_by
                )
            except IntegrityError:
                pass
            invitation.accepted_at = timezone.now()
            invitation.save(update_fields=["accepted_at"])
            mark_verified(request.user)
        record("member.joined", request=request, organization=invitation.organization, target=invitation)
        return Response({"organization": str(invitation.organization.public_id)}, status=status.HTTP_201_CREATED)


class ClientCompanyViewSet(viewsets.ModelViewSet):
    serializer_class = ClientCompanySerializer
    permission_classes = [OrganizationPermission]
    required_perms = {
        "list": "view",
        "retrieve": "view",
        "create": "clients.manage",
        "update": "clients.manage",
        "partial_update": "clients.manage",
        "destroy": "clients.manage",
    }
    lookup_field = "public_id"
    lookup_value_regex = "[0-9a-f-]{36}"
    filterset_fields = ["is_active"]

    def get_queryset(self):
        resolve_membership(self.request)
        qs = ClientCompany.objects.filter(organization=self.request.organization)
        search = self.request.query_params.get("search")
        if search:
            qs = qs.filter(name__icontains=search) | qs.filter(document__startswith=search)
        return qs

    def perform_create(self, serializer):
        if ClientCompany.objects.filter(organization=self.request.organization, document=serializer.validated_data["document"]).exists():
            raise ValidationError({"document": "Cliente já cadastrado."})
        client = serializer.save(organization=self.request.organization)
        record("client.created", request=self.request, target=client)

    def perform_destroy(self, instance):
        instance.is_active = False
        instance.save(update_fields=["is_active"])
        record("client.deactivated", request=self.request, target=instance)

    @action(detail=False, methods=["get"])
    def choices(self, request):
        return Response(
            [{"id": str(c.public_id), "name": c.name, "document": c.document} for c in self.get_queryset().filter(is_active=True)]
        )
