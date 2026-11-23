from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from accounts.models import User
from audit.service import record
from core.fields import OrgRelatedField
from core.viewsets import OrgViewSet
from estoque.models import Vehicle
from pessoas.models import Pessoa

from .models import Interacao, Lead, Tarefa


class MemberField(serializers.SlugRelatedField):
    def __init__(self, **kwargs):
        super().__init__(slug_field="public_id", **kwargs)

    def get_queryset(self):
        org = self.context.get("organization")
        return User.objects.filter(memberships__organization=org, memberships__is_active=True) if org else User.objects.none()

    def to_representation(self, obj):
        return str(obj.public_id)


class InteracaoSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source="user.full_name", read_only=True, default=None)
    kind_display = serializers.CharField(source="get_kind_display", read_only=True)

    class Meta:
        model = Interacao
        fields = ["kind", "kind_display", "text", "user_name", "created_at"]


class TarefaSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="public_id", read_only=True)
    lead = OrgRelatedField(Lead, required=False, allow_null=True)
    lead_name = serializers.CharField(source="lead.name", read_only=True, default=None)
    owner = MemberField(required=False, allow_null=True)
    owner_name = serializers.CharField(source="owner.full_name", read_only=True, default=None)
    done = serializers.BooleanField(write_only=True, required=False)

    class Meta:
        model = Tarefa
        fields = ["id", "lead", "lead_name", "owner", "owner_name", "title", "due_at", "done_at", "done", "created_at"]
        read_only_fields = ["done_at"]

    def update(self, instance, validated_data):
        done = validated_data.pop("done", None)
        if done is not None:
            instance.done_at = timezone.now() if done else None
        return super().update(instance, validated_data)


class LeadSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="public_id", read_only=True)
    stage_display = serializers.CharField(source="get_stage_display", read_only=True)
    source_display = serializers.CharField(source="get_source_display", read_only=True)
    vehicle = OrgRelatedField(Vehicle, required=False, allow_null=True)
    vehicle_title = serializers.CharField(source="vehicle.title", read_only=True, default=None)
    owner = MemberField(required=False, allow_null=True)
    owner_name = serializers.CharField(source="owner.full_name", read_only=True, default=None)
    pessoa = OrgRelatedField(Pessoa, required=False, allow_null=True)
    open_tasks = serializers.SerializerMethodField()

    class Meta:
        model = Lead
        fields = [
            "id",
            "name",
            "phone",
            "email",
            "source",
            "source_display",
            "stage",
            "stage_display",
            "vehicle",
            "vehicle_title",
            "interest",
            "budget_cents",
            "owner",
            "owner_name",
            "pessoa",
            "lost_reason",
            "message",
            "position",
            "open_tasks",
            "created_at",
            "updated_at",
        ]

    def get_open_tasks(self, obj):
        return sum(1 for t in obj.tarefas.all() if not t.done_at)

    def validate(self, attrs):
        if not (attrs.get("phone") or attrs.get("email") or getattr(self.instance, "phone", "") or getattr(self.instance, "email", "")):
            raise serializers.ValidationError({"phone": "Informe telefone ou e-mail para retornar o contato."})
        if attrs.get("stage") == Lead.Stage.PERDIDO and not (attrs.get("lost_reason") or getattr(self.instance, "lost_reason", "")):
            raise serializers.ValidationError({"lost_reason": "Informe o motivo da perda."})
        return attrs


