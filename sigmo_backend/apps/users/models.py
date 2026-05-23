from django.contrib.auth.models import AbstractBaseUser, BaseUserManager
from django.db import models
from typing import ClassVar


class UserManager(BaseUserManager['User']):
    def create_user(self, username: str, email: str, name: str, role: str, password: str | None = None) -> 'User':
        if not username:
            raise ValueError('El usuario debe tener un nombre de usuario')
        if not email:
            raise ValueError('El usuario debe tener un correo')

        user = self.model(
            username=username,
            email=self.normalize_email(email),
            name=name,
            role=role,
        )
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, username: str, email: str, name: str, password: str | None = None) -> 'User':
        return self.create_user(
            username=username,
            email=email,
            name=name,
            role='superuser',
            password=password,
        )


class User(AbstractBaseUser):
    ROLES = [
        ('superuser', 'Superusuario'),
        ('commercial_admin', 'Administrador Comercial'),
        ('cashier', 'Operador de Caja'),
        ('accountant', 'Contador'),
        ('auditor', 'Auditor'),
    ]

    name = models.CharField(max_length=30)
    email = models.EmailField(max_length=30, unique=True)
    username = models.CharField(max_length=30, unique=True)
    role = models.CharField(max_length=30, choices=ROLES)
    state = models.BooleanField(default=True)

    # ← ClassVar le dice a Pylance el tipo exacto del manager
    objects: ClassVar[UserManager] = UserManager()

    USERNAME_FIELD = 'username'
    REQUIRED_FIELDS = ['email', 'name']

    class Meta:
        db_table = '"USER"'

    def __str__(self) -> str:
        return f'{self.username} ({self.role})'