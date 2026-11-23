from rest_framework import permissions

from .entitlements import require_feature


class PlanFeaturePermission(permissions.BasePermission):
    """Exige que o plano da empresa inclua o recurso declarado na view.

    Use depois de `OrganizationPermission` (que resolve a empresa):
    `required_feature = "financeiro"` ou `required_features = {"create": "fiscal"}`.
    Leitura de dados já existentes continua liberada se a view não declarar a ação.
    """

    def has_permission(self, request, view):
        action = getattr(view, "action", None) or request.method.lower()
        feature = getattr(view, "required_features", {}).get(action) or getattr(view, "required_feature", None)
        if feature:
            require_feature(request.organization, feature)
        return True
