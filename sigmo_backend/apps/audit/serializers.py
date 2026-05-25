from rest_framework import serializers
from .models import AuditLog


class AuditLogSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(
        source='user.username', read_only=True, default='Sistema'
    )
    action_display = serializers.CharField(
        source='get_action_display', read_only=True
    )

    class Meta:
        model = AuditLog
        fields = [
            'id',
            'user',
            'user_name',
            'action',
            'action_display',
            'model_name',
            'object_id',
            'previous_data',
            'new_data',
            'ip_address',
            'justification',
            'timestamp',
        ]
        # El log es completamente de solo lectura (RF-05)
        read_only_fields = fields