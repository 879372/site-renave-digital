"""Resolução da empresa do contexto e permissões por papel.

O front envia `X-Organization: <public_id>`. Toda view de negócio herda de
`OrganizationScopedMixin`, que valida o vínculo e filtra os querysets.
"""

import uuid

from rest_framework import permissions
from rest_framework.exceptions import NotFound, PermissionDenied

from accounts.verification import EmailUnverified
from core.context import organization_id_var, user_id_var

from .models import Membership

HEADER = "HTTP_X_ORGANIZATION"


def resolve_membership(request) -> Membership:
    cached = getattr(request, "_membership", None)
    if cached is not None:
        return cached
    if not request.user.email_verified:
        raise EmailUnverified()
    raw = request.META.get(HEADER, "")
    try:
        org_id = uuid.UUID(raw)
    except ValueError:
        raise PermissionDenied("Selecione a empresa (cabeçalho X-Organization ausente ou inválido).")
    membership = (
        Membership.objects.select_related("organization")
        .filter(user=request.user, organization__public_id=org_id, is_active=True, organization__is_active=True)
        .first()
    )
    if membership is None:
        raise NotFound("Empresa não encontrada.")
    org = membership.organization
    if org.parent_id:
        from billing.entitlements import plan_for

        plan_for(org)  # Filiais só operam enquanto a principal mantém Multi-loja.
    if org.mfa_required and not request.user.totp_enabled:
        raise PermissionDenied("Esta empresa exige verificação em duas etapas. Ative o 2FA no seu perfil.")
    request._membership = membership
    request.organization = org
    organization_id_var.set(str(org.public_id))
    user_id_var.set(str(request.user.public_id))
    return membership


class OrganizationPermission(permissions.BasePermission):
    """Exige vínculo com a empresa e a permissão declarada na view.

    A view declara `required_perms = {"list": "view", "create": "consultas.run", ...}`
    ou `required_perm = "..."` para todas as ações. Padrão: leitura=view, escrita=org.manage.
    """

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        membership = resolve_membership(request)
        if membership.organization.is_demo and request.method not in permissions.SAFE_METHODS:
            module = view.__class__.__module__.split(".")[0]
            external = module in {"renave", "comunicacao", "consultas", "billing", "vault"}
            external |= module == "fiscal" and view.__class__.__name__ == "NotaViewSet"
            external |= module == "wallet" and getattr(view, "action", "") == "create"
            external |= module == "contratos" and getattr(view, "action", "") == "sign"
            if external:
                raise PermissionDenied(
                    "Loja demonstrativa: pagamentos, assinaturas e operações externas estão desativados. Os exemplos são locais e fictícios."
                )
        perm = self._required(request, view)
        if not membership.has_perm(perm):
            raise PermissionDenied("Seu perfil não tem permissão para esta ação.")
        return True

    def _required(self, request, view) -> str:
        action = getattr(view, "action", None) or request.method.lower()
        perms = getattr(view, "required_perms", {})
        if action in perms:
            return perms[action]
        if hasattr(view, "required_perm"):
            return view.required_perm
        return "view" if request.method in permissions.SAFE_METHODS else "org.manage"


class OrganizationScopedMixin:
    """Filtra o queryset pela empresa do contexto (campo `organization` por padrão)."""

    organization_field = "organization"
    permission_classes = [permissions.IsAuthenticated, OrganizationPermission]

    @property
    def organization(self):
        return self.request.organization

    @property
    def membership(self):
        return self.request._membership

    def get_queryset(self):
        qs = super().get_queryset()
        return qs.filter(**{self.organization_field: self.request.organization})
