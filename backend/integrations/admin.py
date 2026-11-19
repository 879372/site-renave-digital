from django.contrib import admin

from .models import IntegrationCall, WebhookDelivery


@admin.register(IntegrationCall)
class IntegrationCallAdmin(admin.ModelAdmin):
    list_display = ["created_at", "provider", "method", "path", "status_code", "duration_ms", "success"]
    list_filter = ["provider", "success"]
    search_fields = ["path", "request_id"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(WebhookDelivery)
class WebhookDeliveryAdmin(admin.ModelAdmin):
    list_display = ["received_at", "provider", "event", "delivery_id"]
    list_filter = ["provider", "event"]
