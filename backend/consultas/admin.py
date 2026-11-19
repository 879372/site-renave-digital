from django.contrib import admin

from .models import Consulta, Product


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ["name", "code", "sku", "category", "input_type", "cost_cents", "price_cents", "is_active", "is_featured", "sort_order"]
    list_editable = ["price_cents", "is_active", "is_featured", "sort_order"]
    list_filter = ["is_active", "category", "input_type"]
    search_fields = ["name", "code", "sku"]
    prepopulated_fields = {"code": ("name",)}


@admin.register(Consulta)
class ConsultaAdmin(admin.ModelAdmin):
    list_display = ["created_at", "organization", "sku", "input_value", "status", "price_cents", "charged_cents", "provider_cost_cents"]
    list_filter = ["status", "sku"]
    search_fields = ["input_value", "provider_consulta_id", "organization__cnpj"]
    exclude = ["result_encrypted"]
    readonly_fields = [f.name for f in Consulta._meta.fields if f.name != "result_encrypted"]

    def has_add_permission(self, request):
        return False
