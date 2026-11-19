from rest_framework import permissions

from .verification import EmailUnverified


class IsAuthenticatedAndVerified(permissions.IsAuthenticated):
    """Permissão padrão da API: exige login e e-mail confirmado.

    Views que o usuário precisa antes de confirmar (perfil, verificação, LGPD) declaram
    `allow_unverified_email = True`.
    """

    def has_permission(self, request, view):
        if not super().has_permission(request, view):
            return False
        if request.user.email_verified or getattr(view, "allow_unverified_email", False):
            return True
        raise EmailUnverified()