class LeadViewSet(OrgViewSet):
    queryset = Lead.objects.select_related("vehicle", "owner").prefetch_related("tarefas")
    serializer_class = LeadSerializer
    required_feature = "crm"
    write_perm = "vendas.operate"
    extra_perms = {"interactions": "vendas.operate", "move": "vendas.operate", "convert": "vendas.operate"}

    def get_queryset(self):
        qs = super().get_queryset()
        p = self.request.query_params
        if self.request._membership.role == "vendedor" and p.get("all") != "1":
            qs = qs.filter(Q(owner=self.request.user) | Q(owner__isnull=True))
        if st := p.get("stage"):
            qs = qs.filter(stage__in=st.split(","))
        if src := p.get("source"):
            qs = qs.filter(source=src)
        if owner := p.get("owner"):
            qs = qs.filter(owner__public_id=owner)
        if term := p.get("search", "").strip():
            qs = qs.filter(Q(name__icontains=term) | Q(phone__contains=term) | Q(email__icontains=term))
        return qs

    def perform_create(self, serializer):
        lead = serializer.save(organization=self.request.organization, owner=serializer.validated_data.get("owner") or self.request.user)
        record("crm.lead", request=self.request, target=lead, source=lead.source)

    def perform_update(self, serializer):
        old = serializer.instance.stage
        lead = serializer.save()
        if lead.stage != old:
            Interacao.objects.create(
                lead=lead, user=self.request.user, kind=Interacao.Kind.ETAPA, text=f"{Lead.Stage(old).label} → {lead.get_stage_display()}"
            )

    @action(detail=True, methods=["get", "post"])
    def interactions(self, request, public_id=None):
        lead = self.get_object()
        if request.method == "POST":
            s = InteracaoSerializer(data=request.data)
            s.is_valid(raise_exception=True)
            s.save(lead=lead, user=request.user)
            if lead.stage == Lead.Stage.NOVO:
                lead.stage = Lead.Stage.CONTATO
                lead.save(update_fields=["stage", "updated_at"])
            return Response(s.data, status=status.HTTP_201_CREATED)
        return Response(InteracaoSerializer(lead.interacoes.select_related("user")[:100], many=True).data)

    @action(detail=True, methods=["post"])
    def move(self, request, public_id=None):
        """Arrastar no funil: nova etapa e posição."""
        lead = self.get_object()
        stage = request.data.get("stage")
        if stage not in Lead.Stage.values:
            raise ValidationError({"stage": "Etapa inválida."})
        if stage == Lead.Stage.PERDIDO and not (request.data.get("lost_reason") or lead.lost_reason):
            raise ValidationError({"lost_reason": "Informe o motivo da perda."})
        old = lead.stage
        lead.stage = stage
        lead.position = int(request.data.get("position", 0) or 0)
        if request.data.get("lost_reason"):
            lead.lost_reason = str(request.data["lost_reason"])[:200]
        lead.save(update_fields=["stage", "position", "lost_reason", "updated_at"])
        if old != stage:
            Interacao.objects.create(
                lead=lead, user=request.user, kind=Interacao.Kind.ETAPA, text=f"{Lead.Stage(old).label} → {lead.get_stage_display()}"
            )
        return Response(self.get_serializer(lead).data)

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def convert(self, request, public_id=None):
        """Cria (ou reaproveita) o cadastro do cliente a partir do lead."""
        lead = self.get_object()
        if lead.pessoa_id:
            return Response({"pessoa_id": str(lead.pessoa.public_id)})
        pessoa = Pessoa.objects.create(
            organization=lead.organization, nome=lead.name, telefone=lead.phone, email=lead.email, is_cliente=True
        )
        lead.pessoa = pessoa
        lead.save(update_fields=["pessoa", "updated_at"])
        return Response({"pessoa_id": str(pessoa.public_id)}, status=status.HTTP_201_CREATED)


class TarefaViewSet(OrgViewSet):
    queryset = Tarefa.objects.select_related("lead", "owner")
    serializer_class = TarefaSerializer
    required_feature = "crm"
    write_perm = "vendas.operate"

    def get_queryset(self):
        qs = super().get_queryset()
        p = self.request.query_params
        if p.get("mine") == "1":
            qs = qs.filter(owner=self.request.user)
        if p.get("open") == "1":
            qs = qs.filter(done_at__isnull=True)
        if lead := p.get("lead"):
            qs = qs.filter(lead__public_id=lead)
        return qs

    def perform_create(self, serializer):
        serializer.save(organization=self.request.organization, owner=serializer.validated_data.get("owner") or self.request.user)
