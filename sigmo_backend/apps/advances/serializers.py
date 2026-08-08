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


class AdvanceValueCorrectionSerializer(serializers.Serializer):
    """
    9C — payload de POST /advances/<id>/correct-value/. No es un
    ModelSerializer: no escribe directamente sobre Advance, solo valida la
    entrada; la escritura real (movimiento de ajuste + Advance.value) la
    hace correct_active_advance_value (advances/services.py) dentro de su
    propia transacción con los locks correspondientes.
    """
    correct_value = serializers.DecimalField(max_digits=15, decimal_places=2)
    justification = serializers.CharField(allow_blank=False, trim_whitespace=True)

    def validate_correct_value(self, value):
        # Mismo criterio que Advance.value al crear (RF-29): un anticipo
        # corregido a un valor cero o negativo no tiene sentido de negocio.
        if value <= 0:
            raise serializers.ValidationError(
                'El valor corregido debe ser mayor a cero.'
            )
        return value

    def validate_justification(self, value):
        if not value.strip():
            raise serializers.ValidationError(
                'La justificación es obligatoria para corregir el valor de un anticipo.'
            )
        return value.strip()


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

    def validate(self, data):
        """
        9.3 — `client` y `value` no deben poder editarse una vez que el
        anticipo ya tiene movimientos (AdvanceMovement) registrados:
        - cambiar `client` reasigna el "dueño" del anticipo sin actualizar
          los viajes que ya apuntan a él como su anticipo (quedarían
          apuntando a un anticipo que ahora es de otro cliente);
        - editar `value` no tiene ningún efecto real sobre el saldo, que
          siempre se calcula en vivo desde la suma de movimientos (ver
          get_available_balance) — daría una falsa sensación de que el
          saldo cambió cuando en realidad no.

        Fix conservador (sin justificación de negocio confirmada para
        permitirlo, ver resumen de la Fase 9): se bloquea directamente en
        vez de intentar "arreglar" los viajes/movimientos asociados. Solo
        aplica en edición (self.instance no es None) — en creación
        (AdvanceListCreateView.post) el anticipo todavía no tiene ningún
        AdvanceMovement en este punto, así que nunca se bloquea ahí.

        `data` solo trae las claves de los campos presentes en el request
        (partial=True), así que `'client' in data` / `'value' in data`
        distinguen "el caller intentó tocar este campo" de "no lo mandó".
        """
        if self.instance is not None and self.instance.pk is not None:
            locked_fields = {'client', 'value'} & set(data.keys())
            if locked_fields and AdvanceMovement.objects.filter(advance=self.instance).exists():
                raise serializers.ValidationError({
                    field: (
                        'No se puede editar este campo: el anticipo ya tiene '
                        'movimientos registrados.'
                    )
                    for field in locked_fields
                })
        return data

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