"""Backoffice de assinaturas: planos, assinaturas e faturas (rotas em /api/admin/)."""

from rest_framework import mixins, serializers, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from audit.service import record
from backoffice.views import AdminMixin

from . import service
from .models import Invoice, Plan, Subscription
from .serializers import InvoiceSerializer, PlanSerializer, SubscriptionSerializer


class PlanAdminSerializer(PlanSerializer):
    class Meta(PlanSerializer.Meta):
        fields = [*PlanSerializer.Meta.fields, "id", "credit_limit_cents", "is_active", "sort_order"]
        read_only_fields = ["code", "id"]


class SubscriptionAdminSerializer(SubscriptionSerializer):
    id = serializers.UUIDField(source="public_id", read_only=True)
    organization_id = serializers.UUIDField(source="organization.public_id", read_only=True)
    organization_name = serializers.CharField(source="organization.__str__", read_only=True)
    organization_cnpj = serializers.CharField(source="organization.cnpj", read_only=True)

    class Meta(SubscriptionSerializer.Meta):
        fields = ["id", "organization_id", "organization_name", "organization_cnpj", *SubscriptionSerializer.Meta.fields, "created_at"]


class InvoiceAdminSerializer(InvoiceSerializer):
    organization_id = serializers.UUIDField(source="organization.public_id", read_only=True)
    organization_name = serializers.CharField(source="organization.__str__", read_only=True)
    organization_cnpj = serializers.CharField(source="organization.cnpj", read_only=True)

    class Meta(InvoiceSerializer.Meta):
        fields = [
            *InvoiceSerializer.Meta.fields,
            "organization_id",
            "organization_name",
            "organization_cnpj",
            "provider",
            "provider_payment_id",
        ]


class PlanAdminViewSet(mixins.ListModelMixin, mixins.UpdateModelMixin, viewsets.GenericViewSet):
    queryset = Plan.objects.all()
    serializer_class = PlanAdminSerializer
    permission_classes = AdminMixin.permission_classes
    pagination_class = None
    lookup_field = "code"
    http_method_names = ["get", "patch"]

    def perform_update(self, serializer):
        plan = serializer.save()
        record("admin.plan_updated", request=self.request, target=plan, fields=list(self.request.data))


class SubscriptionAdminViewSet(AdminMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    queryset = Subscription.objects.select_related("organization", "plan", "scheduled_plan")
    serializer_class = SubscriptionAdminSerializer
    search_fields = ("organization__legal_name", "organization__trade_name", "organization__cnpj")

    def get_queryset(self):
        qs = super().get_queryset()
        p = self.request.query_params
        if st := p.get("status"):
            qs = qs.filter(status=st)
        if plan := p.get("plan"):
            qs = qs.filter(plan__code=plan)
        return qs.order_by("-created_at")

    @action(detail=True, methods=["post"], url_path="extend-trial")
    def extend_trial(self, request, public_id=None):
        try:
            days = int(request.data.get("days", 0))
        except (TypeError, ValueError):
            raise ValidationError({"days": "Informe um número de dias."})
        sub = service.extend_trial(self.get_object(), days, user=request.user, request=request)
        return Response(self.get_serializer(sub).data)

    @action(detail=True, methods=["post"], url_path="grant-plan")
    def grant_plan(self, request, public_id=None):
        plan = Plan.objects.filter(code=request.data.get("plan")).first()
        cycle = request.data.get("cycle", Subscription.Cycle.MONTHLY)
        reason = str(request.data.get("reason", "")).strip()
        if plan is None:
            raise ValidationError({"plan": "Plano inválido."})
        if cycle not in Subscription.Cycle.values:
            raise ValidationError({"cycle": "Ciclo inválido."})
        if len(reason) < 5:
            raise ValidationError({"reason": "Descreva o motivo."})
        sub = service.grant_plan(self.get_object(), plan, cycle, user=request.user, request=request)
        record("admin.plan_granted_reason", request=request, organization=sub.organization, target=sub, reason=reason)
        return Response(self.get_serializer(sub).data)


class InvoiceAdminViewSet(AdminMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    queryset = Invoice.objects.select_related("organization", "target_plan").prefetch_related("items")
    serializer_class = InvoiceAdminSerializer
    search_fields = ("organization__legal_name", "organization__cnpj", "provider_payment_id")

    def get_queryset(self):
        qs = super().get_queryset()
        if st := self.request.query_params.get("status"):
            qs = qs.filter(status=st)
        return qs.order_by("-created_at")

    @action(detail=True, methods=["post"], url_path="mark-paid")
    def mark_paid(self, request, public_id=None):
        invoice = self.get_object()
        if invoice.status == Invoice.Status.CANCELED:
            raise ValidationError({"status": "Fatura cancelada não pode ser marcada como paga."})
        invoice = service.mark_paid(invoice, user=request.user, request=request)
        return Response(self.get_serializer(invoice).data)

    @action(detail=True, methods=["post"])
    def cancel(self, request, public_id=None):
        invoice = service.cancel_invoice(self.get_object(), user=request.user, request=request)
        return Response(self.get_serializer(invoice).data)
