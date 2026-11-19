"""API do painel administrativo (/api/admin/*). Toda alteração gera evento de auditoria."""

from datetime import timedelta

from django.conf import settings
from django.contrib.auth import password_validation
from django.contrib.auth.tokens import default_token_generator
from django.db.models import Count, Q, Sum
from django.utils import timezone
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from accounts.models import User
from audit.models import AuditEvent
from audit.service import record
from comunicacao.models import ComunicacaoVenda
from consultas.models import Consulta, Product
from core import email as mailer
from core.documents import only_digits
from core.pagination import DefaultPagination
from fiscal.models import NotaFiscal
from integrations.models import IntegrationCall, WebhookDelivery
from organizations.models import Membership, Organization
from renave.models import RenaveOperation, StockVehicle
from vault.models import Certificate
from wallet import service as wallet
from wallet.models import DEFAULT_PRICES, LedgerEntry, ServicePrice, TopUp

from . import serializers as s
from .auth import IsAdminSession, IsSuperAdmin


class AdminPagination(DefaultPagination):
    page_size = 25
    max_page_size = 200


class AdminMixin:
    """Filtros comuns: ?search, ?organization=<uuid>, ?date_from, ?date_to (AAAA-MM-DD)."""

    permission_classes = [IsAdminSession]
    pagination_class = AdminPagination
    lookup_field = "public_id"
    lookup_value_regex = "[0-9a-f-]{36}"
    search_fields: tuple[str, ...] = ()
    date_field = "created_at"
    org_field = "organization"

    def filter_common(self, qs):
        p = self.request.query_params
        if (term := p.get("search", "").strip()) and self.search_fields:
            cond = Q()
            digits = only_digits(term)
            for field in self.search_fields:
                cond |= Q(**{f"{field}__icontains": term})
                if digits and digits != term:
                    cond |= Q(**{f"{field}__icontains": digits})
            qs = qs.filter(cond)
        if (org := p.get("organization")) and self.org_field:
            qs = qs.filter(**{f"{self.org_field}__public_id": org})
        if d := p.get("date_from"):
            qs = qs.filter(**{f"{self.date_field}__date__gte": d})
        if d := p.get("date_to"):
            qs = qs.filter(**{f"{self.date_field}__date__lte": d})
        return qs

    def get_queryset(self):
        return self.filter_common(super().get_queryset())


# --- Métricas -----------------------------------------------------------------------


