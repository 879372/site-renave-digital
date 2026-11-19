"""Login do painel administrativo: e-mail e senha, sessão separada da do lojista.

O token de admin carrega o claim `scope=admin`; as rotas /api/admin/* só aceitam esse token,
e o refresh fica num cookie próprio (rd_admin_refresh) restrito a /api/admin/auth/.
"""

from django.conf import settings
from django.contrib.auth.models import update_last_login
from rest_framework import permissions, status
from rest_framework.exceptions import PermissionDenied, Throttled
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from accounts import lockout
from accounts.models import User
from accounts.views import AuthView, Unauthorized, _check_origin
from audit.service import client_ip, record

COOKIE = "rd_admin_refresh"
COOKIE_PATH = "/api/admin/auth/"
SCOPE = "admin"


class IsAdminSession(permissions.BasePermission):
    message = "Acesso restrito à equipe administrativa."

    def has_permission(self, request, view):
        user = request.user
        token = request.auth
        return bool(
            user and user.is_authenticated and user.is_active and user.is_staff and token is not None and token.get("scope") == SCOPE
        )


class IsSuperAdmin(IsAdminSession):
    message = "Apenas administradores gerais podem fazer isso."

    def has_permission(self, request, view):
        return super().has_permission(request, view) and request.user.is_superuser


def _set_cookie(response, refresh: str):
    response.set_cookie(
        COOKIE,
        refresh,
        max_age=60 * 60 * 12,
        httponly=True,
        secure=settings.REFRESH_COOKIE_SECURE,
        samesite="Strict",
        path=COOKIE_PATH,
    )


def _clear_cookie(response):
    response.delete_cookie(COOKIE, path=COOKIE_PATH, samesite="Strict")


def admin_profile(user: User) -> dict:
    return {
        "id": str(user.public_id),
        "email": user.email,
        "full_name": user.full_name,
        "is_superuser": user.is_superuser,
    }


class AdminLoginView(AuthView):
    def post(self, request):
        email = str(request.data.get("email", "")).strip().lower()
        password = str(request.data.get("password", ""))
        if not email or not password:
            raise Unauthorized("Informe e-mail e senha.")
        ip = client_ip(request) or "-"
        if lockout.is_locked(email, ip):
            raise Throttled(detail="Muitas tentativas. Aguarde alguns minutos e tente novamente.")
        user = User.objects.filter(email=email).first()
        if user is None or not user.is_active or not user.is_staff or not user.check_password(password):
            if user is None:
                User().set_password(password)
            lockout.register_failure(email, ip)
            record("admin.login_failed", request=request, actor=user, email_hint=email[:3])
            raise Unauthorized("E-mail ou senha incorretos.")
        lockout.reset(email)
        update_last_login(None, user)
        refresh = RefreshToken.for_user(user)
        refresh["scope"] = SCOPE
        record("admin.login", request=request, actor=user)
        response = Response({"access": str(refresh.access_token), "user": admin_profile(user)})
        _set_cookie(response, str(refresh))
        return response


class AdminRefreshView(AuthView):
    throttle_scope = "user"

    def post(self, request):
        _check_origin(request)
        raw = request.COOKIES.get(COOKIE)
        try:
            if not raw:
                raise TokenError("sem cookie")
            refresh = RefreshToken(raw)
            if refresh.get("scope") != SCOPE:
                raise TokenError("escopo inválido")
            user = User.objects.get(id=refresh["user_id"], is_active=True, is_staff=True)
            refresh.blacklist()
            new = RefreshToken.for_user(user)
            new["scope"] = SCOPE
        except (TokenError, User.DoesNotExist, KeyError):
            response = Response({"error": {"code": "session_expired", "message": "Sessão expirada."}}, status=401)
            _clear_cookie(response)
            return response
        response = Response({"access": str(new.access_token), "user": admin_profile(user)})
        _set_cookie(response, str(new))
        return response


class AdminLogoutView(AuthView):
    def post(self, request):
        _check_origin(request)
        raw = request.COOKIES.get(COOKIE)
        if raw:
            try:
                RefreshToken(raw).blacklist()
            except TokenError:
                pass
        response = Response(status=status.HTTP_204_NO_CONTENT)
        _clear_cookie(response)
        return response


class AdminMeView(APIView):
    permission_classes = [IsAdminSession]

    def get(self, request):
        if not request.user.is_staff:
            raise PermissionDenied()
        return Response(admin_profile(request.user))
