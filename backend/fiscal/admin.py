from django.contrib import admin

from .models import FiscalSettings, NotaFiscal


@admin.register(NotaFiscal)
class NotaFiscalAdmin(admin.ModelAdmin):
    list_display = ["created_at", "organization", "serie", "numero", "tipo", "status", "cstat", "total_cents"]
    list_filter = ["status", "tipo", "ambiente"]
    search_fields = ["chave", "organization__cnpj", "destinatario_nome"]
    exclude = ["payload_encrypted", "xml", "pdf"]


admin.site.register(FiscalSettings)
