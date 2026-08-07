from decimal import Decimal

from rest_framework import serializers
from .models import Advance, AdvanceMovement
from apps.clients.serializers import ClientSerializer
from .services import get_available_balance


class AdvanceMovementSerializer(serializers.ModelSerializer):
    class Meta:
        model = AdvanceMovement
        fields = [
            'id',
            'advance',
            'trip',
            'type_movement',
            'amount',
            'trips_quantity',
            'date',
            'description',
        ]
        read_only_fields = ['id']

    def validate_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError(
                'El monto del movimiento debe ser mayor a cero.'
            )
        return value


class AdvanceSerializer(serializers.ModelSerializer):
    # Datos del cliente anidados para lectura
    client_detail = ClientSerializer(source='client', read_only=True)

    # Movimientos anidados para el historial (RF-32)
    movements = AdvanceMovementSerializer(
        source='advancemovement_set',
        many=True,
        read_only=True
    )

    # Campo calculado: no existe en la DB, se computa al vuelo (RF-30)
    available_balance = serializers.SerializerMethodField()

    class Meta:
        model = Advance
        fields = [
            'id',
            'client',           # ID para escritura
            'client_detail',    # objeto para lectura
            'user',             # asignado por la vista, read_only
            'value',
            'transfer_num',
            'date',
            'proforma_number',
            'observations',
            'available_balance',
            'movements',
        ]
        read_only_fields = ['id', 'user', 'available_balance', 'movements']

    def validate_value(self, value):
        # RF-29: el valor del anticipo debe ser mayor a cero
        if value <= 0:
            raise serializers.ValidationError(
                'El valor del anticipo debe ser mayor a cero.'
            )
        return value

    def validate_transfer_num(self, value):
        # RF-29: número de consignación es obligatorio y debe ser positivo
        if value <= 0:
            raise serializers.ValidationError(
                'El número de consignación no es válido.'
            )
        return value

    def get_available_balance(self, obj):
        """
        RF-30: saldo = suma de ingresos - suma de egresos de los movimientos.
        SerializerMethodField llama este método automáticamente
        y su resultado va en el JSON como 'available_balance'.

        FASE 6.2: si el queryset vino de annotate_available_balance() (ver
        AdvanceListCreateView.get), usa esos totales ya calculados en la
        misma consulta en vez de volver a golpear la base de datos por cada
        anticipo — mismo resultado numérico, sin las queries N+1.
        """
        ingresos = getattr(obj, '_annotated_ingresos', None)
        egresos = getattr(obj, '_annotated_egresos', None)
        if ingresos is not None or egresos is not None:
            return float((ingresos or Decimal('0')) - (egresos or Decimal('0')))
        return float(get_available_balance(obj))