class StatsViewSet(viewsets.ViewSet):
    permission_classes = [IsAdminSession]

    def list(self, request):
        from django.db.models.functions import TruncDate

        days = min(max(int(request.query_params.get("days", 30)), 7), 365)
        now = timezone.now()
        since = now - timedelta(days=days)
        today = timezone.localdate()

        consultas = Consulta.objects.filter(created_at__gte=since)
        agg = consultas.aggregate(
            total=Count("id"),
            success=Count("id", filter=Q(status=Consulta.Status.SUCCESS)),
            failed=Count("id", filter=Q(status=Consulta.Status.FAILED)),
            revenue=Sum("charged_cents"),
            cost=Sum("provider_cost_cents"),
        )
        renave_rev = RenaveOperation.objects.filter(created_at__gte=since, success=True).aggregate(v=Sum("price_cents"))["v"] or 0
        nfe_rev = (
            NotaFiscal.objects.filter(created_at__gte=since, status=NotaFiscal.Status.AUTHORIZED).aggregate(v=Sum("price_cents"))["v"] or 0
        )
        cv_rev = (
            ComunicacaoVenda.objects.filter(created_at__gte=since, transmitted_at__isnull=False).aggregate(v=Sum("price_cents"))["v"] or 0
        )
        topups = TopUp.objects.filter(paid_at__gte=since).aggregate(v=Sum("amount_cents"), n=Count("id"))

        daily = {
            row["day"]: row
            for row in consultas.annotate(day=TruncDate("created_at", tzinfo=timezone.get_current_timezone()))
            .values("day")
            .annotate(consultas=Count("id"), revenue=Sum("charged_cents"), cost=Sum("provider_cost_cents"))
        }
        signups = {
            row["day"]: row["n"]
            for row in Organization.objects.filter(created_at__gte=since)
            .annotate(day=TruncDate("created_at", tzinfo=timezone.get_current_timezone()))
            .values("day")
            .annotate(n=Count("id"))
        }
        series = []
        for i in range(days, -1, -1):
            day = today - timedelta(days=i)
            row = daily.get(day, {})
            series.append(
                {
                    "date": day.isoformat(),
                    "consultas": row.get("consultas", 0),
                    "revenue_cents": row.get("revenue") or 0,
                    "cost_cents": row.get("cost") or 0,
                    "new_organizations": signups.get(day, 0),
                }
            )

        day_ago = now - timedelta(hours=24)
        providers = []
        for code, label in IntegrationCall.Provider.choices:
            calls = IntegrationCall.objects.filter(provider=code, created_at__gte=day_ago)
            a = calls.aggregate(total=Count("id"), ok=Count("id", filter=Q(success=True)), avg=Sum("duration_ms"))
            total = a["total"] or 0
            providers.append(
                {
                    "provider": code,
                    "label": label,
                    "calls_24h": total,
                    "success_rate": round((a["ok"] or 0) * 100 / total, 1) if total else None,
                    "avg_ms": int((a["avg"] or 0) / total) if total else None,
                    "last_error": calls.filter(success=False).values_list("error", flat=True).first(),
                }
            )

        top_products = list(
            consultas.filter(charged_cents__gt=0)
            .values("product__name")
            .annotate(n=Count("id"), revenue=Sum("charged_cents"), cost=Sum("provider_cost_cents"))
            .order_by("-revenue")[:8]
        )

        return Response(
            {
                "period_days": days,
                "organizations": {
                    "total": Organization.objects.count(),
                    "active": Organization.objects.filter(is_active=True).count(),
                    "new": Organization.objects.filter(created_at__gte=since).count(),
                },
                "users": {
                    "total": User.objects.filter(anonymized_at__isnull=True).count(),
                    "new": User.objects.filter(date_joined__gte=since).count(),
                },
                "consultas": {
                    **agg,
                    "revenue": agg["revenue"] or 0,
                    "cost": agg["cost"] or 0,
                    "today": Consulta.objects.filter(created_at__date=today).count(),
                },
                "revenue": {
                    "consultas": agg["revenue"] or 0,
                    "renave": renave_rev,
                    "nfe": nfe_rev,
                    "comunicacao": cv_rev,
                    "total": (agg["revenue"] or 0) + renave_rev + nfe_rev + cv_rev,
                },
                "topups": {
                    "paid_cents": topups["v"] or 0,
                    "paid_count": topups["n"] or 0,
                    "pending_count": TopUp.objects.filter(status=TopUp.Status.PENDING).count(),
                    "pending_cents": TopUp.objects.filter(status=TopUp.Status.PENDING).aggregate(v=Sum("amount_cents"))["v"] or 0,
                },
                "wallets_balance_cents": Organization.objects.aggregate(v=Sum("wallet__balance_cents"))["v"] or 0,
                "renave": {
                    "in_stock": StockVehicle.objects.filter(state=StockVehicle.State.CONFIRMADO).count(),
                    "operations": RenaveOperation.objects.filter(created_at__gte=since).count(),
                    "failed": RenaveOperation.objects.filter(created_at__gte=since, success=False).count(),
                },
                "nfe": {
                    "authorized": NotaFiscal.objects.filter(created_at__gte=since, status=NotaFiscal.Status.AUTHORIZED).count(),
                    "rejected": NotaFiscal.objects.filter(created_at__gte=since, status=NotaFiscal.Status.REJECTED).count(),
                },
                "certificates_expiring": Certificate.objects.filter(is_active=True, not_after__lte=now + timedelta(days=30)).count(),
                "series": series,
                "providers": providers,
                "top_products": top_products,
            }
        )


# --- Empresas -----------------------------------------------------------------------


