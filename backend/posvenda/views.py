from django.db import transaction
from django.utils import timezone
from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from billing.entitlements import has_feature
from core.fields import OrgRelatedField
from core.viewsets import OrgViewSet

from .models import Garantia, Ocorrencia


class GarantiaSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="public_id", read_only=True)
    venda_id = serializers.UUIDField(source="venda.public_id", read_only=True)
    vehicle_title = serializers.CharField(source="venda.vehicle.title", read_only=True)
    vehicle_placa = serializers.CharField(source="venda.vehicle.placa", read_only=True)
    cliente_name = serializers.CharField(source="venda.cliente.nome", read_only=True)
    cliente_phone = serializers.CharField(source="venda.cliente.telefone", read_only=True)
    is_active = serializers.BooleanField(read_only=True)
    open_issues = serializers.SerializerMethodField()

    class Meta:
        model = Garantia
        fields = [
            "id",
            "venda_id",
            "vehicle_title",
            "vehicle_placa",
            "cliente_name",
            "cliente_phone",
            "starts_on",
            "ends_on",
            "km_limit",
            "coverage",
            "is_active",
            "open_issues",
        ]
        read_only_fields = ["starts_on"]

    def get_open_issues(self, obj):
        return sum(1 for o in obj.ocorrencias.all() if o.status in ("aberta", "andamento"))

    def validate(self, attrs):
        ends = attrs.get("ends_on")
        if ends and self.instance and ends < self.instance.starts_on:
            raise serializers.ValidationError({"ends_on": "O fim da garantia não pode ser antes do início."})
        return attrs


class OcorrenciaSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="public_id", read_only=True)
    garantia = OrgRelatedField(Garantia)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    vehicle_title = serializers.CharField(source="garantia.venda.vehicle.title", read_only=True)
    cliente_name = serializers.CharField(source="garantia.venda.cliente.nome", read_only=True)

    class Meta:
        model = Ocorrencia
        fields = [
            "id",
            "garantia",
            "vehicle_title",
            "cliente_name",
            "description",
            "status",
            "status_display",
            "cost_cents",
            "resolution",
            "created_at",
        ]


class GarantiaViewSet(OrgViewSet):
    queryset = Garantia.objects.select_related("venda__vehicle", "venda__cliente").prefetch_related("ocorrencias")
    serializer_class = GarantiaSerializer
    required_feature = "posvenda"
    write_perm = "vendas.operate"
    http_method_names = ["get", "patch"]

    def get_queryset(self):
        qs = super().get_queryset()
        p = self.request.query_params
        if p.get("active") == "1":
            qs = qs.filter(ends_on__gte=timezone.localdate())
        if term := p.get("search", "").strip():
            qs = qs.filter(venda__cliente__nome__icontains=term) | qs.filter(venda__vehicle__placa__icontains=term)
        return qs


class OcorrenciaViewSet(OrgViewSet):
    queryset = Ocorrencia.objects.select_related("garantia__venda__vehicle", "garantia__venda__cliente", "lancamento")
    serializer_class = OcorrenciaSerializer
    required_feature = "posvenda"
    write_perm = "vendas.operate"

    def get_queryset(self):
        qs = super().get_queryset()
        if g := self.request.query_params.get("garantia"):
            qs = qs.filter(garantia__public_id=g)
        if st := self.request.query_params.get("status"):
            qs = qs.filter(status=st)
        return qs

    @transaction.atomic
    def _sync_cost(self, oc: Ocorrencia):
        """O custo da ocorrência vira (ou atualiza) uma conta a pagar de garantia."""
        if not has_feature(oc.organization, "financeiro"):
            return
        from financeiro import service as fin

        if oc.lancamento_id:
            lanc = oc.lancamento
            if lanc.paid_at:
                if lanc.amount_cents != oc.cost_cents:
                    raise ValidationError({"cost_cents": "O custo já foi pago no financeiro e não pode ser alterado."})
                return
            if oc.cost_cents <= 0:
                oc.lancamento = None
                oc.save(update_fields=["lancamento"])
                lanc.delete()
                return
            lanc.amount_cents = oc.cost_cents
            lanc.save(update_fields=["amount_cents", "updated_at"])
        elif oc.cost_cents > 0:
            v = oc.garantia.venda.vehicle
            oc.lancamento = fin.create(
                oc.organization,
                kind="pagar",
                origin="garantia",
                description=f"Garantia — {v.title}",
                amount_cents=oc.cost_cents,
                due_date=timezone.localdate(),
                category_code="garantia",
                vehicle=v,
            )[0]
            oc.save(update_fields=["lancamento"])

    @transaction.atomic
    def perform_create(self, serializer):
        oc = serializer.save(organization=self.request.organization)
        self._sync_cost(oc)

    @transaction.atomic
    def perform_update(self, serializer):
        oc = serializer.save()
        self._sync_cost(oc)
