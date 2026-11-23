"""Campos de serializer reutilizados pelos módulos da loja."""

from rest_framework import serializers


class OrgRelatedField(serializers.SlugRelatedField):
    """Relação por public_id restrita à empresa ativa (impede apontar para dados de outra loja)."""

    def __init__(self, model, **kwargs):
        self.model = model
        kwargs.setdefault("slug_field", "public_id")
        super().__init__(**kwargs)

    def get_queryset(self):
        org = self.context.get("organization")
        if org is None:
            return self.model.objects.none()
        return self.model.objects.filter(organization=org)

    def to_representation(self, obj):
        return str(obj.public_id)
