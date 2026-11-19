from django.contrib import admin

from .models import ComunicacaoVenda


@admin.register(ComunicacaoVenda)
class ComunicacaoVendaAdmin(admin.ModelAdmin):
    list_display = ["created_at", "organization", "placa", "protocolo", "situacao", "valor_cents"]
    list_filter = ["situacao"]
    search_fields = ["placa", "protocolo"]
    exclude = ["payload_encrypted"]
