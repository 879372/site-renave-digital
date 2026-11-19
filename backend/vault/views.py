from rest_framework import mixins, status, viewsets
from rest_framework.exceptions import NotFound
from rest_framework.response import Response

from audit.service import record
from organizations.models import ClientCompany
from organizations.tenancy import OrganizationPermission, resolve_membership

from .models import Certificate
from .serializers import CertificateSerializer, CertificateUploadSerializer
from .service import store_certificate


class CertificateViewSet(mixins.ListModelMixin, mixins.DestroyModelMixin, viewsets.GenericViewSet):
    serializer_class = CertificateSerializer
    permission_classes = [OrganizationPermission]
    required_perms = {"list": "view", "create": "vault.manage", "destroy": "vault.manage"}
    lookup_field = "public_id"
    lookup_value_regex = "[0-9a-f-]{36}"

    def get_queryset(self):
        resolve_membership(self.request)
        return Certificate.objects.filter(organization=self.request.organization, is_active=True).select_related("client")

    def create(self, request):
        serializer = CertificateUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        client = None
        if serializer.validated_data.get("client_id"):
            client = ClientCompany.objects.filter(
                organization=request.organization, public_id=serializer.validated_data["client_id"], is_active=True
            ).first()
            if client is None:
                raise NotFound("Cliente não encontrado.")
        cert = store_certificate(
            organization=request.organization,
            client=client,
            pfx=serializer.validated_data["file"].read(),
            password=serializer.validated_data["password"],
            uploaded_by=request.user,
        )
        record("certificate.uploaded", request=request, target=cert, holder=cert.holder_document[-4:], client=bool(client))

        from renave.tasks import sync_certificate_to_carven

        sync_certificate_to_carven.delay(cert.pk)
        return Response(CertificateSerializer(cert).data, status=status.HTTP_201_CREATED)

    def perform_destroy(self, instance):
        instance.is_active = False
        instance.save(update_fields=["is_active"])
        record("certificate.deactivated", request=self.request, target=instance)
