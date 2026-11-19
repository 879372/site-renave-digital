from django.contrib import admin

from .models import Certificate


@admin.register(Certificate)
class CertificateAdmin(admin.ModelAdmin):
    list_display = ["holder_name", "holder_document", "organization", "not_after", "is_active"]
    search_fields = ["holder_name", "holder_document"]
    exclude = ["pfx_encrypted", "password_encrypted"]
    readonly_fields = [f.name for f in Certificate._meta.fields if f.name not in ("pfx_encrypted", "password_encrypted")]

    def has_add_permission(self, request):
        return False
