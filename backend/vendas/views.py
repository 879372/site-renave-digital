from datetime import date, timedelta

from django.db.models import Q
from django.utils import timezone
from rest_framework import serializers
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import User
from audit.service import record
from billing.entitlements import require_feature
from billing.permissions import PlanFeaturePermission
from billing.service import add_months
from core.exceptions import BusinessError
from core.fields import OrgRelatedField
from core.viewsets import OrgViewSet
from estoque.models import Avaliacao, Vehicle
from organizations.models import Membership
from organizations.tenancy import OrganizationPermission
from pessoas.models import Pessoa

from . import service
from .models import Meta, Pagamento, RegraComissao, Venda


class SellerField(serializers.SlugRelatedField):
    """Vendedor = membro ativo da loja."""

    def __init__(self, **kwargs):
        super().__init__(slug_field="public_id", **kwargs)

    def get_queryset(self):
        org = self.context.get("organization")
        return User.objects.filter(memberships__organization=org, memberships__is_active=True) if org else User.objects.none()

    def to_representation(self, obj):
        return str(obj.public_id)


class PagamentoSerializer(serializers.ModelSerializer):
    method_display = serializers.CharField(source="get_method_display", read_only=True)
    trade_in = OrgRelatedField(Avaliacao, required=False, allow_null=True)
    trade_in_title = serializers.SerializerMethodField()

    class Meta:
        model = Pagamento
        fields = ["method", "method_display", "amount_cents", "installments", "first_due", "bank", "trade_in", "trade_in_title"]

    def get_trade_in_title(self, obj):
        t = obj.trade_in
        return f"{t.marca} {t.modelo} {t.placa}".strip() if t else None

    def validate(self, attrs):
        if attrs["amount_cents"] <= 0:
            raise serializers.ValidationError({"amount_cents": "Valor deve ser maior que zero."})
        if attrs["method"] == Pagamento.Method.TROCA and not attrs.get("trade_in"):
            raise serializers.ValidationError({"trade_in": "Escolha a avaliação do carro da troca."})
        if attrs["method"] == Pagamento.Method.FINANCIAMENTO and not attrs.get("bank"):
            raise serializers.ValidationError({"bank": "Informe o banco do financiamento."})
        return attrs


class VendaSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="public_id", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    vehicle = OrgRelatedField(Vehicle)
    cliente = OrgRelatedField(Pessoa)
    seller = SellerField(required=False, allow_null=True)
    vehicle_title = serializers.CharField(source="vehicle.title", read_only=True)
    vehicle_placa = serializers.CharField(source="vehicle.placa", read_only=True)
    cliente_name = serializers.CharField(source="cliente.nome", read_only=True)
    seller_name = serializers.CharField(source="seller.full_name", read_only=True, default=None)
    pagamentos = PagamentoSerializer(many=True, read_only=True)
    paid_total_cents = serializers.SerializerMethodField()
    nota_id = serializers.UUIDField(source="nota.public_id", read_only=True, default=None)
    nota_status = serializers.CharField(source="nota.status", read_only=True, default=None)
    renave_state = serializers.CharField(source="vehicle.renave.state", read_only=True, default=None)
    has_renave = serializers.SerializerMethodField()
    garantia_ate = serializers.DateField(source="garantia.ends_on", read_only=True, default=None)

    class Meta:
        model = Venda
        fields = [
            "id",
            "status",
            "status_display",
            "vehicle",
            "vehicle_title",
            "vehicle_placa",
            "cliente",
            "cliente_name",
            "seller",
            "seller_name",
            "price_cents",
            "notes",
            "reserved_until",
            "closed_at",
            "cancel_reason",
            "cost_cents",
            "consignor_payout_cents",
            "profit_cents",
            "commission_cents",
            "commission_paid",
            "pagamentos",
            "paid_total_cents",
            "nota_id",
            "nota_status",
            "renave_state",
            "has_renave",
            "garantia_ate",
            "created_at",
        ]
        read_only_fields = [
            "status",
            "reserved_until",
            "closed_at",
            "cancel_reason",
            "cost_cents",
            "consignor_payout_cents",
            "profit_cents",
            "commission_cents",
            "commission_paid",
        ]

    def get_paid_total_cents(self, obj):
        return obj.paid_total()

    def get_has_renave(self, obj):
        return bool(obj.vehicle.renave_id)

    def validate(self, attrs):
        if self.instance and self.instance.status in (Venda.Status.FECHADA, Venda.Status.CANCELADA):
            raise serializers.ValidationError({"status": "Venda fechada ou cancelada não pode ser alterada."})
        vehicle = attrs.get("vehicle")
        if vehicle and vehicle.status not in (Vehicle.Status.DISPONIVEL, Vehicle.Status.PREPARACAO, Vehicle.Status.RESERVADO):
            raise serializers.ValidationError({"vehicle": "Este veículo não está disponível para venda."})
        if self.instance and "vehicle" in attrs and attrs["vehicle"] != self.instance.vehicle:
            raise serializers.ValidationError({"vehicle": "Para trocar o veículo, crie outra proposta."})
        price = attrs.get("price_cents")
        if price is not None and price <= 0:
            raise serializers.ValidationError({"price_cents": "Informe o valor da venda."})
        return attrs


