from django.contrib import admin

from .models import ClientCompany, Membership, Organization


class MembershipInline(admin.TabularInline):
    model = Membership
    extra = 0
    fk_name = "organization"
    raw_id_fields = ["user", "invited_by"]


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ["legal_name", "cnpj", "kind", "uf", "is_active", "created_at"]
    search_fields = ["legal_name", "trade_name", "cnpj"]
    list_filter = ["kind", "uf", "is_active"]
    inlines = [MembershipInline]


@admin.register(ClientCompany)
class ClientCompanyAdmin(admin.ModelAdmin):
    list_display = ["name", "document", "organization", "is_active"]
    search_fields = ["name", "document"]
