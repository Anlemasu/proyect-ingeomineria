from rest_framework import serializers
from .models import DailySummary

class DailySummarySerializer(serializers.ModelSerializer):
    """
    Solo lectura en su totalidad: el cierre lo genera
    el service de cierre de caja (RF-41), no el frontend.
    """
    class Meta:
        model = DailySummary
        fields = [
            'id',
            'date',
            'total_trips',
            'total_volume',
            'income_cash',
            'income_transfer',
            'income_advance',
            'avg_trip_value',
            'total_expenses',
        ]
        read_only_fields = fields