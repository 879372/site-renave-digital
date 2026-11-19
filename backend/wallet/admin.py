from django.contrib import admin, messages

from audit.service import record

from .models import LedgerEntry, TopUp, Wallet
from .service import confirm_topup


@admin.register(Wallet)
class WalletAdmin(admin.ModelAdmin):
    list_display = ["organization", "balance_cents", "updated_at"]
    readonly_fields = ["organization", "balance_cents", "updated_at"]
    search_fields = ["organization__legal_name", "organization__cnpj"]

    def has_add_permission(self, request):
        return False


@admin.register(LedgerEntry)
class LedgerEntryAdmin(admin.ModelAdmin):
    list_display = ["created_at", "wallet", "kind", "amount_cents", "balance_after_cents", "description"]
    list_filter = ["kind"]
    search_fields = ["reference_id", "wallet__organization__cnpj"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(TopUp)
class TopUpAdmin(admin.ModelAdmin):
    list_display = ["created_at", "organization", "amount_cents", "status", "provider", "provider_reference"]
    list_filter = ["status", "provider"]
    search_fields = ["provider_reference", "organization__cnpj"]
    actions = ["confirm_payment"]
    readonly_fields = [f.name for f in TopUp._meta.fields]

    @admin.action(description="Confirmar pagamento e creditar")
    def confirm_payment(self, request, queryset):
        for topup in queryset.filter(status=TopUp.Status.PENDING):
            confirm_topup(topup, user=request.user)
            record(
                "wallet.topup_confirmed", request=request, organization=topup.organization, target=topup, amount_cents=topup.amount_cents
            )
        messages.success(request, "Recargas confirmadas.")


from .models import ServicePrice  # noqa: E402


@admin.register(ServicePrice)
class ServicePriceAdmin(admin.ModelAdmin):
    list_display = ["code", "price_cents", "is_active"]
    list_editable = ["price_cents", "is_active"]
