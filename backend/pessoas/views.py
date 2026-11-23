from django.db.models import Q
from rest_framework import serializers
from rest_framework.decorators import action
from rest_framework.response import Response

from core import documents
from core.viewsets import OrgViewSet

from .models import Pessoa


class PessoaSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="public_id", read_only=True)

    class Meta:
        model = Pessoa
        fields = [
            "id",
            "documento",
            "nome",
            "email",
            "telefone",
            "data_nascimento",
            "rg_ie",
            "cep",
            "logradouro",
            "numero",
            "complemento",
            "bairro",
            "cidade",
            "cidade_ibge",
            "uf",
            "is_cliente",
            "is_fornecedor",
            "observacoes",
            "created_at",
        ]

    def validate_documento(self, value):
        value = documents.normalize_document(value or "")
        if value and not documents.is_valid_document(value):
            raise serializers.ValidationError("CPF/CNPJ inválido.")
        org = self.context["organization"]
        if value and Pessoa.objects.filter(organization=org, documento=value).exclude(pk=getattr(self.instance, "pk", None)).exists():
            raise serializers.ValidationError("Já existe um cadastro com este documento.")
        return value

    def validate_cep(self, value):
        return documents.only_digits(value or "")[:8]

    def validate_uf(self, value):
        return (value or "").upper()[:2]


class PessoaViewSet(OrgViewSet):
    queryset = Pessoa.objects.all()
    serializer_class = PessoaSerializer
    required_feature = "estoque"
    write_perm = "vendas.operate"

    def get_queryset(self):
        qs = super().get_queryset()
        p = self.request.query_params
        if term := p.get("search", "").strip():
            digits = documents.only_digits(term)
            cond = Q(nome__icontains=term) | Q(email__icontains=term)
            if digits:
                cond |= Q(documento__startswith=digits) | Q(telefone__contains=digits)
            qs = qs.filter(cond)
        if p.get("tipo") == "cliente":
            qs = qs.filter(is_cliente=True)
        elif p.get("tipo") == "fornecedor":
            qs = qs.filter(is_fornecedor=True)
        return qs

    @action(detail=False, methods=["get"])
    def choices(self, request):
        """Lista curta para selects (até 50, com busca)."""
        qs = self.get_queryset()[:50]
        return Response([{"id": str(p.public_id), "nome": p.nome, "documento": p.documento} for p in qs])
