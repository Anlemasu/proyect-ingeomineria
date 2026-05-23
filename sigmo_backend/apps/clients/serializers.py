from rest_framework import serializers
from .models import Client
from apps.users.serializers import UserReadSerializer


class ClientSerializer(serializers.ModelSerializer):
    """
    Lectura: incluye datos del usuario que creó el cliente.
    Escritura: el frontend solo manda los datos del cliente;
    el campo 'user' se asigna automáticamente en la vista.
    """
    created_by = UserReadSerializer(source='user', read_only=True)

    class Meta:
        model = Client
        fields = [
            'id',
            'nit',
            'name',
            'abrev_name',
            'address',
            'phone',
            'city',
            'facturation_name',
            'email',
            'validate_certification',
            'state',
            'created_by',   # solo lectura, viene de 'user'
        ]
        read_only_fields = ['id', 'created_by']
        # 'user' no está en fields intencionalmente:
        # se asigna en la vista con perform_create, no lo manda el frontend
        extra_kwargs = {
            'nit': {'validators': []}
        }

    def validate_nit(self, value):
        normalized = value.replace(' ', '').replace('-', '')

        qs = Client.objects.filter(nit=normalized)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)

        if qs.exists():
            existing = qs.first()
            existing_name = existing.name if existing else ''  # type: ignore
            raise serializers.ValidationError(
                f"Ya existe un cliente con este NIT: '{existing_name}'."
            )
        return normalized

    def validate_phone(self, value):
        if value <= 0:
            raise serializers.ValidationError(
                'El teléfono debe ser un número positivo.'
            )
        return value

    def validate_state(self, value):
        # RF-09: no eliminación física, solo desactivación.
        # La validación de "no eliminar" la maneja el ViewSet (no expone DELETE).
        # Aquí simplemente dejamos pasar el valor booleano.
        return value