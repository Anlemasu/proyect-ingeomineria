# apps/audit/views.py
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from drf_spectacular.utils import extend_schema

from .models import AuditLog
from .serializers import AuditLogSerializer


class AuditLogListView(APIView):
    """
    GET /api/audit/
    Solo Superusuario y Auditor pueden consultar (RF-05)
    Filtros: user, action, model_name, date_from, date_to
    """
    permission_classes = [IsAuthenticated]

    @extend_schema(summary="Consultar el log de auditoría del sistema.")
    def get(self, request):
        """Consultar el log de auditoría del sistema."""
        if request.user.role not in ['superuser', 'auditor']:
            return Response(
                {'error': 'No tiene permisos para consultar el log de auditoría.'},
                status=status.HTTP_403_FORBIDDEN
            )

        logs = AuditLog.objects.select_related('user').all()

        # Filtros (RF-05: filtrable por usuario, fecha y tipo de acción)
        user_id    = request.query_params.get('user')
        action     = request.query_params.get('action')
        model_name = request.query_params.get('model')
        date_from  = request.query_params.get('date_from')
        date_to    = request.query_params.get('date_to')

        if user_id:
            logs = logs.filter(user_id=user_id)
        if action:
            logs = logs.filter(action=action)
        if model_name:
            logs = logs.filter(model_name__icontains=model_name)
        if date_from:
            logs = logs.filter(timestamp__date__gte=date_from)
        if date_to:
            logs = logs.filter(timestamp__date__lte=date_to)

        serializer = AuditLogSerializer(logs, many=True)
        return Response(serializer.data)