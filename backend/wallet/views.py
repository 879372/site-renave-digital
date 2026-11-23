from rest_framework import mixins, viewsets
from rest_framework.response import Response
from rest_framework.views import APIView

from audit.service import record
from core.pagination import CreatedCursorPagination
from organizations.tenancy import OrganizationPermission, resolve_membership

from .models import LedgerEntry, TopUp
from .payments import get_provider
from .serializers import LedgerEntrySerializer, TopUpSerializer
from .service import get_wallet


class WalletView(APIView):
    permission_classes = [OrganizationPermission]
    required_perm = "view"

    def get(self, request):
        wallet = get_wallet(request.organization)
        return Response(
            {
                "balance_cents": wallet.balance_cents,
                "credit_limit_cents": wallet.credit_limit_cents,
                "available_cents": wallet.available_cents,
                "updated_at": wallet.updated_at,
            }
        )


class PriceListView(APIView):
    permission_classes = [OrganizationPermission]
    required_perm = "view"

    def get(self, request):
        from .models import ServicePrice
        from .service import price_for

        org = request.organization
        return Response([{"code": c.value, "label": c.label, "price_cents": price_for(c.value, org)} for c in ServicePrice.Code])


class LedgerViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    serializer_class = LedgerEntrySerializer
    permission_classes = [OrganizationPermission]
    required_perm = "view"
    pagination_class = CreatedCursorPagination
    filterset_fields = ["kind"]

    def get_queryset(self):
        resolve_membership(self.request)
        return LedgerEntry.objects.filter(wallet__organization=self.request.organization)


class TopUpViewSet(mixins.ListModelMixin, mixins.CreateModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    serializer_class = TopUpSerializer
    permission_classes = [OrganizationPermission]
    required_perms = {"list": "view", "retrieve": "view", "create": "wallet.manage"}
    lookup_field = "public_id"
    lookup_value_regex = "[0-9a-f-]{36}"

    def get_queryset(self):
        resolve_membership(self.request)
        return TopUp.objects.filter(organization=self.request.organization)

    def perform_create(self, serializer):
        provider = get_provider()
        topup = serializer.save(organization=self.request.organization, requested_by=self.request.user, provider=provider.name)
        charge = provider.create_charge(topup)
        topup.provider_reference = charge.reference
        topup.pix_copy_paste = charge.pix_copy_paste
        topup.pix_qr_base64 = charge.pix_qr_base64
        topup.expires_at = charge.expires_at
        topup.save(update_fields=["provider_reference", "pix_copy_paste", "pix_qr_base64", "expires_at"])
        record("wallet.topup_requested", request=self.request, target=topup, amount_cents=topup.amount_cents)
