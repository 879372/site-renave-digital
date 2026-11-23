from datetime import timedelta

from django.db import transaction
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound
from rest_framework.response import Response
from rest_framework.views import APIView

from audit.service import record
from billing.entitlements import has_feature
from billing.permissions import PlanFeaturePermission
from core.fields import OrgRelatedField
from core.viewsets import OrgViewSet
from estoque.models import Vehicle
from organizations.tenancy import OrganizationPermission
from pessoas.models import Pessoa
from vendas.models import Venda

from . import service
from .models import Ficha, Proposta


class PropostaSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="public_id", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = Proposta
        fields = [
            "id",
            "bank",
            "status",
            "status_display",
            "monthly_rate_bp",
            "term_months",
            "financed_cents",
            "installment_cents",
            "cet_annual_bp",
            "dealer_return_cents",
            "notes",
            "created_at",
            "updated_at",
        ]


class FichaSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="public_id", read_only=True)
    cliente = OrgRelatedField(Pessoa)
    cliente_name = serializers.CharField(source="cliente.nome", read_only=True)
    cliente_documento = serializers.CharField(source="cliente.documento", read_only=True)
    vehicle = OrgRelatedField(Vehicle, required=False, allow_null=True)
    vehicle_title = serializers.CharField(source="vehicle.title", read_only=True, default=None)
    venda = OrgRelatedField(Venda, required=False, allow_null=True)
    financed_cents = serializers.IntegerField(read_only=True)
    propostas = PropostaSerializer(many=True, read_only=True)
    best_status = serializers.SerializerMethodField()

    class Meta:
        model = Ficha
        fields = [
            "id",
            "cliente",
            "cliente_name",
            "cliente_documento",
            "vehicle",
            "vehicle_title",
            "venda",
            "mother_name",
            "marital_status",
            "occupation",
            "employer",
            "job_title",
            "employed_since",
            "monthly_income_cents",
            "reference_name",
            "reference_phone",
            "vehicle_price_cents",
            "down_payment_cents",
            "term_months",
            "financed_cents",
            "notes",
            "propostas",
            "best_status",
            "created_at",
        ]

    def get_best_status(self, obj):
        order = ["paga", "aprovada", "analise", "enviada", "recusada", "cancelada"]
        statuses = [p.status for p in obj.propostas.all()]
        return next((s for s in order if s in statuses), None)

    def validate(self, attrs):
        price = attrs.get("vehicle_price_cents", getattr(self.instance, "vehicle_price_cents", 0))
        down = attrs.get("down_payment_cents", getattr(self.instance, "down_payment_cents", 0))
        if down and price and down >= price:
            raise serializers.ValidationError({"down_payment_cents": "A entrada precisa ser menor que o valor do carro."})
        return attrs


class FichaViewSet(OrgViewSet):
    queryset = Ficha.objects.select_related("cliente", "vehicle").prefetch_related("propostas")
    serializer_class = FichaSerializer
    required_feature = "financiamento"
    write_perm = "vendas.operate"
    extra_perms = {"propostas": "vendas.operate", "proposta": "vendas.operate"}

    def get_queryset(self):
        qs = super().get_queryset()
        if term := self.request.query_params.get("search", "").strip():
            qs = qs.filter(cliente__nome__icontains=term)
        return qs

    def perform_create(self, serializer):
        ficha = serializer.save(organization=self.request.organization)
        record("financiamento.ficha", request=self.request, target=ficha)

    @action(detail=True, methods=["post"])
    def propostas(self, request, public_id=None):
        ficha = self.get_object()
        s = PropostaSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        p = s.save(organization=request.organization, ficha=ficha)
        return Response(PropostaSerializer(p).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["patch", "delete"], url_path=r"propostas/(?P<proposta_id>[0-9a-f-]{36})")
    @transaction.atomic
    def proposta(self, request, public_id=None, proposta_id=None):
        ficha = self.get_object()
        p = ficha.propostas.filter(public_id=proposta_id).first()
        if p is None:
            raise NotFound("Proposta não encontrada.")
        if request.method == "DELETE":
            p.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        s = PropostaSerializer(p, data=request.data, partial=True)
        s.is_valid(raise_exception=True)
        p = s.save()
        # Retorno da financeira vira conta a receber quando a proposta é paga.
        if (
            p.status == Proposta.Status.PAGA
            and p.dealer_return_cents > 0
            and not p.return_entry_id
            and has_feature(request.organization, "financeiro")
        ):
            from financeiro import service as fin

            p.return_entry = fin.create(
                request.organization,
                kind="receber",
                origin="manual",
                description=f"Retorno {p.bank} — {ficha.cliente.nome}",
                amount_cents=p.dealer_return_cents,
                due_date=timezone.localdate() + timedelta(days=30),
                category_code="retorno_financiamento",
                pessoa=None,
                vehicle=ficha.vehicle,
            )[0]
            p.save(update_fields=["return_entry"])
        record("financiamento.proposta", request=request, target=p, status=p.status)
        return Response(PropostaSerializer(p).data)


class SimularSerializer(serializers.Serializer):
    price_cents = serializers.IntegerField(min_value=1)
    down_cents = serializers.IntegerField(min_value=0, default=0)
    monthly_rate_bp = serializers.IntegerField(min_value=0, max_value=1500)
    months = serializers.IntegerField(min_value=1, max_value=96)
    fees_cents = serializers.IntegerField(min_value=0, default=0)
    iof_pct_bp = serializers.IntegerField(min_value=0, max_value=1000, default=0)


class SimularView(APIView):
    permission_classes = [OrganizationPermission, PlanFeaturePermission]
    required_perm = "view"
    required_feature = "financiamento"

    def post(self, request):
        s = SimularSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        terms = request.data.get("terms") or [s.validated_data["months"]]
        out = []
        for m in sorted({int(t) for t in terms if str(t).isdigit() and 1 <= int(t) <= 96})[:8]:
            out.append({"months": m, **service.simulate(**{**s.validated_data, "months": m})})
        return Response(out)
