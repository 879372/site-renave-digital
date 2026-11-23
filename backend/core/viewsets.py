"""Base para os cadastros da loja: escopo por empresa, permissão por papel e recurso do plano."""

from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from billing.permissions import PlanFeaturePermission
from organizations.tenancy import OrganizationPermission, resolve_membership


class OrgViewSet(viewsets.ModelViewSet):
    """ModelViewSet filtrado pela empresa ativa.

    Declare `required_feature` (recurso do plano) e `write_perm` (permissão para escrever).
    Leitura exige só vínculo com a empresa.
    """

    permission_classes = [IsAuthenticated, OrganizationPermission, PlanFeaturePermission]
    lookup_field = "public_id"
    lookup_value_regex = "[0-9a-f-]{36}"
    write_perm = "org.manage"
    http_method_names = ["get", "post", "patch", "delete"]

    @property
    def required_perms(self):
        write = self.write_perm
        perms = {"list": "view", "retrieve": "view", "create": write, "partial_update": write, "update": write, "destroy": write}
        perms.update(getattr(self, "extra_perms", {}))
        return perms

    def get_queryset(self):
        resolve_membership(self.request)
        return super().get_queryset().filter(organization=self.request.organization)

    def perform_create(self, serializer):
        serializer.save(organization=self.request.organization)

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx["organization"] = getattr(self.request, "organization", None)
        return ctx
