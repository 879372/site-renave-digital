from django.db.models import Count, Q, Sum
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import APIException, NotFound
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle

from audit.service import record
from core.pagination import CreatedCursorPagination
from organizations.tenancy import OrganizationPermission, resolve_membership

from . import service
from .models import Consulta, Product
from .serializers import ConsultaCreateSerializer, ConsultaDetailSerializer, ConsultaSerializer, ProductSerializer


class ProductViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    serializer_class = ProductSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None
    queryset = Product.objects.filter(is_active=True)


class ConsultaViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.CreateModelMixin, viewsets.GenericViewSet):
    permission_classes = [OrganizationPermission]
    required_perms = {"list": "view", "retrieve": "view", "summary": "view", "create": "consultas.run", "refresh": "view"}
    pagination_class = CreatedCursorPagination
    lookup_field = "public_id"
    lookup_value_regex = "[0-9a-f-]{36}"
    filterset_fields = ["status", "input_value"]

    def get_throttles(self):
        if self.action == "create":
            self.throttle_scope = "consulta"
            return [ScopedRateThrottle()]
        return super().get_throttles()

    def get_queryset(self):
        resolve_membership(self.request)
        qs = Consulta.objects.filter(organization=self.request.organization).select_related("product", "user")
        if search := self.request.query_params.get("search"):
            qs = qs.filter(input_value__icontains=search.replace("-", "").upper())
        return qs

    def get_serializer_class(self):
        return ConsultaDetailSerializer if self.action == "retrieve" else ConsultaSerializer

    def create(self, request):
        serializer = ConsultaCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        product = Product.objects.filter(code=serializer.validated_data["product"], is_active=True).first()
        if product is None:
            raise NotFound("Produto não encontrado.")
        try:
            consulta = service.start(
                organization=request.organization,
                user=request.user,
                product=product,
                value=serializer.validated_data["value"],
                purpose=serializer.validated_data["purpose"],
            )
        except APIException as exc:
            record("consulta.failed", request=request, product=product.code, reason=getattr(exc, "default_code", "error"))
            raise
        record("consulta.created", request=request, target=consulta, product=product.code, status=consulta.status)
        code = status.HTTP_202_ACCEPTED if consulta.status == Consulta.Status.PROCESSING else status.HTTP_201_CREATED
        return Response(ConsultaDetailSerializer(consulta).data, status=code)

    @action(detail=True, methods=["post"])
    def refresh(self, request, public_id=None):
        consulta = self.get_object()
        service.refresh(consulta)
        return Response(ConsultaDetailSerializer(consulta).data)

    @action(detail=False, methods=["get"])
    def summary(self, request):
        from datetime import timedelta

        from django.utils import timezone

        since = timezone.now() - timedelta(days=30)
        qs = self.get_queryset().filter(created_at__gte=since)
        agg = qs.aggregate(
            total=Count("id"),
            success=Count("id", filter=Q(status=Consulta.Status.SUCCESS)),
            spent=Sum("charged_cents"),
        )
        return Response({"last_30_days": {**agg, "spent": agg["spent"] or 0}})
