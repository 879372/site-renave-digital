from django.urls import path

from . import views

urlpatterns = [
    path("register", views.RegisterView.as_view()),
    path("login", views.LoginView.as_view()),
    path("login/mfa", views.MfaLoginView.as_view()),
    path("refresh", views.RefreshView.as_view()),
    path("logout", views.LogoutView.as_view()),
    path("me", views.MeView.as_view()),
    path("email/send", views.EmailCodeSendView.as_view()),
    path("email/verify", views.EmailCodeVerifyView.as_view()),
    path("password/change", views.PasswordChangeView.as_view()),
    path("password/reset", views.PasswordResetView.as_view()),
    path("password/reset/confirm", views.PasswordResetConfirmView.as_view()),
    path("mfa/setup", views.MfaSetupView.as_view()),
    path("mfa/enable", views.MfaEnableView.as_view()),
    path("mfa/disable", views.MfaDisableView.as_view()),
    path("legal/accept", views.AcceptLegalView.as_view()),
    path("me/export", views.DataExportView.as_view()),
    path("me/delete", views.AccountDeleteView.as_view()),
]
