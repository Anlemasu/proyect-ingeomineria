from django.contrib.auth import password_validation
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers
from .models import User


def _run_django_password_validators(value, *, user=None, field='password'):
    """
    8A.2 — AUTH_PASSWORD_VALIDATORS (settings.py) estaba configurado pero
    nunca se invocaba: ningún flujo de creación/cambio de contraseña
    llamaba a Django para aplicarlo, así que las reglas ahí declaradas
    (longitud mínima, no similar al usuario, no una contraseña común, no
    solo numérica) no tenían ningún efecto real.

    `validate_password` de Django lanza su propio ValidationError (con
    `.messages`, una lista de strings) — no el de DRF. Se relanza como
    serializers.ValidationError para que DRF lo agregue automáticamente a
    serializer.errors, igual que cualquier otro error de validate_*, sin
    tener que tocar ninguna vista.
    """
    try:
        password_validation.validate_password(value, user=user)
    except DjangoValidationError as e:
        raise serializers.ValidationError({field: list(e.messages)})


# ── Lectura ──────────────────────────────────────────────────────────────────
class UserReadSerializer(serializers.ModelSerializer):
    """
    Solo para devolver datos del usuario en respuestas GET.
    NUNCA expone el password, ni siquiera el hash.
    """
    role_display = serializers.CharField(
        source='get_role_display',  # convierte 'cashier' → 'Operador de Caja'
        read_only=True
    )

    class Meta:
        model = User
        fields = [
            'id',
            'name',
            'email',
            'username',
            'role',
            'role_display',
            'state',
        ]


# ── Creación (RF-01) ──────────────────────────────────────────────────────────
class UserCreateSerializer(serializers.ModelSerializer):
    """
    Para que el Superusuario cree nuevos usuarios (RF-01).
    Recibe password en texto plano, Django lo hashea con set_password().
    """
    password = serializers.CharField(
        write_only=True,   # sale en el request pero NUNCA en la respuesta
        min_length=8,
        style={'input_type': 'password'}
    )

    class Meta:
        model = User
        fields = ['name', 'email', 'username', 'password', 'role']

    def validate_password(self, value):
        # RF-06B: mínimo 8 caracteres, al menos una mayúscula y un número
        if not any(c.isupper() for c in value):
            raise serializers.ValidationError(
                'La contraseña debe contener al menos una letra mayúscula.'
            )
        if not any(c.isdigit() for c in value):
            raise serializers.ValidationError(
                'La contraseña debe contener al menos un número.'
            )
        return value

    def validate_role(self, value):
        # RF-02: solo roles predefinidos (los choices ya lo garantizan,
        # pero lo hacemos explícito para el mensaje de error)
        valid_roles = [r[0] for r in User.ROLES]
        if value not in valid_roles:
            raise serializers.ValidationError(
                f'Rol inválido. Opciones: {valid_roles}'
            )
        return value

    def validate(self, data):
        # 8A.2: a esta altura ya corrieron los validate_<campo> (incluido
        # validate_password, arriba), así que 'username'/'email'/'name' ya
        # están en `data`. Todavía no existe un User guardado — se arma uno
        # sin persistir solo para que UserAttributeSimilarityValidator
        # pueda comparar la contraseña contra el username/email reales
        # (sin este objeto, ese validador específico no tendría con qué
        # comparar y sería un no-op).
        candidate = User(
            username=data.get('username', ''),
            email=data.get('email', ''),
            name=data.get('name', ''),
        )
        _run_django_password_validators(data['password'], user=candidate, field='password')
        return data

    def create(self, validated_data):
        return User.objects.create_user(
            username=validated_data['username'],
            email=validated_data['email'],
            name=validated_data['name'],
            role=validated_data['role'],
            password=validated_data['password'],
    )


# ── Cambio de contraseña (RF-06B) ─────────────────────────────────────────────
class ChangePasswordSerializer(serializers.Serializer):
    """
    Serializer sin modelo porque no guarda un objeto completo,
    solo valida y procesa el cambio de contraseña.
    """
    current_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True, min_length=8)
    confirm_password = serializers.CharField(write_only=True)

    def validate_new_password(self, value):
        if not any(c.isupper() for c in value):
            raise serializers.ValidationError(
                'La nueva contraseña debe tener al menos una mayúscula.'
            )
        if not any(c.isdigit() for c in value):
            raise serializers.ValidationError(
                'La nueva contraseña debe tener al menos un número.'
            )
        # 8A.2: usuario real disponible vía el contexto que la vista ya
        # pasa (`context={'request': request}`) — permite que
        # UserAttributeSimilarityValidator compare contra el username/email
        # reales, no solo las reglas manuales de arriba.
        user = self.context['request'].user
        _run_django_password_validators(value, user=user, field='new_password')
        return value

    def validate(self, data):
        # Verificar que nueva y confirmación coinciden
        if data['new_password'] != data['confirm_password']:
            raise serializers.ValidationError(
                {'confirm_password': 'Las contraseñas no coinciden.'}
            )
        # Verificar que la contraseña actual es correcta
        # self.context['request'] lo pasa la vista automáticamente
        user = self.context['request'].user
        if not user.check_password(data['current_password']):
            raise serializers.ValidationError(
                {'current_password': 'La contraseña actual es incorrecta.'}
            )
        return data


# ── Reset de contraseña por el Superusuario (RF-01) ───────────────────────────
class ResetPasswordByAdminSerializer(serializers.Serializer):
    """Permite al superusuario establecer una contraseña temporal a cualquier usuario."""
    new_password = serializers.CharField(write_only=True, min_length=8)

    def validate_new_password(self, value):
        if not any(c.isupper() for c in value):
            raise serializers.ValidationError(
                'La contraseña debe contener al menos una letra mayúscula.'
            )
        if not any(c.isdigit() for c in value):
            raise serializers.ValidationError(
                'La contraseña debe contener al menos un número.'
            )
        # 8A.2: la vista (ResetPasswordAdminView) pasa target_user en el
        # contexto — permite comparar contra el username/email del usuario
        # que efectivamente va a recibir esta contraseña, no el del
        # superusuario que hace el reset.
        target_user = self.context.get('target_user')
        _run_django_password_validators(value, user=target_user, field='new_password')
        return value