class VendaViewSet(OrgViewSet):
    queryset = Venda.objects.select_related("vehicle__renave", "cliente", "seller", "nota", "garantia").prefetch_related(
        "pagamentos__trade_in"
    )
    serializer_class = VendaSerializer
    required_feature = "estoque"
    write_perm = "vendas.operate"
    extra_perms = {
        "payments": "vendas.operate",
        "reserve": "vendas.operate",
        "close": "vendas.operate",
        "cancel": "vendas.operate",
        "nfe": "fiscal.emit",
        "renave_saida": "renave.operate",
    }
    http_method_names = ["get", "post", "patch", "put"]

    def get_queryset(self):
        qs = super().get_queryset()
        p = self.request.query_params
        membership = self.request._membership
        if membership.role == "vendedor" and p.get("all") != "1":
            qs = qs.filter(seller=self.request.user)
        if st := p.get("status"):
            qs = qs.filter(status__in=st.split(","))
        if seller := p.get("seller"):
            qs = qs.filter(seller__public_id=seller)
        if month := p.get("month"):
            try:
                start = date.fromisoformat(month).replace(day=1)
            except ValueError:
                raise ValidationError({"month": "Mês inválido."})
            qs = qs.filter(closed_at__gte=start, closed_at__lt=add_months(start, 1))
        if term := p.get("search", "").strip():
            qs = qs.filter(Q(cliente__nome__icontains=term) | Q(vehicle__modelo__icontains=term) | Q(vehicle__placa__icontains=term))
        if v := p.get("vehicle"):
            qs = qs.filter(vehicle__public_id=v)
        return qs

    def perform_create(self, serializer):
        seller = serializer.validated_data.get("seller") or self.request.user
        venda = serializer.save(organization=self.request.organization, seller=seller)
        record("vendas.proposta", request=self.request, target=venda, price_cents=venda.price_cents)

    def _out(self, venda):
        return Response(self.get_serializer(self.get_queryset().get(pk=venda.pk)).data)

    @action(detail=True, methods=["put"])
    def payments(self, request, public_id=None):
        venda = self.get_object()
        s = PagamentoSerializer(data=request.data.get("items", []), many=True, context=self.get_serializer_context())
        s.is_valid(raise_exception=True)
        service.set_payments(venda, s.validated_data)
        return self._out(venda)

    @action(detail=True, methods=["post"])
    def reserve(self, request, public_id=None):
        venda = self.get_object()
        try:
            amount = int(request.data.get("amount_cents", 0))
            until = date.fromisoformat(request.data.get("until") or (timezone.localdate() + timedelta(days=3)).isoformat())
        except (TypeError, ValueError):
            raise ValidationError({"amount_cents": "Valor ou data inválidos."})
        service.reserve(venda, amount_cents=amount, until=until, user=request.user)
        return self._out(venda)

    @action(detail=True, methods=["post"])
    def close(self, request, public_id=None):
        venda = service.close(self.get_object(), user=request.user)
        return self._out(venda)

    @action(detail=True, methods=["post"])
    def cancel(self, request, public_id=None):
        venda = self.get_object()
        info = service.cancel(venda, reason=str(request.data.get("reason", "")), user=request.user)
        venda.refresh_from_db()
        return Response({**self.get_serializer(venda).data, **info})

    @action(detail=True, methods=["post"])
    def nfe(self, request, public_id=None):
        """Emite a NF-e de saída com os dados da venda (cliente, endereço e veículo)."""
        from fiscal import service as fiscal
        from fiscal.serializers import NotaCreateSerializer

        require_feature(request.organization, "fiscal")
        venda = self.get_object()
        if venda.status != Venda.Status.FECHADA:
            raise BusinessError("Feche a venda antes de emitir a nota.")
        if venda.nota_id and venda.nota.status not in ("rejected", "error", "canceled"):
            raise BusinessError("Esta venda já tem nota fiscal.")
        c, v = venda.cliente, venda.vehicle
        data = {
            "tipo": "1",
            "documento": c.documento,
            "nome": c.nome,
            "email": c.email,
            "telefone": c.telefone,
            "cep": c.cep,
            "logradouro": c.logradouro,
            "numero": c.numero,
            "complemento": c.complemento,
            "bairro": c.bairro,
            "cidade": c.cidade,
            "cidade_ibge": c.cidade_ibge,
            "uf": c.uf,
            "placa": v.placa,
            "chassi": v.chassi,
            "renavam": v.renavam,
            "marca_modelo": f"{v.marca} {v.modelo}"[:80],
            "ano_fabricacao": v.ano_fabricacao,
            "ano_modelo": v.ano_modelo,
            "cor": v.cor,
            "km": v.km or 0,
            "valor_cents": venda.price_cents,
            "observacoes": str(request.data.get("observacoes", ""))[:1000],
        }
        s = NotaCreateSerializer(data=data)
        if not s.is_valid():
            raise ValidationError({"missing": s.errors, "detail": "Complete o cadastro do cliente e do veículo para emitir a nota."})
        nota = fiscal.criar(organization=request.organization, user=request.user, data=s.validated_data, vehicle=v.renave)
        venda.nota = nota
        venda.save(update_fields=["nota", "updated_at"])
        return self._out(venda)

    @action(detail=True, methods=["post"], url_path="renave-saida")
    def renave_saida(self, request, public_id=None):
        """Dá saída no RENAVE com os dados da venda; a loja informa só o código de segurança do CRV."""
        from renave import service as renave
        from renave.serializers import SaidaSerializer

        venda = self.get_object()
        v, c = venda.vehicle, venda.cliente
        if venda.status != Venda.Status.FECHADA:
            raise BusinessError("Feche a venda antes de dar saída no RENAVE.")
        if not v.renave_id:
            raise BusinessError("Este veículo não está ligado a uma entrada no RENAVE.")
        if len(c.documento) != 11:
            raise BusinessError(
                "A saída para comprador CNPJ deve ser concluída com a integradora. Nenhuma transferência entre estabelecimentos foi enviada.",
                code="renave_cnpj_unsupported",
            )
        data = {
            "tipo_transferencia": 1,
            "data_venda": venda.closed_at.isoformat(),
            "cod_seguranca_crv": request.data.get("cod_seguranca_crv", ""),
            "comprador_nome": c.nome,
            "comprador_documento": c.documento,
            "valor_venda_cents": venda.price_cents,
            "municipio": c.cidade_ibge,
            "email": c.email,
            "cep": c.cep,
            "logradouro": c.logradouro,
            "numero": c.numero,
            "complemento": c.complemento,
            "bairro": c.bairro,
            "km": v.km or 0,
        }
        s = SaidaSerializer(data=data)
        if not s.is_valid():
            raise ValidationError({"missing": s.errors, "detail": "Complete os dados do comprador para dar saída."})
        renave.saida(vehicle=v.renave, user=request.user, data=s.validated_data)
        return self._out(venda)


