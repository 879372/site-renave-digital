"""Configuração do site da loja, anúncios e as rotas públicas (vitrine, contato e feed para portais)."""

import secrets
from xml.etree.ElementTree import Element, SubElement, tostring

from django.conf import settings
from django.db.models import Prefetch
from django.http import Http404, HttpResponse
from rest_framework import permissions, serializers, status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView

from audit.service import record
from billing.entitlements import has_feature
from billing.permissions import PlanFeaturePermission
from core.fields import OrgRelatedField
from core.viewsets import OrgViewSet
from crm.models import Lead
from estoque.models import Vehicle, VehiclePhoto
from estoque.serializers import file_url
from organizations.tenancy import OrganizationPermission

from .models import RESERVED, Anuncio, Site

PUBLIC_STATUSES = (Vehicle.Status.DISPONIVEL, Vehicle.Status.RESERVADO)


class SiteSerializer(serializers.ModelSerializer):
    url = serializers.SerializerMethodField()
    feed_url = serializers.SerializerMethodField()
    logo_url = serializers.SerializerMethodField()

    class Meta:
        model = Site
        fields = [
            "slug",
            "is_published",
            "title",
            "about",
            "whatsapp",
            "phone",
            "email",
            "address",
            "instagram",
            "accent_color",
            "url",
            "feed_url",
            "logo_url",
        ]

    def validate_slug(self, value):
        value = value.lower().strip()
        if value in RESERVED:
            raise serializers.ValidationError("Este endereço é reservado. Escolha outro.")
        if Site.objects.filter(slug=value).exclude(pk=getattr(self.instance, "pk", None)).exists():
            raise serializers.ValidationError("Este endereço já está em uso.")
        return value

    def validate_accent_color(self, value):
        import re

        if not re.fullmatch(r"#[0-9a-fA-F]{6}", value or ""):
            raise serializers.ValidationError("Cor inválida (use #RRGGBB).")
        return value

    def get_url(self, obj):
        return f"https://{obj.slug}.{settings.STOREFRONT_DOMAIN}"

    def get_feed_url(self, obj):
        if not obj.feed_token:
            return None
        return f"{settings.PUBLIC_API_URL}/api/public/feed/{obj.slug}/{obj.feed_token}.xml"

    def get_logo_url(self, obj):
        return file_url(self.context.get("request"), obj.logo)


class SiteView(APIView):
    permission_classes = [OrganizationPermission, PlanFeaturePermission]
    required_feature = "vitrine"
    required_perms = {"get": "view", "put": "org.manage", "post": "org.manage"}

    def get(self, request):
        site = Site.objects.filter(organization=request.organization).first()
        if site is None:
            return Response({"configured": False})
        return Response(SiteSerializer(site, context={"request": request}).data)

    def put(self, request):
        site = Site.objects.filter(organization=request.organization).first()
        s = SiteSerializer(site, data=request.data, partial=site is not None, context={"request": request})
        s.is_valid(raise_exception=True)
        site = s.save(organization=request.organization) if site is None else s.save()
        if not site.feed_token:
            site.feed_token = secrets.token_urlsafe(24)
            site.save(update_fields=["feed_token"])
        record("site.atualizado", request=request, target=site)
        return Response(SiteSerializer(site, context={"request": request}).data)

    def post(self, request):
        """Novo token do feed (invalida o link antigo dos portais)."""
        site = Site.objects.filter(organization=request.organization).first()
        if site is None:
            raise ValidationError({"slug": "Configure o site primeiro."})
        site.feed_token = secrets.token_urlsafe(24)
        site.save(update_fields=["feed_token"])
        return Response(SiteSerializer(site, context={"request": request}).data)


class AnuncioSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="public_id", read_only=True)
    vehicle = OrgRelatedField(Vehicle)
    vehicle_title = serializers.CharField(source="vehicle.title", read_only=True)
    portal_display = serializers.CharField(source="get_portal_display", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = Anuncio
        fields = ["id", "vehicle", "vehicle_title", "portal", "portal_display", "status", "status_display", "external_id", "url", "message"]


class AnuncioViewSet(OrgViewSet):
    queryset = Anuncio.objects.select_related("vehicle")
    serializer_class = AnuncioSerializer
    required_feature = "vitrine"
    write_perm = "estoque.manage"
    pagination_class = None

    def get_queryset(self):
        qs = super().get_queryset()
        if v := self.request.query_params.get("vehicle"):
            qs = qs.filter(vehicle__public_id=v)
        return qs

    def perform_create(self, serializer):
        if Anuncio.objects.filter(vehicle=serializer.validated_data["vehicle"], portal=serializer.validated_data["portal"]).exists():
            raise ValidationError({"portal": "Este veículo já está neste portal."})
        serializer.save(organization=self.request.organization)


# --- rotas públicas ----------------------------------------------------------------------------


class PublicThrottle(AnonRateThrottle):
    rate = "120/min"


class ContactThrottle(AnonRateThrottle):
    scope = "contact"
    rate = "10/hour"


def _site(slug) -> Site:
    site = Site.objects.select_related("organization").filter(slug=slug.lower(), is_published=True, organization__is_active=True).first()
    if site is None or not has_feature(site.organization, "vitrine"):
        raise Http404
    return site


def _public_vehicle(request, v: Vehicle, full=False) -> dict:
    photos = getattr(v, "public_photos", None) or list(v.photos.all())
    data = {
        "id": str(v.public_id),
        "title": v.title,
        "marca": v.marca,
        "modelo": v.modelo,
        "versao": v.versao,
        "ano_fabricacao": v.ano_fabricacao,
        "ano_modelo": v.ano_modelo,
        "km": v.km,
        "cor": v.cor,
        "cambio": v.cambio,
        "combustivel": v.combustivel,
        "price_cents": v.price_cents or None,
        "reserved": v.status == Vehicle.Status.RESERVADO,
        "featured": v.featured,
        "cover": file_url(request, photos[0].image) if photos else None,
    }
    if full:
        data.update(
            {
                "photos": [file_url(request, p.image) for p in photos],
                "opcionais": v.opcionais,
                "descricao": v.descricao,
                "portas": v.portas,
                "final_placa": v.placa[-1:] if v.placa else "",
            }
        )
    return data


class PublicView(APIView):
    authentication_classes = []
    permission_classes = [permissions.AllowAny]
    throttle_classes = [PublicThrottle]


class PublicSiteView(PublicView):
    def get(self, request, slug):
        site = _site(slug)
        return Response({**SiteSerializer(site, context={"request": request}).data, "feed_url": None, "name": str(site.organization)})


class PublicVehiclesView(PublicView):
    def get(self, request, slug, vehicle_id=None):
        site = _site(slug)
        qs = Vehicle.objects.filter(organization=site.organization, published=True, status__in=PUBLIC_STATUSES).prefetch_related(
            Prefetch("photos", queryset=VehiclePhoto.objects.order_by("position"), to_attr="public_photos")
        )
        if vehicle_id:
            v = qs.filter(public_id=vehicle_id).first()
            if v is None:
                raise Http404
            return Response(_public_vehicle(request, v, full=True))
        p = request.query_params
        if marca := p.get("marca"):
            qs = qs.filter(marca__iexact=marca)
        if q := p.get("q", "").strip():
            qs = qs.filter(modelo__icontains=q) | qs.filter(marca__icontains=q)
        if mx := p.get("max"):
            try:
                maximum = int(mx)
                if not 0 <= maximum <= 2**63 - 1:
                    raise ValueError
            except (ValueError, TypeError):
                raise ValidationError({"max": "Informe um preço máximo inteiro e não negativo."})
            qs = qs.filter(price_cents__lte=maximum)
        qs = qs.order_by("-featured", "-created_at")[:200]
        brands = sorted(
            set(
                Vehicle.objects.filter(organization=site.organization, published=True, status__in=PUBLIC_STATUSES).values_list(
                    "marca", flat=True
                )
            )
        )
        return Response({"brands": brands, "results": [_public_vehicle(request, v) for v in qs]})


class ContactSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=150)
    phone = serializers.CharField(max_length=20)
    email = serializers.EmailField(required=False, allow_blank=True)
    message = serializers.CharField(max_length=1000, required=False, allow_blank=True)
    vehicle_id = serializers.UUIDField(required=False, allow_null=True)
    website = serializers.CharField(required=False, allow_blank=True)  # armadilha para robôs (campo oculto)
    consent = serializers.BooleanField()

    def validate_consent(self, value):
        if not value:
            raise serializers.ValidationError("É preciso aceitar o contato da loja.")
        return value


