"""Respostas de erro fora das views da API (rota inexistente, falha não tratada).

Mantêm o mesmo formato JSON da API, {"error": {"code", "message"}}, em vez da página HTML do Django.
"""

from django.http import JsonResponse


def not_found(request, exception=None):
    return JsonResponse({"error": {"code": "not_found", "message": "Endereço não encontrado."}}, status=404)


def server_error(request):
    return JsonResponse(
        {"error": {"code": "server_error", "message": "Erro interno. Tente novamente em instantes."}},
        status=500,
    )
