import uuid

from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from django.db import models
from django.utils import timezone

from core.documents import validate_cpf


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create(self, email, password, **extra):
        if not email:
            raise ValueError("E-mail é obrigatório.")
        user = self.model(email=self.normalize_email(email).lower(), **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra):
        extra.setdefault("is_staff", False)
        extra.setdefault("is_superuser", False)
        return self._create(email, password, **extra)

    def create_superuser(self, email, password=None, **extra):
        extra.update(is_staff=True, is_superuser=True, email_verified=True)
        return self._create(email, password, **extra)


class User(AbstractBaseUser, PermissionsMixin):
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    email = models.EmailField("e-mail", unique=True)
    full_name = models.CharField("nome completo", max_length=150)
    cpf = models.CharField("CPF", max_length=11, blank=True, validators=[validate_cpf])
    phone = models.CharField("telefone", max_length=20, blank=True)
    email_verified = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    date_joined = models.DateTimeField(default=timezone.now)
    password_changed_at = models.DateTimeField(null=True, blank=True)

    # LGPD: prova do aceite (versão vigente dos documentos e momento)
    terms_accepted_at = models.DateTimeField(null=True, blank=True)
    legal_version = models.CharField(max_length=20, blank=True)
    marketing_opt_in = models.BooleanField("aceita comunicações comerciais", default=False)
    anonymized_at = models.DateTimeField(null=True, blank=True)

    # 2FA (TOTP). O segredo é cifrado pelo cofre.
    totp_secret_encrypted = models.BinaryField(null=True, blank=True, editable=False)
    totp_enabled = models.BooleanField(default=False)
    recovery_codes = models.JSONField(default=list, blank=True, editable=False)  # hashes

    objects = UserManager()

    USERNAME_FIELD = "email"
    EMAIL_FIELD = "email"
    REQUIRED_FIELDS = ["full_name"]

    class Meta:
        verbose_name = "usuário"
        verbose_name_plural = "usuários"

    def __str__(self):
        return self.email

    def set_password(self, raw_password):
        super().set_password(raw_password)
        self.password_changed_at = timezone.now()
