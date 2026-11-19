from rest_framework import mixins, serializers, viewsets

from core.pagination import CreatedCursorPagination
from organizations.tenancy import OrganizationPermission, resolve_membership

from .models import AuditEvent


class AuditEventSerializer(serializers.ModelSerializer):
    actor = serializers.CharField(source="actor.full_name", default=None)

    class Meta:
        model = AuditEvent
        fields = ["id", "created_at", "actor", "action", "target_type", "target_id", "ip", "metadata"]


class AuditEventViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    serializer_class = AuditEventSerializer
    permission_classes = [OrganizationPermission]
    required_perm = "audit.view"
    pagination_class = CreatedCursorPagination
    filterset_fields = ["action"]

    def get_queryset(self):
        resolve_membership(self.request)
        return AuditEvent.objects.filter(organization=self.request.organization).select_related("actor")
