from rest_framework import serializers
from .models import PendingEntry
from apps.clients.serializers import ClientSerializer
from apps.masters.serializers import PaymentMethodSerializer


class PendingEntryWriteSerializer(serializers.ModelSerializer):
    """
    Create/update de un pendiente. `entry_type` NO es un campo de este
    serializer: en creación lo decide la vista (PendingEntryListCreateView.post,
    a partir de request.data) y se pasa como kwarg extra a `.save()`, igual
    que `AdvanceListCreateView.post` hace con `trips_quantity`; en edición
    es inmutable (ver PendingEntryDetailView.patch), así que tampoco puede
    tocarse ahí. `self.context['entry_type']` lo inyecta la vista en ambos
    casos para que `validate()` pueda aplicar la regla de payment_method.
    """
    class Meta:
        model = PendingEntry
        fields = ['id', 'client', 'value', 'date', 'payment_method', 'observations']
        read_only_fields = ['id']

    def validate_value(self, value):
        if value <= 0:
            raise serializers.ValidationError('El valor debe ser mayor a cero.')
        return value

    def validate(self, data):
        entry_type = self.context.get('entry_type') or getattr(self.instance, 'entry_type', None)
        payment_method = data.get('payment_method', getattr(self.instance, 'payment_method', None))

        if entry_type == 'transfer' and not payment_method:
            raise serializers.ValidationError({
                'payment_method': 'El método de pago es obligatorio para una transferencia pendiente.'
            })
        if entry_type == 'advance' and payment_method:
            raise serializers.ValidationError({
                'payment_method': 'No debe indicar método de pago para un anticipo pendiente.'
            })
        return data


class PendingEntrySerializer(serializers.ModelSerializer):
    client_detail = ClientSerializer(source='client', read_only=True)
    payment_method_detail = PaymentMethodSerializer(source='payment_method', read_only=True)

    class Meta:
        model = PendingEntry
        fields = [
            'id', 'entry_type', 'status',
            'client', 'client_detail', 'value', 'date',
            'payment_method', 'payment_method_detail', 'observations',
            'executed_advance', 'executed_trip',
            'created_by', 'executed_by', 'executed_at',
            'cancelled_by', 'cancelled_at', 'cancellation_justification',
            'created_at', 'updated_at',
        ]
        read_only_fields = fields


class PendingEntryCancelSerializer(serializers.Serializer):
    """Payload de POST /pending-entries/<id>/cancel/ — no escribe sobre el
    modelo directamente, la escritura la hace cancel_pending_entry
    (services.py) dentro de su propia transacción con el lock del pendiente."""
    justification = serializers.CharField(allow_blank=False, trim_whitespace=True)

    def validate_justification(self, value):
        if not value.strip():
            raise serializers.ValidationError('La justificación es obligatoria para cancelar un pendiente.')
        return value.strip()
