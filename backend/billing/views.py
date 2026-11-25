from rest_framework import mixins, permissions, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound
from rest_framework.response import Response
from rest_framework.views import APIView

from core.pagination import CreatedCursorPagination
from organizations.models import Membership
from organizations.tenancy import OrganizationPermission, resolve_membership
from wallet.service import get_wallet

from . import entitlements, service
from .models import Feature, Invoice, Plan
from .serializers import ChangePlanSerializer, InvoiceSerializer, PlanSerializer, SubscriptionSerializer


class PlanListView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        return Response(PlanSerializer(Plan.objects.filter(is_active=True), many=True).data)


class BillingMeView(APIView):
    """Plano, recursos liberados e limites da empresa ativa (o front usa para mostrar cadeados)."""

    permission_classes = [OrganizationPermission]
    required_perm = "view"

    def get(self, request):
        org = request.organization
        sub = entitlements.get_subscription(org)
        if sub is None:
            return Response({"applies": False, "features": list(Feature.values)})
        plan = entitlements.effective_plan(sub)
        wallet = get_wallet(org)
        open_invoice = org.invoices.filter(status__in=[Invoice.Status.OPEN, Invoice.Status.OVERDUE]).prefetch_related("items").first()
        return Response(
            {
                "applies": True,
                "subscription": SubscriptionSerializer(sub).data,
                "effective_plan": plan.code,
                "features": plan.features,
                "limits": {
                    "vehicles": plan.vehicle_limit,
                    "users": plan.user_limit,
                    "plate_queries": plan.plate_queries_included,
                },
                "usage": {"users": Membership.objects.filter(organization=org, is_active=True).count()},
                "postpaid": {
                    "credit_limit_cents": wallet.credit_limit_cents,
                    "owed_cents": max(-wallet.balance_cents, 0),
                },
                "open_invoice": InvoiceSerializer(open_invoice).data if open_invoice else None,
            }
        )


class ChangePlanView(APIView):
    permission_classes = [OrganizationPermission]
    required_perm = "billing.manage"

    def post(self, request):
        s = ChangePlanSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        invoice = service.change_plan(
            request.organization, s.validated_data["plan"], s.validated_data["cycle"], user=request.user, request=request
        )
        sub = entitlements.get_subscription(request.organization)
        body = {"subscription": SubscriptionSerializer(sub).data, "invoice": None}
        if invoice is not None:
            invoice.refresh_from_db()
            body["invoice"] = InvoiceSerializer(invoice).data
        return Response(body, status=status.HTTP_201_CREATED if invoice else status.HTTP_200_OK)


class InvoiceViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    serializer_class = InvoiceSerializer
    permission_classes = [OrganizationPermission]
    required_perms = {"list": "view", "retrieve": "view", "checkout": "billing.manage"}
    pagination_class = CreatedCursorPagination
    lookup_field = "public_id"
    lookup_value_regex = "[0-9a-f-]{36}"
    filterset_fields = ["status"]

    @action(detail=True, methods=["post"])
    def checkout(self, request, **kwargs):
        from core.exceptions import BusinessError, ProviderUnavailable
        from integrations.http import ProviderError

        from .gateway import enabled, push_invoice

        invoice = self.get_object()
        if invoice.status not in (Invoice.Status.OPEN, Invoice.Status.OVERDUE):
            raise BusinessError("Esta fatura não está aberta para pagamento.")
        if not enabled():
            raise ProviderUnavailable("O checkout ainda não foi configurado. Fale com o suporte.")
        try:
            invoice = push_invoice(invoice)
        except ProviderError as exc:
            raise ProviderUnavailable("Não foi possível abrir o checkout. Tente novamente.") from exc
        return Response(self.get_serializer(invoice).data)

    def get_queryset(self):
        resolve_membership(self.request)
        return Invoice.objects.filter(organization=self.request.organization).select_related("target_plan").prefetch_related("items")


class ConfirmCheckoutView(APIView):
    permission_classes = [OrganizationPermission]
    required_perm = "view"

    def post(self, request):
        from core.exceptions import ProviderUnavailable
        from integrations.http import ProviderError

        from .webhooks import confirm_checkout, find_checkout

        class InputSerializer(serializers.Serializer):
            order_nsu = serializers.CharField(max_length=80)
            transaction_nsu = serializers.CharField(max_length=120)
            slug = serializers.CharField(max_length=120)

        data = InputSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        values = data.validated_data
        checkout = find_checkout(values["order_nsu"])
        if checkout is None or checkout.organization.pk != request.organization.pk:
            raise NotFound("Pagamento não encontrado nesta loja. Selecione a loja que gerou a cobrança.")
        try:
            paid = confirm_checkout(values["order_nsu"], values["transaction_nsu"], values["slug"])
        except ProviderError as exc:
            raise ProviderUnavailable("Não foi possível confirmar agora. Tente novamente em instantes.") from exc
        checkout.refresh_from_db()
        obj = checkout.invoice if checkout.invoice_id else checkout.topup
        review = bool(checkout.paid_at and (obj.canceled_at if checkout.invoice_id else obj.status in ("canceled", "expired")))
        return Response({"paid": paid, "kind": "invoice" if checkout.invoice_id else "topup", "requires_review": review})
