from datetime import date as date_cls

from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from drf_spectacular.utils import extend_schema

from apps.advances.models import Advance
from apps.clients.serializers import ClientSerializer
from apps.trips.models import Trip
from .serializers import (
    RegisterEntrySerializer,
    SetQuotaSerializer,
    ReopenSerializer,
    BulkRegisterEntriesSerializer,
    PhysicalCountEntrySerializer,
    PhysicalCountClosureSerializer,
)
from .services import (
    get_open_physical_reports,
    get_closed_physical_reports,
    get_latest_entries_by_date,
    get_cumulative_entered,
    is_closed,
    is_entry_editable,
    get_last_closure_action,
    register_entry,
    set_expected_quantity,
    close_advance,
    undo_close_advance,
    reopen_advance,
    ClosedTrackingError,
    JustificationRequiredError,
    QuotaAlreadySetError,
    NotClosedError,
    UndoWindowExpiredError,
)


def can_manage_physical_reports(user):
    return user.role in ['superuser', 'cashier', 'commercial_admin']


def _parse_date_param(request):
    """
    Lee `?date=YYYY-MM-DD` de la query string. Devuelve (fecha_o_None, error):
    `error` es una Response 400 lista para devolver si el formato es
    inválido, o None si todo está bien (incluyendo cuando no se mandó fecha).
    """
    raw = request.query_params.get('date')
    if not raw:
        return None, None
    try:
        return date_cls.fromisoformat(raw), None
    except ValueError:
        return None, Response(
            {'error': 'Parámetro date inválido: use el formato YYYY-MM-DD.'},
            status=status.HTTP_400_BAD_REQUEST,
        )


def _serialize_summary(row: dict) -> dict:
    advance = row['advance']
    data = {
        'advance': advance.id,
        'client_detail': ClientSerializer(advance.client).data,
        'date': advance.date,
        'expected_trips_quantity': row['expected_trips_quantity'],
        'cumulative_entered': row['cumulative_entered'],
        'remaining': row['remaining'],
    }
    if 'day_count' in row:
        data['day_count'] = row['day_count']
        data['day_editable'] = row['day_editable']
    return data


class PhysicalReportListView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(summary="Listar anticipos con conteo físico abierto y viajes pendientes por confirmar.")
    def get(self, request):
        as_of_date, error = _parse_date_param(request)
        if error:
            return error
        rows = get_open_physical_reports(as_of_date=as_of_date)
        return Response([_serialize_summary(r) for r in rows])


class PhysicalReportDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get_object(self, pk):
        try:
            return Advance.objects.select_related('client').get(pk=pk)
        except Advance.DoesNotExist:
            return None

    @extend_schema(summary="Detalle del conteo físico de un anticipo, opcionalmente de una fecha puntual.")
    def get(self, request, pk):
        advance = self.get_object(pk)
        if not advance:
            return Response({'error': 'Anticipo no encontrado.'}, status=status.HTTP_404_NOT_FOUND)

        entries_by_date = get_latest_entries_by_date(advance)
        cumulative = get_cumulative_entered(advance)
        expected = advance.expected_trips_quantity
        remaining = (expected - cumulative) if expected is not None else None
        closed = is_closed(advance)
        last_closure = get_last_closure_action(advance)

        data = {
            'advance': advance.id,
            'client_detail': ClientSerializer(advance.client).data,
            'date': advance.date,
            'expected_trips_quantity': expected,
            'cumulative_entered': cumulative,
            'remaining': remaining,
            'closed': closed,
            'last_closure': PhysicalCountClosureSerializer(last_closure).data if last_closure else None,
        }

        selected_date = request.query_params.get('date')
        if selected_date:
            day_entries = list(
                advance.physicalcountentry_set.filter(date=selected_date).order_by('id')  # type: ignore[attr-defined]
            )
            current_entry = day_entries[-1] if day_entries else None
            system_count = Trip.objects.filter(
                advance=advance, date=selected_date, state=True,
            ).count()
            data['day_detail'] = {
                'date': selected_date,
                'physical_count': current_entry.count if current_entry else None,
                'system_count': system_count,
                'difference': (
                    (current_entry.count - system_count) if current_entry else None
                ),
                'history': PhysicalCountEntrySerializer(day_entries, many=True).data,
                # Dentro de la ventana de ajuste rápido (o si no hay ningún
                # conteo todavía): corregirlo aquí mismo no exige
                # justificación. Ver ENTRY_ADJUSTMENT_WINDOW_MINUTES.
                'editable': is_entry_editable(current_entry),
            }

        return Response(data)


