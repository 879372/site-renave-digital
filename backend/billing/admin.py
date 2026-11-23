from django.contrib import admin

from .models import Invoice, InvoiceItem, Plan, Subscription


@admin.register(Plan)
class PlanAdmin(admin.ModelAdmin):
    list_display = ["name", "code", "monthly_price_cents", "annual_price_cents", "vehicle_limit", "user_limit", "is_active"]


class InvoiceItemInline(admin.TabularInline):
    model = InvoiceItem
    extra = 0
    readonly_fields = ["kind", "description", "quantity", "total_cents"]
    can_delete = False


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ["organization", "plan", "status", "cycle", "trial_ends_at", "paid_through", "next_billing_date"]
    list_filter = ["status", "plan", "cycle"]
    search_fields = ["organization__legal_name", "organization__cnpj"]
    readonly_fields = ["organization"]


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ["created_at", "organization", "kind", "status", "total_cents", "due_date", "paid_at"]
    list_filter = ["status", "kind"]
    search_fields = ["organization__legal_name", "organization__cnpj", "provider_payment_id"]
    inlines = [InvoiceItemInline]
    readonly_fields = [f.name for f in Invoice._meta.fields]

    def has_add_permission(self, request):
        return False
