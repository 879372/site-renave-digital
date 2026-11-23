from datetime import date, timedelta

from django.db import transaction
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from audit.service import record
from billing.permissions import PlanFeaturePermission
from core.fields import OrgRelatedField
from core.viewsets import OrgViewSet
from organizations.tenancy import OrganizationPermission
from pessoas.models import Pessoa

from . import ofx, service
from .models import Categoria, Conta, Lancamento


def _date(value, default):
    try:
        return date.fromisoformat(value) if value else default
    except ValueError:
        raise ValidationError({"date": "Data inválida (use AAAA-MM-DD)."})


class ContaSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="public_id", read_only=True)

    class Meta:
        model = Conta
        fields = ["id", "name", "kind", "bank", "opening_balance_cents", "is_active"]


class CategoriaSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="public_id", read_only=True)
    is_system = serializers.SerializerMethodField()

    class Meta:
        model = Categoria
        fields = ["id", "name", "kind", "is_system"]

    def get_is_system(self, obj):
        return bool(obj.system_code)


class LancamentoSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="public_id", read_only=True)
    status = serializers.CharField(read_only=True)
    categoria = OrgRelatedField(Categoria, required=False, allow_null=True)
    conta = OrgRelatedField(Conta, required=False, allow_null=True)
    pessoa = OrgRelatedField(Pessoa, required=False, allow_null=True)
    categoria_name = serializers.CharField(source="categoria.name", read_only=True, default=None)
    conta_name = serializers.CharField(source="conta.name", read_only=True, default=None)
    pessoa_name = serializers.CharField(source="pessoa.nome", read_only=True, default=None)
    vehicle_id = serializers.UUIDField(source="vehicle.public_id", read_only=True, default=None)
    vehicle_title = serializers.CharField(source="vehicle.title", read_only=True, default=None)
    origin_display = serializers.CharField(source="get_origin_display", read_only=True)
    installments = serializers.IntegerField(min_value=1, max_value=120, default=1)

    class Meta:
        model = Lancamento
        fields = [
            "id",
            "kind",
            "origin",
            "origin_display",
            "description",
            "categoria",
            "categoria_name",
            "pessoa",
            "pessoa_name",
            "vehicle_id",
            "vehicle_title",
            "amount_cents",
            "due_date",
            "installment",
            "installments",
            "paid_at",
            "paid_cents",
            "conta",
            "conta_name",
            "status",
            "notes",
            "created_at",
        ]
        read_only_fields = ["origin", "installment", "paid_at", "paid_cents"]

    def validate_amount_cents(self, value):
        if value <= 0:
            raise serializers.ValidationError("Informe um valor maior que zero.")
        return value


class ContaViewSet(OrgViewSet):
    queryset = Conta.objects.all()
    serializer_class = ContaSerializer
    required_feature = "financeiro"
    write_perm = "financeiro.manage"
    pagination_class = None

    def list(self, request, *args, **kwargs):
        return Response(service.account_balances(request.organization))

    def perform_destroy(self, instance):
        if instance.lancamentos.exists():
            raise ValidationError({"conta": "Esta conta tem lançamentos. Desative em vez de apagar."})
        instance.delete()


class CategoriaViewSet(OrgViewSet):
    queryset = Categoria.objects.all()
    serializer_class = CategoriaSerializer
    required_feature = "financeiro"
    write_perm = "financeiro.manage"
    pagination_class = None

    def get_queryset(self):
        service.ensure_setup(self.request.organization)
        return super().get_queryset()

    def perform_destroy(self, instance):
        if instance.system_code:
            raise ValidationError({"categoria": "Categorias do sistema não podem ser apagadas."})
        instance.delete()