class OrganizationAdminViewSet(
    AdminMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.UpdateModelMixin, viewsets.GenericViewSet
):
    queryset = Organization.objects.all()
    search_fields = ("legal_name", "trade_name", "cnpj", "city")
    org_field = ""
    http_method_names = ["get", "patch", "post"]

    def get_queryset(self):
        qs = (
            super()
            .get_queryset()
            .select_related("wallet")
            .prefetch_related("memberships__user")
            .annotate(members_count=Count("memberships", filter=Q(memberships__is_active=True), distinct=True))
        )
        p = self.request.query_params
        if p.get("is_active") in ("true", "false"):
            qs = qs.filter(is_active=p["is_active"] == "true")
        if kind := p.get("kind"):
            qs = qs.filter(kind=kind)
        if uf := p.get("uf"):
            qs = qs.filter(uf=uf.upper())
        return qs.order_by("-created_at")

    def get_serializer_class(self):
        return s.OrganizationListSerializer if self.action == "list" else s.OrganizationDetailSerializer

    def retrieve(self, request, *args, **kwargs):
        org = self.get_object()
        since = timezone.now() - timedelta(days=30)
        data = s.OrganizationDetailSerializer(org).data
        data["balance_cents"] = wallet.get_wallet(org).balance_cents
        data["members"] = s.MemberAdminSerializer(org.memberships.select_related("user", "organization"), many=True).data
        data["certificates"] = s.CertificateAdminSerializer(
            org.certificates.filter(is_active=True).select_related("client", "organization"), many=True
        ).data
        data["counts"] = {
            "consultas_30d": org.consultas.filter(created_at__gte=since).count(),
            "spent_30d": org.consultas.filter(created_at__gte=since).aggregate(v=Sum("charged_cents"))["v"] or 0,
            "stock": org.stock.filter(state=StockVehicle.State.CONFIRMADO).count(),
            "notas": org.notas.count(),
            "clients": org.clients.filter(is_active=True).count(),
        }
        return Response(data)

    def perform_update(self, serializer):
        org = serializer.save()
        record("admin.organization_updated", request=self.request, organization=org, target=org, fields=list(self.request.data))

    @action(detail=True, methods=["post"], url_path="wallet-adjust")
    def wallet_adjust(self, request, public_id=None):
        org = self.get_object()
        try:
            amount = int(request.data.get("amount_cents", 0))
        except (TypeError, ValueError):
            raise ValidationError({"amount_cents": "Valor inválido."})
        reason = str(request.data.get("reason", "")).strip()
        if amount == 0:
            raise ValidationError({"amount_cents": "Informe um valor diferente de zero."})
        if len(reason) < 5:
            raise ValidationError({"reason": "Descreva o motivo do ajuste."})
        entry = wallet.adjust(org, amount, f"Ajuste administrativo: {reason}", user=request.user)
        record("admin.wallet_adjusted", request=request, organization=org, target=org, amount_cents=amount, reason=reason)
        return Response(s.LedgerAdminSerializer(entry).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["get"])
    def ledger(self, request, public_id=None):
        org = self.get_object()
        qs = LedgerEntry.objects.filter(wallet__organization=org).select_related("created_by")
        page = self.paginate_queryset(qs)
        return self.get_paginated_response(s.LedgerAdminSerializer(page, many=True).data)


# --- Usuários e equipe --------------------------------------------------------------


