from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from drf_spectacular.utils import extend_schema

from apps.audit.services import log_action
from .models import PendingEntry, ENTRY_TYPE_CHOICES
from .serializers import PendingEntryWriteSerializer, PendingEntrySerializer, PendingEntryCancelSerializer
from .services import cancel_pending_entry, PendingEntryNotPendingError

VALID_ENTRY_TYPES = {choice[0] for choice in ENTRY_TYPE_CHOICES}


def can_manage_pending_entries(user):
    return user.role in ['superuser', 'auditor']


class PendingEntryListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(summary="Listar pendientes (anticipos y transferencias), con filtros opcionales.")
    def get(self, request):
        """Listar pendientes (anticipos y transferencias), con filtros opcionales.

        Sin restricción de rol: todos los roles pueden ver el listado
        (RN#1), solo crear/editar/cancelar está restringido a auditor/superuser."""
        entries = PendingEntry.objects.select_related(
            'client', 'payment_method'
        ).all().order_by('-date', '-id')

        client_id = request.query_params.get('client')
        entry_type = request.query_params.get('entry_type')
        entry_status = request.query_params.get('status')

        if client_id:
            entries = entries.filter(client_id=client_id)
        if entry_type:
            entries = entries.filter(entry_type=entry_type)
        if entry_status:
            entries = entries.filter(status=entry_status)

        serializer = PendingEntrySerializer(entries, many=True)
        return Response(serializer.data)

    @extend_schema(summary="Registrar un nuevo pendiente de anticipo o transferencia.")
    def post(self, request):
        """Registrar un nuevo pendiente de anticipo o transferencia (solo auditor/superuser)."""
        if not can_manage_pending_entries(request.user):
            log_action(request, 'access_denied', 'PendingEntry')
            return Response(
                {'error': 'No tiene permisos para registrar pendientes.'},
                status=status.HTTP_403_FORBIDDEN
            )

        entry_type = request.data.get('entry_type')
        if entry_type not in VALID_ENTRY_TYPES:
            return Response(
                {'error': f'entry_type debe ser uno de: {sorted(VALID_ENTRY_TYPES)}.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        serializer = PendingEntryWriteSerializer(data=request.data, context={'entry_type': entry_type})
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        entry = serializer.save(entry_type=entry_type, created_by=request.user)
        log_action(
            request, 'create', 'PendingEntry',
            object_id=entry.id,
            new_data=dict(PendingEntrySerializer(entry).data),
        )
        return Response(PendingEntrySerializer(entry).data, status=status.HTTP_201_CREATED)


class PendingEntryDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get_object(self, pk):
        try:
            return PendingEntry.objects.get(pk=pk)
        except PendingEntry.DoesNotExist:
            return None

    @extend_schema(summary="Consultar el detalle de un pendiente.")
    def get(self, request, pk):
        """Consultar el detalle de un pendiente."""
        obj = self.get_object(pk)
        if not obj:
            return Response({'error': 'Pendiente no encontrado.'}, status=status.HTTP_404_NOT_FOUND)
        return Response(PendingEntrySerializer(obj).data)

    @extend_schema(summary="Editar un pendiente en estado 'pendiente' (solo auditor/superuser).")
    def patch(self, request, pk):
        """Editar un pendiente en estado 'pendiente' (solo auditor/superuser)."""
        if not can_manage_pending_entries(request.user):
            log_action(request, 'access_denied', 'PendingEntry', object_id=pk)
            return Response(
                {'error': 'No tiene permisos para modificar pendientes.'},
                status=status.HTTP_403_FORBIDDEN
            )

        obj = self.get_object(pk)
        if not obj:
            return Response({'error': 'Pendiente no encontrado.'}, status=status.HTTP_404_NOT_FOUND)

        # RN#3: inmutable una vez ejecutado o cancelado.
        if obj.status != 'pending':
            return Response(
                {'error': 'Solo se puede editar un pendiente en estado "pendiente".'},
                status=status.HTTP_400_BAD_REQUEST
            )

        previous = dict(PendingEntrySerializer(obj).data)
        serializer = PendingEntryWriteSerializer(
            obj, data=request.data, partial=True, context={'entry_type': obj.entry_type}
        )
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        entry = serializer.save()
        fresh_data = PendingEntrySerializer(entry).data
        log_action(
            request, 'update', 'PendingEntry',
            object_id=entry.id,
            previous_data=previous,
            new_data=dict(fresh_data),
        )
        return Response(fresh_data)


class PendingEntryCancelView(APIView):
    """
    POST /pending-entries/<id>/cancel/ — cancela (soft-status) un pendiente
    en estado 'pending' (solo auditor/superuser). Ver cancel_pending_entry
    en services.py: nunca se borra la fila, siempre queda auditado con la
    justificación aportada.
    """
    permission_classes = [IsAuthenticated]

    @extend_schema(summary="Cancelar un pendiente en estado 'pendiente'.")
    def post(self, request, pk):
        """Cancelar un pendiente en estado 'pendiente' (solo auditor/superuser)."""
        if not can_manage_pending_entries(request.user):
            log_action(request, 'access_denied', 'PendingEntry', object_id=pk)
            return Response(
                {'error': 'No tiene permisos para cancelar pendientes.'},
                status=status.HTTP_403_FORBIDDEN
            )

        try:
            obj = PendingEntry.objects.get(pk=pk)
        except PendingEntry.DoesNotExist:
            return Response({'error': 'Pendiente no encontrado.'}, status=status.HTTP_404_NOT_FOUND)

        serializer = PendingEntryCancelSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        try:
            entry = cancel_pending_entry(
                obj, justification=serializer.validated_data['justification'], request=request
            )
        except PendingEntryNotPendingError:
            return Response(
                {'error': 'Solo se puede cancelar un pendiente en estado "pendiente".'},
                status=status.HTTP_400_BAD_REQUEST
            )

        return Response(PendingEntrySerializer(entry).data)
