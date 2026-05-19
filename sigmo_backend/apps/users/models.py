from django.contrib.auth.models import AbstractBaseUser, BaseUserManager
from django.db import models


class UserManager(BaseUserManager):
    def create_user(self, username, email, name, role, password=None):
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

    def create_superuser(self, username, email, name, password=None):
        user = self.create_user(
            username=username,
            email=email,
            name=name,
            role='superuser',
            password=password,
        )
        return user


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

    objects = UserManager()

    USERNAME_FIELD = 'username'
    REQUIRED_FIELDS = ['email', 'name']

    class Meta:
        db_table = '"USER"'

    def __str__(self):
        return f'{self.username} ({self.role})'