from rest_framework import serializers
from .models import Trip, Transfer
from apps.masters.serializers import (
    VehicleSerializer, MaterialTypeSerializer,
    PaymentMethodSerializer, OriginSiteSerializer
)
from apps.clients.serializers import ClientSerializer


class TransferSerializer(serializers.ModelSerializer):
    class Meta:
        model = Transfer
        fields = ['id', 'trip', 'number']
        read_only_fields = ['id']


# ── Lectura: GET con todos los objetos anidados ───────────────────────────────
class TripReadSerializer(serializers.ModelSerializer):
    """
    Para respuestas GET: devuelve objetos completos para que
    el frontend pueda mostrar nombres, capacidades, etc.
    sin hacer requests adicionales.
    """
    client_detail = ClientSerializer(source='client', read_only=True)
    payment_detail = PaymentMethodSerializer(source='payment', read_only=True)
    vehicle_detail = VehicleSerializer(source='vehicle', read_only=True)
    material_type_detail = MaterialTypeSerializer(source='material_type', read_only=True)
    origin_site_detail = OriginSiteSerializer(source='origin_site', read_only=True)
    transfers = TransferSerializer(
        source='transfer_set', many=True, read_only=True
    )

    class Meta:
        model = Trip
        fields = [
            'id',
            'voucher_num',
            'date',
            'date_register',
            'value',
            'extern_voucher_num',
            'invoice_pos',
            'certification_state',
            'certification_num',
            'state',
            # Relaciones como objetos completos
            'client_detail',
            'payment_detail',
            'vehicle_detail',
            'material_type_detail',
            'origin_site_detail',
            'advance',
            'invoice',
            'summary',
            'transfers',
        ]


# ── Escritura: POST/PUT con IDs y validaciones de negocio ────────────────────
class TripWriteSerializer(serializers.ModelSerializer):
    """
    Para crear y editar viajes (RF-26, RF-28).
    Solo recibe IDs de relaciones y aplica todas las
    validaciones de negocio antes de llegar al service layer.
    """

    class Meta:
        model = Trip
        fields = [
            'payment',
            'origin_site',
            'material_type',
            'client',
            'vehicle',
            'advance',          # nullable, solo si pago es anticipo
            'voucher_num',
            'value',
            'extern_voucher_num',
            'date',
            'state',
        ]

    def validate_value(self, value):
        # RF-28: no acepta valores negativos ni cero
        if value <= 0:
            raise serializers.ValidationError(
                'El valor del servicio debe ser mayor a cero.'
            )
        return value

    def validate(self, data):
        payment = data.get('payment')
        advance = data.get('advance')

        # RF-31B: si el medio de pago es anticipo, debe venir el anticipo
        if payment and payment.is_advance:
            if not advance:
                raise serializers.ValidationError(
                    'Debe seleccionar un anticipo cuando el medio de pago es anticipo.'
                )
            # La validación del saldo suficiente va en el service (paso 2),
            # porque requiere lógica transaccional con bloqueo de fila.
            # Aquí solo verificamos que el anticipo pertenezca al cliente
            client = data.get('client')
            if advance and client and advance.client_id != client.id:
                raise serializers.ValidationError(
                    'El anticipo seleccionado no pertenece al cliente indicado.'
                )

        # Si el pago NO es anticipo, el campo advance debe estar vacío
        if payment and not payment.is_advance and advance:
            raise serializers.ValidationError(
                'No debe indicar un anticipo para este medio de pago.'
            )

        return data