# --- comissões e metas -------------------------------------------------------------------------


class RegraSerializer(serializers.ModelSerializer):
    class Meta:
        model = RegraComissao
        fields = ["mode", "value", "min_cents"]


class MetaSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(read_only=True)
    seller = SellerField()
    seller_name = serializers.CharField(source="seller.full_name", read_only=True)

    class Meta:
        model = Meta
        fields = ["id", "seller", "seller_name", "month", "units", "revenue_cents"]

    def validate_month(self, value):
        return value.replace(day=1)


class ComissaoView(APIView):
    permission_classes = [OrganizationPermission, PlanFeaturePermission]
    required_feature = "comissoes"
    required_perms = {"get": "view", "put": "financeiro.manage", "post": "financeiro.manage"}


def _month(request):
    raw = request.query_params.get("month") or request.data.get("month")
    try:
        start = date.fromisoformat(raw).replace(day=1) if raw else timezone.localdate().replace(day=1)
    except (TypeError, ValueError):
        raise ValidationError({"month": "Mês inválido (AAAA-MM-DD)."})
    return start, add_months(start, 1) - timedelta(days=1)


class RegraComissaoView(ComissaoView):
    def get(self, request):
        rule, _ = RegraComissao.objects.get_or_create(organization=request.organization)
        return Response(RegraSerializer(rule).data)

    def put(self, request):
        rule, _ = RegraComissao.objects.get_or_create(organization=request.organization)
        s = RegraSerializer(rule, data=request.data)
        s.is_valid(raise_exception=True)
        s.save()
        record("vendas.regra_comissao", request=request, **s.validated_data)
        return Response(s.data)


class ComissaoRelatorioView(ComissaoView):
    def get(self, request):
        start, end = _month(request)
        return Response({"month": start.isoformat(), "rows": service.commissions_report(request.organization, start, end)})

    def post(self, request):
        start, end = _month(request)
        n = service.pay_commissions(request.organization, start, end, user=request.user)
        return Response({"sellers": n})


class MetaViewSet(OrgViewSet):
    queryset = Meta.objects.select_related("seller")
    serializer_class = MetaSerializer
    required_feature = "comissoes"
    write_perm = "financeiro.manage"
    lookup_field = "pk"
    lookup_value_regex = r"\d+"
    pagination_class = None

    def get_queryset(self):
        qs = super().get_queryset()
        if m := self.request.query_params.get("month"):
            qs = qs.filter(month=date.fromisoformat(m).replace(day=1))
        return qs


class VendedoresView(APIView):
    """Membros ativos da loja, para escolher vendedor."""

    permission_classes = [OrganizationPermission]
    required_perm = "view"

    def get(self, request):
        ms = Membership.objects.filter(organization=request.organization, is_active=True).select_related("user").order_by("user__full_name")
        return Response([{"id": str(m.user.public_id), "name": m.user.full_name, "role": m.role} for m in ms])
