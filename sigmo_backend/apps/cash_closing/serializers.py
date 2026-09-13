from rest_framework import serializers
from .models import DailySummary, DailySummaryPayment
from .aggregates import build_trips_by_client


class DailySummaryPaymentSerializer(serializers.ModelSerializer):
    payment_method_name = serializers.CharField(
        source='payment_method.name', read_only=True
    )

    class Meta:
        model = DailySummaryPayment
        fields = ['payment_method', 'payment_method_name', 'total']


class DailySummarySerializer(serializers.ModelSerializer):
    payment_details = DailySummaryPaymentSerializer(
        many=True, read_only=True
    )
    # Desglose "viajes por cliente" calculado EN VIVO desde los TRIP activos
    # vinculados a este cierre (Trip.summary) — no se persiste. Mismo formato
    # que 'trips_by_client' del resumen del día en curso (ver aggregates.py).
    client_details = serializers.SerializerMethodField()

    class Meta:
        model = DailySummary
        fields = [
            'id',
            'date',
            'state',
            'total_trips',
            'total_volume',
            'avg_trip_value',
            'total_expenses',
            'payment_details',
            'client_details',
        ]
        read_only_fields = fields

    def get_client_details(self, obj):
        # En listados (DailySummaryListView) la vista precalcula el desglose
        # de todos los cierres en una sola consulta y lo pasa por context,
        # para no hacer un query por fila (N+1). Si no viene en context
        # (serialización de un solo cierre: execute_close, revert, resync),
        # se calcula al vuelo — un único query.
        precomputed = self.context.get('client_details_by_summary')
        if precomputed is not None:
            return precomputed.get(obj.id, [])
        from apps.trips.models import Trip  # import diferido: evita ciclo con trips.models
        return build_trips_by_client(Trip.objects.filter(summary=obj, state=True))