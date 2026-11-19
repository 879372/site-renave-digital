from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.db import transaction
from django.utils import timezone
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from rest_framework import permissions, status
from rest_framework.exceptions import APIException, AuthenticationFailed, PermissionDenied, Throttled, ValidationError
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.serializers import TokenRefreshSerializer
from rest_framework_simplejwt.tokens import RefreshToken

from audit.service import client_ip, record
from core import email as mailer
from organizations.models import Membership, Role
from organizations.service import create_organization

from . import lockout, totp, verification
from .models import User
from .serializers import (
    EmailCodeSerializer,
    LoginSerializer,
    MfaCodeSerializer,
    MfaDisableSerializer,
    MfaLoginSerializer,
    PasswordChangeSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetSerializer,
    RegisterSerializer,
    UserSerializer,
)
from .tokens import clear_refresh_cookie, issue_tokens, make_mfa_token, read_mfa_token, set_refresh_cookie

INVALID_CREDENTIALS = "E-mail ou senha incorretos."


class Unauthorized(APIException):
    """401 explícito: as views de login não têm classe de autenticação, e o DRF trocaria por 403."""

    status_code = status.HTTP_401_UNAUTHORIZED
    default_code = "not_authenticated"
    default_detail = "Não autenticado."


def _check_origin(request):
    origin = request.headers.get("Origin")
    if origin and origin not in settings.CORS_ALLOWED_ORIGINS:
        raise PermissionDenied("Origem não permitida.")


