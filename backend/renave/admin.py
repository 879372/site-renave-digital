from django.contrib import admin

from .models import RenaveOperation, StockVehicle


class OperationInline(admin.TabularInline):
    model = RenaveOperation
    extra = 0
    fields = ["created_at", "kind", "success", "message", "price_cents"]
    readonly_fields = fields
    can_delete = False


@admin.register(StockVehicle)
class StockVehicleAdmin(admin.ModelAdmin):
    list_display = ["placa", "organization", "client", "state", "id_estoque", "entry_date", "exit_date"]
    list_filter = ["state"]
    search_fields = ["placa", "renavam", "organization__cnpj"]
    inlines = [OperationInline]