class PhysicalReportEntryView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(summary="Registrar (o corregir) el conteo físico de un día para un anticipo.")
    def post(self, request, pk):
        if not can_manage_physical_reports(request.user):
            return Response(
                {'error': 'No tiene permisos para registrar el conteo físico.'},
                status=status.HTTP_403_FORBIDDEN,
            )
        try:
            advance = Advance.objects.get(pk=pk)
        except Advance.DoesNotExist:
            return Response({'error': 'Anticipo no encontrado.'}, status=status.HTTP_404_NOT_FOUND)

        serializer = RegisterEntrySerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        try:
            entry = register_entry(
                advance,
                date=serializer.validated_data['date'],
                count=serializer.validated_data['count'],
                user=request.user,
                justification=serializer.validated_data.get('justification'),
            )
        except ClosedTrackingError:
            return Response(
                {'error': 'El conteo físico de este anticipo está cerrado. Reábralo antes de agregar conteos.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except JustificationRequiredError:
            return Response(
                {'error': 'Ya existe un conteo para esta fecha: la justificación es obligatoria para corregirlo.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(PhysicalCountEntrySerializer(entry).data, status=status.HTTP_201_CREATED)


class PhysicalReportQuotaView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(summary="Definir el cupo esperado de viajes de un anticipo que aún no lo tiene.")
    def post(self, request, pk):
        if not can_manage_physical_reports(request.user):
            return Response(
                {'error': 'No tiene permisos para definir el cupo esperado.'},
                status=status.HTTP_403_FORBIDDEN,
            )
        try:
            advance = Advance.objects.get(pk=pk)
        except Advance.DoesNotExist:
            return Response({'error': 'Anticipo no encontrado.'}, status=status.HTTP_404_NOT_FOUND)

        serializer = SetQuotaSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        try:
            advance = set_expected_quantity(advance, serializer.validated_data['quantity'], request.user)
        except QuotaAlreadySetError:
            return Response(
                {'error': 'Este anticipo ya tiene un cupo esperado definido.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response({'advance': advance.id, 'expected_trips_quantity': advance.expected_trips_quantity})


class PhysicalReportCloseView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(summary="Finalizar el conteo físico de un anticipo.")
    def post(self, request, pk):
        if not can_manage_physical_reports(request.user):
            return Response({'error': 'No tiene permisos para finalizar este registro.'}, status=status.HTTP_403_FORBIDDEN)
        try:
            advance = Advance.objects.get(pk=pk)
        except Advance.DoesNotExist:
            return Response({'error': 'Anticipo no encontrado.'}, status=status.HTTP_404_NOT_FOUND)

        try:
            closure = close_advance(advance, request.user)
        except ClosedTrackingError:
            return Response({'error': 'Este anticipo ya está cerrado.'}, status=status.HTTP_400_BAD_REQUEST)

        return Response(PhysicalCountClosureSerializer(closure).data, status=status.HTTP_201_CREATED)


class PhysicalReportUndoCloseView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(summary="Deshacer inmediatamente el cierre de un anticipo (sin justificación).")
    def post(self, request, pk):
        if not can_manage_physical_reports(request.user):
            return Response({'error': 'No tiene permisos para deshacer este cierre.'}, status=status.HTTP_403_FORBIDDEN)
        try:
            advance = Advance.objects.get(pk=pk)
        except Advance.DoesNotExist:
            return Response({'error': 'Anticipo no encontrado.'}, status=status.HTTP_404_NOT_FOUND)

        try:
            closure = undo_close_advance(advance, request.user)
        except NotClosedError:
            return Response({'error': 'Este anticipo no está cerrado.'}, status=status.HTTP_400_BAD_REQUEST)
        except UndoWindowExpiredError:
            return Response(
                {'error': 'Ya pasó el tiempo para deshacer este cierre. Use "Reabrir" con una justificación.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(PhysicalCountClosureSerializer(closure).data, status=status.HTTP_201_CREATED)


class PhysicalReportReopenView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(summary="Reabrir el conteo físico de un anticipo cerrado, con justificación.")
    def post(self, request, pk):
        if not can_manage_physical_reports(request.user):
            return Response({'error': 'No tiene permisos para reabrir este registro.'}, status=status.HTTP_403_FORBIDDEN)
        try:
            advance = Advance.objects.get(pk=pk)
        except Advance.DoesNotExist:
            return Response({'error': 'Anticipo no encontrado.'}, status=status.HTTP_404_NOT_FOUND)

        serializer = ReopenSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        try:
            closure = reopen_advance(advance, request.user, serializer.validated_data['justification'])
        except NotClosedError:
            return Response({'error': 'Este anticipo no está cerrado.'}, status=status.HTTP_400_BAD_REQUEST)

        return Response(PhysicalCountClosureSerializer(closure).data, status=status.HTTP_201_CREATED)


class ClosedPhysicalReportListView(APIView):
    """GET /physical-reports/closed/ — anticipos con el conteo físico cerrado, para la vista de 'Cerrados' (reabrir)."""
    permission_classes = [IsAuthenticated]

    @extend_schema(summary="Listar anticipos con el conteo físico cerrado.")
    def get(self, request):
        as_of_date, error = _parse_date_param(request)
        if error:
            return error
        rows = get_closed_physical_reports(as_of_date=as_of_date)
        return Response([_serialize_summary(r) for r in rows])


class PhysicalReportBulkEntryView(APIView):
    """
    POST /physical-reports/bulk-entries/ — botón único "Guardar todos" de la
    tabla principal: una misma fecha para varios anticipos a la vez. Cada
    entrada se procesa independientemente (no es una transacción conjunta):
    si un anticipo falla (p.ej. quedó fuera de la ventana de ajuste rápido
    porque alguien más lo corrigió hace rato, o se cerró mientras tanto), el
    resto de anticipos válidos igual se guardan — el frontend le muestra al
    usuario cuáles filas fallaron y por qué, para que las ajuste
    individualmente desde el detalle.
    """
    permission_classes = [IsAuthenticated]

    @extend_schema(summary="Registrar el conteo físico de varios anticipos a la vez, para una misma fecha.")
    def post(self, request):
        if not can_manage_physical_reports(request.user):
            return Response(
                {'error': 'No tiene permisos para registrar el conteo físico.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = BulkRegisterEntriesSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        date = serializer.validated_data['date']
        results = []
        for item in serializer.validated_data['entries']:
            advance_id = item['advance']
            try:
                advance = Advance.objects.get(pk=advance_id)
            except Advance.DoesNotExist:
                results.append({'advance': advance_id, 'status': 'error', 'error': 'Anticipo no encontrado.'})
                continue

            try:
                entry = register_entry(advance, date=date, count=item['count'], user=request.user)
            except ClosedTrackingError:
                results.append({
                    'advance': advance_id, 'status': 'error',
                    'error': 'El conteo físico de este anticipo está cerrado.',
                })
            except JustificationRequiredError:
                results.append({
                    'advance': advance_id, 'status': 'error',
                    'error': 'Ya pasó la ventana de ajuste rápido: corríjalo individualmente desde el detalle.',
                })
            else:
                results.append({
                    'advance': advance_id, 'status': 'ok',
                    'entry': PhysicalCountEntrySerializer(entry).data,
                })

        return Response(results)