class PublicContactView(PublicView):
    throttle_classes = [ContactThrottle]

    def post(self, request, slug):
        site = _site(slug)
        s = ContactSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        if d.get("website"):
            return Response(status=status.HTTP_204_NO_CONTENT)
        vehicle = None
        if d.get("vehicle_id"):
            vehicle = Vehicle.objects.filter(organization=site.organization, public_id=d["vehicle_id"], published=True).first()
        if has_feature(site.organization, "crm"):
            Lead.objects.create(
                organization=site.organization,
                name=d["name"],
                phone=d["phone"],
                email=d.get("email", ""),
                source=Lead.Source.SITE,
                vehicle=vehicle,
                interest=vehicle.title if vehicle else "",
                message=d.get("message", ""),
            )
        return Response({"ok": True}, status=status.HTTP_201_CREATED)


class FeedView(PublicView):
    """Feed XML do estoque para portais que importam por URL (formato genérico de integradores)."""

    def get(self, request, slug, token):
        site = Site.objects.select_related("organization").filter(slug=slug.lower(), organization__is_active=True).first()
        if (
            site is None
            or not site.feed_token
            or not secrets.compare_digest(site.feed_token, token)
            or not has_feature(site.organization, "vitrine")
        ):
            raise Http404
        portal = request.query_params.get("portal")
        qs = Vehicle.objects.filter(organization=site.organization, status__in=PUBLIC_STATUSES).prefetch_related(
            Prefetch("photos", queryset=VehiclePhoto.objects.order_by("position"), to_attr="public_photos")
        )
        if portal:
            qs = qs.filter(anuncios__portal=portal, anuncios__status=Anuncio.Status.ATIVO)
        else:
            qs = qs.filter(published=True)
        root = Element("estoque", loja=str(site.organization), cnpj=site.organization.cnpj)
        for v in qs.distinct():
            item = SubElement(root, "veiculo", id=str(v.public_id))
            fields = {
                "tipo": v.kind,
                "marca": v.marca,
                "modelo": v.modelo,
                "versao": v.versao,
                "ano_fabricacao": v.ano_fabricacao,
                "ano_modelo": v.ano_modelo,
                "km": v.km,
                "cor": v.cor,
                "cambio": v.cambio,
                "combustivel": v.combustivel,
                "portas": v.portas,
                "preco": f"{v.price_cents / 100:.2f}" if v.price_cents else "",
                "final_placa": v.placa[-1:] if v.placa else "",
                "descricao": v.descricao,
                "codigo_fipe": v.fipe_code,
            }
            for key, value in fields.items():
                SubElement(item, key).text = "" if value is None else str(value)
            opc = SubElement(item, "opcionais")
            for o in v.opcionais or []:
                SubElement(opc, "opcional").text = str(o)
            fotos = SubElement(item, "fotos")
            for p in v.public_photos:
                SubElement(fotos, "foto").text = file_url(request, p.image)
        return HttpResponse(
            b'<?xml version="1.0" encoding="UTF-8"?>' + tostring(root, encoding="utf-8"), content_type="application/xml; charset=utf-8"
        )