class UserAdminViewSet(AdminMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.UpdateModelMixin, viewsets.GenericViewSet):
    queryset = User.objects.all()
    serializer_class = s.UserAdminSerializer
    search_fields = ("email", "full_name", "cpf", "phone")
    org_field = "memberships__organization"
    date_field = "date_joined"
    http_method_names = ["get", "patch", "post"]

    def get_queryset(self):
        qs = super().get_queryset().annotate(organizations_count=Count("memberships", distinct=True))
        p = self.request.query_params
        if p.get("staff") == "true":
            qs = qs.filter(is_staff=True)
        if p.get("is_active") in ("true", "false"):
            qs = qs.filter(is_active=p["is_active"] == "true")
        return qs.order_by("-date_joined")

    def retrieve(self, request, *args, **kwargs):
        user = self.get_object()
        data = s.UserAdminSerializer(user).data
        data["memberships"] = s.MemberAdminSerializer(user.memberships.select_related("organization", "user"), many=True).data
        data["recent_activity"] = s.AuditAdminSerializer(
            AuditEvent.objects.filter(actor=user).select_related("organization", "actor")[:20], many=True
        ).data
        return Response(data)

    def perform_update(self, serializer):
        target = serializer.instance
        if "is_active" in serializer.validated_data and target.is_staff and not self.request.user.is_superuser:
            raise ValidationError("Apenas administradores gerais podem ativar ou desativar membros da equipe.")
        if target.pk == self.request.user.pk and serializer.validated_data.get("is_active") is False:
            raise ValidationError("Você não pode desativar a própria conta.")
        user = serializer.save()
        record("admin.user_updated", request=self.request, target=user, fields=list(self.request.data))

    @action(detail=True, methods=["post"], url_path="reset-mfa")
    def reset_mfa(self, request, public_id=None):
        user = self.get_object()
        user.totp_enabled = False
        user.totp_secret_encrypted = None
        user.recovery_codes = []
        user.save(update_fields=["totp_enabled", "totp_secret_encrypted", "recovery_codes"])
        record("admin.user_mfa_reset", request=request, target=user)
        return Response(s.UserAdminSerializer(user).data)

    @action(detail=True, methods=["post"], url_path="send-password-reset")
    def send_password_reset(self, request, public_id=None):
        user = self.get_object()
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)
        link = f"{settings.CORS_ALLOWED_ORIGINS[0]}/redefinir-senha?uid={uid}&token={token}"
        mailer.send(
            "Redefinição de senha — RENAVE DIGITAL",
            f"Olá, {user.full_name}.\n\nA equipe do RENAVE DIGITAL enviou um link para você criar uma nova senha:\n{link}",
            [user.email],
        )
        record("admin.user_password_reset_sent", request=request, target=user)
        return Response(status=status.HTTP_202_ACCEPTED)

    @action(detail=False, methods=["post"], url_path="staff", permission_classes=[IsSuperAdmin])
    def create_staff(self, request):
        ser = s.StaffCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        password_validation.validate_password(d["password"])
        user = User.objects.create_user(
            email=d["email"], password=d["password"], full_name=d["full_name"], is_staff=True, is_superuser=d["is_superuser"]
        )
        record("admin.staff_created", request=request, target=user, superuser=d["is_superuser"])
        return Response(
            s.UserAdminSerializer(User.objects.annotate(organizations_count=Count("memberships")).get(pk=user.pk)).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["post"], url_path="staff-role", permission_classes=[IsSuperAdmin])
    def staff_role(self, request, public_id=None):
        user = self.get_object()
        if user.pk == request.user.pk:
            raise ValidationError("Você não pode alterar o próprio acesso.")
        role = request.data.get("role")
        if role not in ("none", "staff", "superuser"):
            raise ValidationError({"role": "Use none, staff ou superuser."})
        user.is_staff = role != "none"
        user.is_superuser = role == "superuser"
        user.save(update_fields=["is_staff", "is_superuser"])
        record("admin.staff_role_changed", request=request, target=user, role=role)
        return Response(s.UserAdminSerializer(User.objects.annotate(organizations_count=Count("memberships")).get(pk=user.pk)).data)


class MembershipAdminViewSet(AdminMixin, mixins.UpdateModelMixin, mixins.DestroyModelMixin, viewsets.GenericViewSet):
    queryset = Membership.objects.select_related("user", "organization")
    serializer_class = s.MemberAdminSerializer
    http_method_names = ["patch", "delete"]

    def perform_update(self, serializer):
        m = serializer.save()
        record("admin.membership_updated", request=self.request, organization=m.organization, target=m, role=m.role, active=m.is_active)

    def perform_destroy(self, instance):
        record("admin.membership_removed", request=self.request, organization=instance.organization, target=instance)
        instance.delete()


