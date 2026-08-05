from rest_framework import serializers
from .models import DailySummary, DailySummaryPayment


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
        ]
        read_only_fields = fields