class LancamentoViewSet(OrgViewSet):
    queryset = Lancamento.objects.select_related("categoria", "conta", "pessoa", "vehicle")
    serializer_class = LancamentoSerializer
    required_feature = "financeiro"
    write_perm = "financeiro.manage"
    extra_perms = {"pagar": "financeiro.manage", "estornar": "financeiro.manage", "cancelar": "financeiro.manage"}

    def get_queryset(self):
        qs = super().get_queryset()
        p = self.request.query_params
        today = timezone.localdate()
        if kind := p.get("kind"):
            qs = qs.filter(kind=kind)
        st = p.get("status")
        if st == "aberto":
            qs = qs.filter(paid_at__isnull=True, canceled=False, due_date__gte=today)
        elif st == "vencido":
            qs = qs.filter(paid_at__isnull=True, canceled=False, due_date__lt=today)
        elif st == "pendente":
            qs = qs.filter(paid_at__isnull=True, canceled=False)
        elif st == "pago":
            qs = qs.filter(paid_at__isnull=False)
        elif st == "cancelado":
            qs = qs.filter(canceled=True)
        if d := p.get("date_from"):
            qs = qs.filter(due_date__gte=_date(d, None))
        if d := p.get("date_to"):
            qs = qs.filter(due_date__lte=_date(d, None))
        if term := p.get("search", "").strip():
            qs = service.search(qs, term)
        if v := p.get("vehicle"):
            qs = qs.filter(vehicle__public_id=v)
        return qs

    def create(self, request, *args, **kwargs):
        s = self.get_serializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        items = service.create(
            request.organization,
            kind=d["kind"],
            description=d["description"],
            amount_cents=d["amount_cents"],
            due_date=d["due_date"],
            installments=d.get("installments", 1),
            categoria=d.get("categoria"),
            pessoa=d.get("pessoa"),
            conta=d.get("conta"),
            notes=d.get("notes", ""),
        )
        record("financeiro.lancamento_criado", request=request, target=items[0], amount_cents=d["amount_cents"])
        return Response(self.get_serializer(items, many=True).data, status=status.HTTP_201_CREATED)

    def perform_update(self, serializer):
        if serializer.instance.origin != Lancamento.Origin.MANUAL and {"amount_cents", "kind"} & set(serializer.validated_data):
            raise ValidationError({"amount_cents": "Lançamentos automáticos só podem ter descrição, vencimento e conta alterados."})
        serializer.validated_data.pop("installments", None)
        serializer.save()

    def perform_destroy(self, instance):
        if instance.origin != Lancamento.Origin.MANUAL or instance.paid_at:
            raise ValidationError({"lancamento": "Cancele em vez de apagar (lançamento automático ou já pago)."})
        instance.delete()

    @action(detail=True, methods=["post"])
    def pagar(self, request, public_id=None):
        lanc = self.get_object()
        conta = None
        if cid := request.data.get("conta"):
            conta = Conta.objects.filter(organization=request.organization, public_id=cid).first()
            if conta is None:
                raise ValidationError({"conta": "Conta não encontrada."})
        paid_cents = request.data.get("paid_cents")
        lanc = service.pay(
            lanc,
            paid_at=_date(request.data.get("paid_at"), timezone.localdate()),
            paid_cents=int(paid_cents) if paid_cents not in (None, "") else None,
            conta=conta,
        )
        record("financeiro.baixa", request=request, target=lanc, amount_cents=lanc.paid_cents)
        return Response(self.get_serializer(lanc).data)

    @action(detail=True, methods=["post"])
    def estornar(self, request, public_id=None):
        lanc = service.unpay(self.get_object())
        record("financeiro.estorno", request=request, target=lanc)
        return Response(self.get_serializer(lanc).data)

    @action(detail=True, methods=["post"])
    def cancelar(self, request, public_id=None):
        lanc = self.get_object()
        if lanc.paid_at:
            raise ValidationError({"lancamento": "Estorne a baixa antes de cancelar."})
        lanc.canceled = True
        lanc.save(update_fields=["canceled", "updated_at"])
        record("financeiro.cancelado", request=request, target=lanc)
        return Response(self.get_serializer(lanc).data)


class FinanceView(APIView):
    permission_classes = [OrganizationPermission, PlanFeaturePermission]
    required_perm = "view"
    required_feature = "financeiro"


class ResumoView(FinanceView):
    def get(self, request):
        return Response(service.summary(request.organization))


class FluxoView(FinanceView):
    def get(self, request):
        today = timezone.localdate()
        start = _date(request.query_params.get("date_from"), today - timedelta(days=15))
        end = _date(request.query_params.get("date_to"), today + timedelta(days=30))
        if (end - start).days > 400:
            raise ValidationError({"date_to": "Período máximo de 400 dias."})
        return Response(service.cash_flow(request.organization, start, end))


class DreView(FinanceView):
    def get(self, request):
        month = _date(request.query_params.get("month"), timezone.localdate())
        return Response(service.dre(request.organization, month))


class ConciliacaoView(FinanceView):
    """Envia um OFX: devolve as transações com sugestão de lançamento. POST com `confirm` dá baixa nos pares escolhidos."""

    required_perm = "financeiro.manage"
    required_feature = "conciliacao"

    def post(self, request):
        if request.data.get("confirm"):
            return self._confirm(request)
        upload = request.FILES.get("file")
        if upload is None:
            raise ValidationError({"file": "Envie o arquivo OFX do extrato."})
        if upload.size > 5 * 1024 * 1024:
            raise ValidationError({"file": "Arquivo maior que 5 MB."})
        txs = ofx.parse(upload.read())
        return Response(service.reconcile(request.organization, txs))

    @transaction.atomic
    def _confirm(self, request):
        pairs = request.data.get("pairs") or []
        conta = Conta.objects.filter(organization=request.organization, public_id=request.data.get("conta")).first()
        done = 0
        for pair in pairs[:500]:
            lanc = Lancamento.objects.filter(organization=request.organization, public_id=pair.get("lancamento")).first()
            if lanc is None or lanc.paid_at:
                continue
            service.pay(lanc, paid_at=_date(pair.get("date"), timezone.localdate()), conta=conta)
            lanc.bank_ref = str(pair.get("fitid", ""))[:80]
            lanc.save(update_fields=["bank_ref"])
            done += 1
        record("financeiro.conciliacao", request=request, count=done)
        return Response({"reconciled": done})