# --- Financeiro ---------------------------------------------------------------------


class TopUpAdminViewSet(AdminMixin, mixins.ListModelMixin, viewsets.GenericViewSet):
    queryset = TopUp.objects.select_related("organization", "requested_by")
    serializer_class = s.TopUpAdminSerializer
    search_fields = ("provider_reference", "organization__legal_name", "organization__cnpj")

    def get_queryset(self):
        qs = super().get_queryset()
        if st := self.request.query_params.get("status"):
            qs = qs.filter(status=st)
        return qs.order_by("-created_at")

    @action(detail=True, methods=["post"])
    def confirm(self, request, public_id=None):
        topup = wallet.confirm_topup(self.get_object(), user=request.user)
        record("wallet.topup_confirmed", request=request, organization=topup.organization, target=topup, amount_cents=topup.amount_cents)
        return Response(s.TopUpAdminSerializer(topup).data)

    @action(detail=True, methods=["post"])
    def cancel(self, request, public_id=None):
        topup = wallet.cancel_topup(self.get_object())
        record("wallet.topup_canceled", request=request, organization=topup.organization, target=topup)
        return Response(s.TopUpAdminSerializer(topup).data)


class LedgerAdminViewSet(AdminMixin, mixins.ListModelMixin, viewsets.GenericViewSet):
    queryset = LedgerEntry.objects.select_related("created_by", "wallet__organization")
    serializer_class = s.LedgerAdminSerializer
    org_field = "wallet__organization"
    search_fields = ("description",)

    def get_queryset(self):
        qs = super().get_queryset()
        if kind := self.request.query_params.get("kind"):
            qs = qs.filter(kind=kind)
        return qs


# --- Catálogo e preços --------------------------------------------------------------


class ProductAdminViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAdminSession]
    queryset = Product.objects.all().order_by("sort_order", "name")
    serializer_class = s.ProductAdminSerializer
    pagination_class = None

    def perform_create(self, serializer):
        p = serializer.save()
        record("admin.product_created", request=self.request, target=p, code=p.code)

    def perform_update(self, serializer):
        p = serializer.save()
        record("admin.product_updated", request=self.request, target=p, code=p.code, fields=list(self.request.data))

    def perform_destroy(self, instance):
        if instance.consultas.exists():
            raise ValidationError("Este produto já tem consultas. Desative-o em vez de excluir.")
        record("admin.product_deleted", request=self.request, code=instance.code)
        instance.delete()


class ServicePriceAdminViewSet(mixins.ListModelMixin, mixins.UpdateModelMixin, viewsets.GenericViewSet):
    permission_classes = [IsAdminSession]
    serializer_class = s.ServicePriceAdminSerializer
    pagination_class = None
    http_method_names = ["get", "patch"]

    def get_queryset(self):
        for code, price in DEFAULT_PRICES.items():
            ServicePrice.objects.get_or_create(code=code, defaults={"price_cents": price})
        return ServicePrice.objects.order_by("code")

    def perform_update(self, serializer):
        item = serializer.save()
        record("admin.price_updated", request=self.request, code=item.code, price_cents=item.price_cents)


# --- Operações ----------------------------------------------------------------------


