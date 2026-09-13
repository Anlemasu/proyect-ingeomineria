from rest_framework import serializers
from .models import PhysicalCountEntry, PhysicalCountClosure


class PhysicalCountEntrySerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source='user.username', read_only=True)

    class Meta:
        model = PhysicalCountEntry
        fields = ['id', 'advance', 'date', 'count', 'user', 'user_name', 'created_at', 'justification']
        read_only_fields = fields


class PhysicalCountClosureSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source='user.username', read_only=True)

    class Meta:
        model = PhysicalCountClosure
        fields = ['id', 'advance', 'action', 'user', 'user_name', 'created_at', 'justification']
        read_only_fields = fields


class RegisterEntrySerializer(serializers.Serializer):
    """
    Payload de POST /physical-reports/<id>/entries/. La obligatoriedad de
    `justification` (cuando ya existe un conteo previo para esa fecha) se
    valida en services.register_entry, no aquí: este serializer solo valida
    la forma del dato de entrada.
    """
    date = serializers.DateField()
    count = serializers.IntegerField(min_value=0)
    justification = serializers.CharField(required=False, allow_blank=True, trim_whitespace=True)


class SetQuotaSerializer(serializers.Serializer):
    quantity = serializers.IntegerField(min_value=1)


class BulkEntryItemSerializer(serializers.Serializer):
    advance = serializers.IntegerField()
    count = serializers.IntegerField(min_value=0)


class BulkRegisterEntriesSerializer(serializers.Serializer):
    """
    Payload de POST /physical-reports/bulk-entries/ — el botón único
    "Guardar todos" de la tabla principal. Una sola fecha para todos los
    anticipos incluidos (nunca lleva `justification`: este camino solo
    existe para el registro rápido dentro de la ventana de ajuste — ver
    ENTRY_ADJUSTMENT_WINDOW_MINUTES; pasada la ventana, cada anticipo se
    corrige individualmente desde el detalle).
    """
    date = serializers.DateField()
    entries = BulkEntryItemSerializer(many=True)

    def validate_entries(self, value):
        if not value:
            raise serializers.ValidationError('Debe incluir al menos un conteo para guardar.')
        return value


class ReopenSerializer(serializers.Serializer):
    justification = serializers.CharField(allow_blank=False, trim_whitespace=True)

    def validate_justification(self, value):
        if not value.strip():
            raise serializers.ValidationError('La justificación es obligatoria para reabrir el registro.')
        return value.strip()
