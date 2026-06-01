from rest_framework import serializers
from .models import Trip
from apps.masters.serializers import (
    VehicleSerializer, MaterialTypeSerializer,
    PaymentMethodSerializer, OriginSiteSerializer
)
from apps.clients.serializers import ClientSerializer


# ── Lectura: GET con todos los objetos anidados ───────────────────────────────
class TripReadSerializer(serializers.ModelSerializer):
    client_detail = ClientSerializer(source='client', read_only=True)
    payment_detail = PaymentMethodSerializer(source='payment', read_only=True)
    vehicle_detail = VehicleSerializer(source='vehicle', read_only=True)
    material_type_detail = MaterialTypeSerializer(source='material_type', read_only=True)
    origin_site_detail = OriginSiteSerializer(source='origin_site', read_only=True)

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
            'client_detail',
            'payment_detail',
            'vehicle_detail',
            'material_type_detail',
            'origin_site_detail',
            'advance',
            'invoice',
            'summary',
        ]


# ── Escritura: POST/PUT con IDs y validaciones de negocio ────────────────────
class TripWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Trip
        fields = [
            'payment',
            'origin_site',
            'material_type',
            'client',
            'vehicle',
            'advance',
            'voucher_num',
            'value',
            'extern_voucher_num',
            'date',
            'state',
        ]

    def validate_value(self, value):
        if value <= 0:
            raise serializers.ValidationError(
                'El valor del servicio debe ser mayor a cero.'
            )
        return value

    def validate(self, data):
        payment = data.get('payment')
        advance = data.get('advance')

        if payment and payment.is_advance:
            if not advance:
                raise serializers.ValidationError(
                    'Debe seleccionar un anticipo cuando el medio de pago es anticipo.'
                )
            client = data.get('client')
            if advance and client and advance.client_id != client.id:
                raise serializers.ValidationError(
                    'El anticipo seleccionado no pertenece al cliente indicado.'
                )

        if payment and not payment.is_advance and advance:
            raise serializers.ValidationError(
                'No debe indicar un anticipo para este medio de pago.'
            )

        return data