class ConsultaAdminViewSet(AdminMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    queryset = Consulta.objects.select_related("organization", "product", "user")
    serializer_class = s.ConsultaAdminSerializer
    search_fields = ("input_value", "organization__legal_name", "organization__cnpj", "provider_consulta_id")

    def get_queryset(self):
        qs = super().get_queryset()
        if st := self.request.query_params.get("status"):
            qs = qs.filter(status=st)
        if prod := self.request.query_params.get("product"):
            qs = qs.filter(product__code=prod)
        return qs

    def retrieve(self, request, *args, **kwargs):
        consulta = self.get_object()
        data = s.ConsultaAdminSerializer(consulta).data
        if request.query_params.get("with_result") == "1":
            data["result"] = consulta.get_result()
            record("admin.consulta_result_viewed", request=request, organization=consulta.organization, target=consulta)
        return Response(data)


class NotaAdminViewSet(AdminMixin, mixins.ListModelMixin, viewsets.GenericViewSet):
    queryset = NotaFiscal.objects.select_related("organization")
    serializer_class = s.NotaAdminSerializer
    search_fields = ("chave", "destinatario_nome", "organization__legal_name", "organization__cnpj")

    def get_queryset(self):
        qs = super().get_queryset()
        if st := self.request.query_params.get("status"):
            qs = qs.filter(status=st)
        return qs


class StockAdminViewSet(AdminMixin, mixins.ListModelMixin, viewsets.GenericViewSet):
    queryset = StockVehicle.objects.select_related("organization", "client")
    serializer_class = s.StockAdminSerializer
    search_fields = ("placa", "renavam", "organization__legal_name", "organization__cnpj")

    def get_queryset(self):
        qs = super().get_queryset()
        if st := self.request.query_params.get("state"):
            qs = qs.filter(state=st)
        return qs


class RenaveOperationAdminViewSet(AdminMixin, mixins.ListModelMixin, viewsets.GenericViewSet):
    queryset = RenaveOperation.objects.select_related("organization", "vehicle", "user")
    serializer_class = s.RenaveOperationAdminSerializer
    search_fields = ("vehicle__placa", "message", "organization__legal_name")

    def get_queryset(self):
        qs = super().get_queryset()
        if self.request.query_params.get("success") in ("true", "false"):
            qs = qs.filter(success=self.request.query_params["success"] == "true")
        return qs


class ComunicacaoAdminViewSet(AdminMixin, mixins.ListModelMixin, viewsets.GenericViewSet):
    queryset = ComunicacaoVenda.objects.select_related("organization")
    serializer_class = s.ComunicacaoAdminSerializer
    search_fields = ("placa", "protocolo", "comprador_nome", "organization__legal_name")


class CertificateAdminViewSet(AdminMixin, mixins.ListModelMixin, viewsets.GenericViewSet):
    queryset = Certificate.objects.filter(is_active=True).select_related("organization", "client")
    serializer_class = s.CertificateAdminSerializer
    search_fields = ("holder_name", "holder_document", "organization__legal_name")

    def get_queryset(self):
        qs = super().get_queryset()
        if days := self.request.query_params.get("expiring_in"):
            qs = qs.filter(not_after__lte=timezone.now() + timedelta(days=int(days)))
        return qs.order_by("not_after")


# --- Sistema ------------------------------------------------------------------------


class IntegrationCallAdminViewSet(AdminMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    queryset = IntegrationCall.objects.select_related("organization")
    lookup_field = "pk"
    lookup_value_regex = "[0-9]+"
    search_fields = ("path", "error", "request_id")

    def get_serializer_class(self):
        return s.IntegrationCallDetailSerializer if self.action == "retrieve" else s.IntegrationCallAdminSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        p = self.request.query_params
        if prov := p.get("provider"):
            qs = qs.filter(provider=prov)
        if p.get("success") in ("true", "false"):
            qs = qs.filter(success=p["success"] == "true")
        return qs


class WebhookAdminViewSet(AdminMixin, mixins.ListModelMixin, viewsets.GenericViewSet):
    queryset = WebhookDelivery.objects.order_by("-received_at")
    serializer_class = s.WebhookAdminSerializer
    org_field = ""
    date_field = "received_at"
    search_fields = ("delivery_id", "event")


class AuditAdminViewSet(AdminMixin, mixins.ListModelMixin, viewsets.GenericViewSet):
    queryset = AuditEvent.objects.select_related("actor", "organization")
    serializer_class = s.AuditAdminSerializer
    search_fields = ("action", "actor__email", "target_id", "request_id", "ip")

    def get_queryset(self):
        qs = super().get_queryset()
        if a := self.request.query_params.get("action"):
            qs = qs.filter(action__startswith=a)
        return qs
