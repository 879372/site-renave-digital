"""Transporte real por HTTPS; Resend simulado, sem mandar e-mails nos testes."""

import json
from unittest.mock import patch

import httpx
import pytest
import respx
from django.core.mail import EmailMessage, EmailMultiAlternatives

from core.email import _deliver
from core.email_backend import DELIVERY_HEADER, ResendDeliveryError

ENDPOINT = "https://api.resend.com/emails"


@pytest.fixture(autouse=True)
def resend_backend(settings):
    settings.EMAIL_BACKEND = "core.email_backend.ResendEmailBackend"
    settings.RESEND_API_KEY = "re_unit_test"
    settings.DEFAULT_FROM_EMAIL = "REVENDA DIGITAL <nao-responda@kaibez.com.br>"
    settings.SUPPORT_EMAIL = "contato@kaibez.com.br"


@respx.mock
def test_https_payload_preserva_remetente_replyto_e_texto():
    route = respx.post(ENDPOINT).mock(return_value=httpx.Response(200, json={"id": "email-123"}))
    msg = EmailMessage("Confirmação", "Código de teste: 123456", to=["teste@example.com"], reply_to=["contato@kaibez.com.br"])
    with patch("smtplib.SMTP", side_effect=AssertionError("SMTP não deve ser usado")):
        assert msg.send() == 1
    payload = json.loads(route.calls[0].request.content)
    assert payload == {
        "from": "REVENDA DIGITAL <nao-responda@kaibez.com.br>",
        "to": ["teste@example.com"],
        "reply_to": ["contato@kaibez.com.br"],
        "subject": "Confirmação",
        "text": "Código de teste: 123456",
    }
    assert route.calls[0].request.headers["Authorization"] == "Bearer re_unit_test"
    assert msg.resend_message_id == "email-123"


@respx.mock
def test_repeticao_da_mesma_mensagem_mantem_idempotencia():
    route = respx.post(ENDPOINT).mock(return_value=httpx.Response(200, json={"id": "email-123"}))
    msg = EmailMessage("Teste", "Corpo", to=["teste@example.com"])
    msg.send()
    msg.send()
    keys = [call.request.headers["Idempotency-Key"] for call in route.calls]
    assert keys[0] == keys[1]
    assert DELIVERY_HEADER not in json.loads(route.calls[0].request.content).get("headers", {})


@respx.mock
def test_falha_temporaria_reagenda_a_tarefa_com_mesma_chave():
    route = respx.post(ENDPOINT).mock(side_effect=[httpx.Response(429), httpx.Response(200, json={"id": "email-retry"})])
    result = _deliver.apply(args=("Teste", "Corpo", ["teste@example.com"]), task_id="delivery-test-id")
    assert result.successful() and result.result == {"provider_id": "email-retry"}
    assert route.call_count == 2
    assert {call.request.headers["Idempotency-Key"] for call in route.calls} == {"revenda/delivery-test-id"}


@respx.mock
def test_dominio_ou_chave_invalida_nao_entra_em_ciclo_de_tentativas():
    route = respx.post(ENDPOINT).mock(return_value=httpx.Response(403, json={"message": "privado: re_unit_test"}))
    result = _deliver.apply(args=("Teste", "Corpo", ["teste@example.com"]), task_id="denied-id")
    assert result.failed() and isinstance(result.result, ResendDeliveryError)
    assert not result.result.retryable and route.call_count == 1
    assert "re_unit_test" not in str(result.result) and "teste@example.com" not in str(result.result)


@respx.mock
def test_timeout_e_retentavel_sem_expor_conteudo():
    respx.post(ENDPOINT).mock(side_effect=httpx.ReadTimeout("conexão encerrada"))
    with pytest.raises(ResendDeliveryError) as exc:
        EmailMessage("Privado", "Código secreto", to=["teste@example.com"]).send()
    assert exc.value.retryable and "Código secreto" not in str(exc.value)


@respx.mock
def test_fail_silently_ignora_falha_sem_dizer_que_enviou():
    respx.post(ENDPOINT).mock(return_value=httpx.Response(503))
    assert EmailMessage("Teste", "Corpo", to=["teste@example.com"]).send(fail_silently=True) == 0


@respx.mock
def test_sucesso_sem_id_nao_e_confirmacao_de_envio():
    respx.post(ENDPOINT).mock(return_value=httpx.Response(200, json={}))
    with pytest.raises(ResendDeliveryError) as exc:
        EmailMessage("Teste", "Corpo", to=["teste@example.com"]).send()
    assert exc.value.retryable


@respx.mock
def test_mensagem_com_alternativa_html_e_copia():
    route = respx.post(ENDPOINT).mock(return_value=httpx.Response(200, json={"id": "html-id"}))
    msg = EmailMultiAlternatives("Teste", "Texto", to=["teste@example.com"], cc=["copia@example.com"])
    msg.attach_alternative("<p>Texto</p>", "text/html")
    msg.send()
    payload = json.loads(route.calls[0].request.content)
    assert payload["text"] == "Texto" and payload["html"] == "<p>Texto</p>" and payload["cc"] == ["copia@example.com"]
