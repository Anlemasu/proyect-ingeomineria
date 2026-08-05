from rest_framework import serializers
from .models import Expense

class ExpenseSerializer(serializers.ModelSerializer):
    class Meta:
        model = Expense
        fields = ['id', 'user', 'value', 'description', 'date', 'state']
        read_only_fields = ['id', 'user']  # user lo asigna la vista

    def validate_value(self, value):
        # RF-34: valor mayor a cero
        if value <= 0:
            raise serializers.ValidationError(
                'El valor del gasto debe ser mayor a cero.'
            )
        return value