class AuthView(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"


def _session_response(user, request, status_code=status.HTTP_200_OK):
    access, refresh = issue_tokens(user)
    response = Response({"access": access, "user": UserSerializer(user).data}, status=status_code)
    set_refresh_cookie(response, refresh)
    return response


class RegisterView(AuthView):
    """Cria o usuário, a empresa e o vínculo de proprietário numa transação."""

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        with transaction.atomic():
            user = User.objects.create_user(
                email=data["email"],
                password=data["password"],
                full_name=data["full_name"],
                cpf=data["cpf"],
                phone=data["phone"],
                terms_accepted_at=timezone.now(),
                legal_version=settings.LEGAL_VERSION,
                marketing_opt_in=data.get("marketing_opt_in", False),
            )
            org = create_organization(
                user,
                cnpj=data["cnpj"],
                legal_name=data["legal_name"],
                trade_name=data.get("trade_name", ""),
                kind=data["kind"],
                uf=data["uf"],
                city=data["city"],
                email=data["email"],
                phone=data["phone"],
            )
            record("account.registered", request=request, actor=user, organization=org, target=org)
            record("legal.accepted", request=request, actor=user, organization=org, version=settings.LEGAL_VERSION)
            verification.send_code(user)
        return _session_response(user, request, status.HTTP_201_CREATED)


class LoginView(AuthView):
    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"].lower()
        ip = client_ip(request) or "-"
        if lockout.is_locked(email, ip):
            raise Throttled(detail="Muitas tentativas. Aguarde alguns minutos e tente novamente.")

        user = User.objects.filter(email=email).first()
        if user is None or not user.is_active or not user.check_password(serializer.validated_data["password"]):
            if user is None:
                User().set_password(serializer.validated_data["password"])  # tempo constante
            lockout.register_failure(email, ip)
            record("auth.login_failed", request=request, actor=user, email_hint=email[:3])
            raise Unauthorized(INVALID_CREDENTIALS)

        lockout.reset(email)
        if user.totp_enabled:
            return Response({"mfa_required": True, "mfa_token": make_mfa_token(user)})
        record("auth.login", request=request, actor=user)
        return _session_response(user, request)


class MfaLoginView(AuthView):
    def post(self, request):
        serializer = MfaLoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        uid = read_mfa_token(serializer.validated_data["mfa_token"])
        user = User.objects.filter(public_id=uid, is_active=True).first() if uid else None
        if user is None:
            raise Unauthorized("Sessão de verificação expirada. Entre novamente.")
        ip = client_ip(request) or "-"
        if lockout.is_locked(user.email, ip):
            raise Throttled(detail="Muitas tentativas. Aguarde alguns minutos e tente novamente.")
        code = serializer.validated_data["code"]
        if not (totp.verify(user, code) or totp.consume_recovery_code(user, code)):
            lockout.register_failure(user.email, ip)
            record("auth.mfa_failed", request=request, actor=user)
            raise Unauthorized("Código inválido.")
        lockout.reset(user.email)
        record("auth.login", request=request, actor=user, mfa=True)
        return _session_response(user, request)


class RefreshView(AuthView):
    throttle_scope = "user"

    def post(self, request):
        _check_origin(request)
        raw = request.COOKIES.get(settings.REFRESH_COOKIE_NAME)
        if not raw:
            raise Unauthorized("Sessão expirada.")
        serializer = TokenRefreshSerializer(data={"refresh": raw})
        try:
            serializer.is_valid(raise_exception=True)
        except TokenError:
            response = Response({"error": {"code": "session_expired", "message": "Sessão expirada."}}, status=401)
            clear_refresh_cookie(response)
            return response
        except Exception:
            response = Response({"error": {"code": "session_expired", "message": "Sessão expirada."}}, status=401)
            clear_refresh_cookie(response)
            return response
        response = Response({"access": serializer.validated_data["access"]})
        set_refresh_cookie(response, serializer.validated_data.get("refresh", raw))
        return response


class LogoutView(AuthView):
    def post(self, request):
        _check_origin(request)
        raw = request.COOKIES.get(settings.REFRESH_COOKIE_NAME)
        if raw:
            try:
                RefreshToken(raw).blacklist()
            except TokenError:
                pass
        response = Response(status=status.HTTP_204_NO_CONTENT)
        clear_refresh_cookie(response)
        return response


class MeView(APIView):
    allow_unverified_email = True

    def get(self, request):
        memberships = (
            Membership.objects.filter(user=request.user, is_active=True, organization__is_active=True)
            .select_related("organization")
            .order_by("organization__legal_name")
        )
        return Response(
            {
                "user": UserSerializer(request.user).data,
                "legal_version": settings.LEGAL_VERSION,
                "organizations": [
                    {
                        "id": str(m.organization.public_id),
                        "name": str(m.organization),
                        "cnpj": m.organization.cnpj,
                        "kind": m.organization.kind,
                        "role": m.role,
                        "mfa_required": m.organization.mfa_required,
                    }
                    for m in memberships
                ],
            }
        )

    def patch(self, request):
        serializer = UserSerializer(request.user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class PasswordChangeView(APIView):
    allow_unverified_email = True

    def post(self, request):
        serializer = PasswordChangeSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        request.user.set_password(serializer.validated_data["new_password"])
        request.user.save(update_fields=["password", "password_changed_at"])
        record("auth.password_changed", request=request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class PasswordResetView(AuthView):
    """Sempre responde 202 para não revelar se o e-mail existe."""

    def post(self, request):
        serializer = PasswordResetSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = User.objects.filter(email=serializer.validated_data["email"].lower(), is_active=True).first()
        if user:
            uid = urlsafe_base64_encode(force_bytes(user.pk))
            token = default_token_generator.make_token(user)
            link = f"{settings.CORS_ALLOWED_ORIGINS[0]}/redefinir-senha?uid={uid}&token={token}"
            mailer.send(
                "Redefinição de senha — RENAVE DIGITAL",
                f"Olá, {user.full_name}.\n\nPara criar uma nova senha, acesse:\n{link}\n\n"
                "Se você não pediu a redefinição, ignore este e-mail.",
                [user.email],
            )
            record("auth.password_reset_requested", request=request, actor=user)
        return Response(status=status.HTTP_202_ACCEPTED)


class PasswordResetConfirmView(AuthView):
    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            pk = force_str(urlsafe_base64_decode(serializer.validated_data["uid"]))
            user = User.objects.get(pk=pk, is_active=True)
        except (User.DoesNotExist, ValueError, TypeError, OverflowError):
            user = None
        if user is None or not default_token_generator.check_token(user, serializer.validated_data["token"]):
            raise Unauthorized("Link inválido ou expirado.")
        from django.contrib.auth import password_validation

        password_validation.validate_password(serializer.validated_data["new_password"], user)
        user.set_password(serializer.validated_data["new_password"])
        user.save(update_fields=["password", "password_changed_at"])
        verification.mark_verified(user)  # o link chegou na caixa de entrada: o e-mail é dele
        lockout.reset(user.email)
        record("auth.password_reset", request=request, actor=user)
        return Response(status=status.HTTP_204_NO_CONTENT)


class EmailCodeSendView(APIView):
    """Envia (ou reenvia) o código de confirmação. Respeita um intervalo mínimo entre envios."""

    allow_unverified_email = True
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"

    def post(self, request):
        user = request.user
        if user.email_verified:
            return Response({"verified": True, "sent": False, "retry_in": 0})
        wait = verification.send_code(user)
        if not wait:
            record("auth.email_code_sent", request=request)
        return Response({"verified": False, "sent": not wait, "retry_in": wait or verification.RESEND_COOLDOWN})


class EmailCodeVerifyView(APIView):
    allow_unverified_email = True
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"

    def post(self, request):
        user = request.user
        if user.email_verified:
            return Response(status=status.HTTP_204_NO_CONTENT)
        serializer = EmailCodeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = verification.check_code(user, serializer.validated_data["code"])
        if result == "expired":
            record("auth.email_verify_failed", request=request, reason="expired")
            raise ValidationError({"code": ["Este código expirou. Peça um novo código."]})
        if result == "invalid":
            record("auth.email_verify_failed", request=request, reason="invalid")
            raise ValidationError({"code": ["Código incorreto. Confira o e-mail e tente de novo."]})
        verification.mark_verified(user)
        record("auth.email_verified", request=request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class MfaSetupView(APIView):
    """Gera um novo segredo (ainda não ativo) e devolve a URI para o QR code."""

    def post(self, request):
        user = request.user
        if user.totp_enabled:
            raise PermissionDenied("A verificação em duas etapas já está ativa.")
        secret = totp.new_secret()
        totp.store_secret(user, secret)
        user.save(update_fields=["totp_secret_encrypted"])
        return Response({"secret": secret, "otpauth_uri": totp.provisioning_uri(user, secret)})


class MfaEnableView(APIView):
    def post(self, request):
        serializer = MfaCodeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = request.user
        if not totp.verify(user, serializer.validated_data["code"]):
            raise AuthenticationFailed("Código inválido. Confira o horário do celular e tente de novo.")
        codes = totp.generate_recovery_codes(user)
        user.totp_enabled = True
        user.save(update_fields=["totp_enabled", "recovery_codes"])
        record("auth.mfa_enabled", request=request)
        return Response({"recovery_codes": codes})


class MfaDisableView(APIView):
    def post(self, request):
        serializer = MfaDisableSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = request.user
        if not user.check_password(serializer.validated_data["password"]) or not (
            totp.verify(user, serializer.validated_data["code"]) or totp.consume_recovery_code(user, serializer.validated_data["code"])
        ):
            raise AuthenticationFailed("Senha ou código inválido.")
        user.totp_enabled = False
        user.totp_secret_encrypted = None
        user.recovery_codes = []
        user.save(update_fields=["totp_enabled", "totp_secret_encrypted", "recovery_codes"])
        record("auth.mfa_disabled", request=request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class AcceptLegalView(APIView):
    """Registra o aceite de uma nova versão dos Termos/Política."""

    allow_unverified_email = True

    def post(self, request):
        request.user.terms_accepted_at = timezone.now()
        request.user.legal_version = settings.LEGAL_VERSION
        request.user.save(update_fields=["terms_accepted_at", "legal_version"])
        record("legal.accepted", request=request, version=settings.LEGAL_VERSION)
        return Response({"legal_version": settings.LEGAL_VERSION})


class DataExportView(APIView):
    """LGPD art. 18 (II e V): acesso e portabilidade dos dados do titular."""

    allow_unverified_email = True

    def get(self, request):
        from audit.models import AuditEvent
        from consultas.models import Consulta

        user = request.user
        data = {
            "gerado_em": timezone.now().isoformat(),
            "titular": {
                "nome": user.full_name,
                "email": user.email,
                "cpf": user.cpf,
                "telefone": user.phone,
                "cadastro": user.date_joined.isoformat(),
                "ultimo_acesso": user.last_login.isoformat() if user.last_login else None,
                "verificacao_duas_etapas": user.totp_enabled,
                "comunicacoes_comerciais": user.marketing_opt_in,
                "aceite_termos": {
                    "versao": user.legal_version,
                    "em": user.terms_accepted_at.isoformat() if user.terms_accepted_at else None,
                },
            },
            "empresas": [
                {
                    "empresa": str(m.organization),
                    "cnpj": m.organization.cnpj,
                    "papel": m.get_role_display(),
                    "desde": m.created_at.isoformat(),
                }
                for m in Membership.objects.filter(user=user).select_related("organization")
            ],
            "consultas_realizadas": [
                {
                    "data": c.created_at.isoformat(),
                    "produto": c.product.name,
                    "identificador": c.input_value,
                    "finalidade": c.get_purpose_display(),
                    "status": c.get_status_display(),
                }
                for c in Consulta.objects.filter(user=user).select_related("product")[:5000]
            ],
            "registros_de_acesso": [
                {"data": e.created_at.isoformat(), "acao": e.action, "ip": e.ip}
                for e in AuditEvent.objects.filter(actor=user).order_by("-created_at")[:2000]
            ],
        }
        record("privacy.data_exported", request=request)
        response = Response(data)
        response["Content-Disposition"] = 'attachment; filename="meus-dados-renave-digital.json"'
        return response


class AccountDeleteView(APIView):
    """LGPD art. 18 (VI): eliminação. Dados com obrigação legal de guarda (fiscais, RENAVE,
    auditoria) são mantidos pelo prazo legal, desvinculados da pessoa."""

    allow_unverified_email = True

    def post(self, request):
        from .serializers import AccountDeleteSerializer

        serializer = AccountDeleteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = request.user
        if not user.check_password(serializer.validated_data["password"]):
            raise PermissionDenied("Senha incorreta.")
        owned = Membership.objects.filter(user=user, role=Role.OWNER, is_active=True).select_related("organization")
        for m in owned:
            others = Membership.objects.filter(organization=m.organization, is_active=True).exclude(user=user)
            if others.exists():
                raise PermissionDenied(
                    f"Você é proprietário de {m.organization}, que tem outros membros. "
                    "Transfira a titularidade pelo suporte antes de excluir sua conta."
                )
        with transaction.atomic():
            for m in owned:
                m.organization.is_active = False
                m.organization.save(update_fields=["is_active"])
            record("privacy.account_deleted", request=request)
            Membership.objects.filter(user=user).delete()
            user.email = f"removido-{user.public_id.hex}@anonimo.invalid"
            user.full_name = "Usuário removido"
            user.cpf = ""
            user.phone = ""
            user.is_active = False
            user.totp_enabled = False
            user.totp_secret_encrypted = None
            user.recovery_codes = []
            user.anonymized_at = timezone.now()
            user.set_unusable_password()
            user.save()
        raw = request.COOKIES.get(settings.REFRESH_COOKIE_NAME)
        if raw:
            try:
                RefreshToken(raw).blacklist()
            except TokenError:
                pass
        response = Response(status=status.HTTP_204_NO_CONTENT)
        clear_refresh_cookie(response)
        return response
