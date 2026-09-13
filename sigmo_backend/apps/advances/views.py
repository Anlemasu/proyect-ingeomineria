from decimal import Decimal

from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from drf_spectacular.utils import extend_schema
from django.db import transaction
from apps.audit.services import log_action

from .models import Advance, AdvanceMovement
from .serializers import AdvanceSerializer, AdvanceMovementSerializer, AdvanceValueCorrectionSerializer
from .services import (
    annotate_available_balance,
    settle_pending_debts,
    correct_active_advance_value,
    compute_unlink_impact,
    get_pending_debts_by_client,
    AdvanceNotActiveError,
    NoValueChangeError,
)
from apps.pending_entries.models import PendingEntry
from apps.pending_entries.services import (
    execute_pending_advance,
    PendingEntryNotPendingError,
    PendingEntryTypeMismatchError,
    PendingEntryClientMismatchError,
)


def can_manage_advances(user):
    return user.role in ['superuser', 'accountant', 'commercial_admin']


class AdvanceListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(summary="Listar anticipos registrados, con filtro opcional por cliente.")
    def get(self, request):
        """Listar anticipos registrados, con filtro opcional por cliente."""
        advances = Advance.objects.select_related('client', 'user').all().order_by('-date')
        client_id = request.query_params.get('client')
        if client_id:
            advances = advances.filter(client_id=client_id)
        # FASE 6.2: saldo de todos los anticipos en una sola consulta
        # agregada en vez de una query por anticipo (ver AdvanceSerializer).
        advances = annotate_available_balance(advances)
        serializer = AdvanceSerializer(advances, many=True)
        return Response(serializer.data)

    @extend_schema(summary="Registrar un nuevo anticipo para un cliente.")
    def post(self, request):
        """Registrar un nuevo anticipo para un cliente."""
        if not can_manage_advances(request.user):
            log_action(request, 'access_denied', 'Advance')
            return Response(
                {'error': 'No tiene permisos para registrar anticipos.'},
                status=status.HTTP_403_FORBIDDEN
            )
        serializer = AdvanceSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        # RN#4 — vincular este anticipo a un aviso de "anticipo pendiente"
        # (apps.pending_entries) ya existente para el mismo cliente, si el
        # frontend mandó uno. Se valida ANTES del atomic para no crear el
        # Advance si el pendiente ya no está disponible.
        pending_entry = None
        pending_entry_id = request.data.get('pending_entry_id')
        if pending_entry_id:
            try:
                pending_entry = PendingEntry.objects.get(pk=pending_entry_id)
            except PendingEntry.DoesNotExist:
                return Response({'error': 'Anticipo pendiente no encontrado.'}, status=status.HTTP_404_NOT_FOUND)
            if pending_entry.status != 'pending':
                return Response(
                    {'error': 'Este pendiente ya fue ejecutado o cancelado.'},
                    status=status.HTTP_409_CONFLICT
                )
            if pending_entry.entry_type != 'advance':
                return Response(
                    {'error': 'Este pendiente no corresponde a un anticipo.'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            if pending_entry.client_id != serializer.validated_data['client'].id:  # type: ignore
                return Response(
                    {'error': 'El cliente del pendiente no coincide con el cliente del anticipo.'},
                    status=status.HTTP_400_BAD_REQUEST
                )

        try:
            trips_quantity = int(request.data.get('trips_quantity', 0))
            if trips_quantity < 0:
                trips_quantity = 0
        except (TypeError, ValueError):
            trips_quantity = 0

        try:
            with transaction.atomic():
                # `trips_quantity` > 0 también queda como el cupo esperado del
                # módulo "Reporte Físico" (apps.physical_reports) — mismo dato
                # de entrada, sin agregar un campo nuevo al formulario de
                # creación de anticipo.
                extra = {'expected_trips_quantity': trips_quantity} if trips_quantity > 0 else {}
                advance: Advance = serializer.save(user=request.user, **extra)  # type: ignore

                # select_for_update() aunque la fila se acaba de crear (mismo
                # patrón de Fase 1): protege contra una liquidación de deuda
                # concurrente si, por lo que sea, dos requests terminan
                # operando sobre este mismo anticipo casi al mismo tiempo.
                advance = Advance.objects.select_for_update().get(pk=advance.pk)

                AdvanceMovement.objects.create(
                    advance=advance,
                    type_movement='ingreso',
                    amount=advance.value,
                    trips_quantity=trips_quantity,
                    date=advance.date,
                    description=f'Anticipo registrado. Ref: {advance.transfer_num}',
                )
                log_action(
                    request, 'create', 'Advance',
                    object_id=advance.id,
                    new_data=dict(AdvanceSerializer(advance).data),  # type: ignore
                )

                # FASE 3: liquidar deuda pendiente del cliente ANTES de que
                # el saldo quede disponible para viajes futuros — ver
                # advances/services.py:settle_pending_debts (FIFO por
                # date_register del viaje).
                settle_pending_debts(advance, request=request)

                if pending_entry:
                    execute_pending_advance(pending_entry, advance, request=request)

            advance.refresh_from_db()
            return Response(AdvanceSerializer(advance).data, status=status.HTTP_201_CREATED)
        except (PendingEntryNotPendingError, PendingEntryTypeMismatchError, PendingEntryClientMismatchError):
            # Carrera rara: el pendiente se ejecutó/canceló entre la
            # validación de arriba y este punto. El atomic ya revirtió la
            # creación del Advance.
            return Response(
                {'error': 'El pendiente ya no está disponible para ejecutar (puede haber sido ejecutado por otra solicitud).'},
                status=status.HTTP_409_CONFLICT
            )
        except Exception:
            return Response(
                {'error': 'Error al registrar el anticipo. Intente nuevamente.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class AdvanceDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get_object(self, pk):
        try:
            return Advance.objects.get(pk=pk)
        except Advance.DoesNotExist:
            return None

    @extend_schema(summary="Consultar el detalle de un anticipo.")
    def get(self, request, pk):
        """Consultar el detalle de un anticipo."""
        obj = self.get_object(pk)
        if not obj:
            return Response(
                {'error': 'Anticipo no encontrado.'},
                status=status.HTTP_404_NOT_FOUND
            )
        return Response(AdvanceSerializer(obj).data)

    @extend_schema(summary="Editar un anticipo (Superusuario, Contador o Administrador Comercial).")
    def patch(self, request, pk):
        """Editar un anticipo (Superusuario, Contador o Administrador Comercial)."""
        # Antes solo el superusuario podía editar. Se amplía a los mismos 3
        # roles que ya pueden registrar anticipos y corregir su valor
        # (can_manage_advances) — quien ya puede tocar el campo más sensible
        # (`value`, vía AdvanceCorrectValueView) no tiene sentido que se le
        # bloquee editar el resto de campos (fecha, N° consignación, N°
        # proforma, observaciones), y quien registra un anticipo debe poder
        # corregir sus propios datos.
        if not can_manage_advances(request.user):
            log_action(request, 'access_denied', 'Advance', object_id=pk)
            return Response(
                {'error': 'No tiene permisos para modificar anticipos.'},
                status=status.HTTP_403_FORBIDDEN
            )
        obj = self.get_object(pk)
        if not obj:
            return Response(
                {'error': 'Anticipo no encontrado.'},
                status=status.HTTP_404_NOT_FOUND
            )

        # trips_quantity no es un campo de Advance (vive en el
        # AdvanceMovement de ingreso inicial, ver
        # AdvanceSerializer.get_trips_quantity) — el serializer lo declara
        # read_only, así que se valida y aplica aparte, igual que en
        # AdvanceListCreateView.post.
        trips_quantity = None
        if 'trips_quantity' in request.data:
            try:
                trips_quantity = int(request.data.get('trips_quantity'))
                if trips_quantity < 0:
                    raise ValueError
            except (TypeError, ValueError):
                return Response(
                    {'error': 'El número de viajes debe ser un entero no negativo.'},
                    status=status.HTTP_400_BAD_REQUEST
                )

        # Capturar datos anteriores antes de modificar (RF-32B)
        previous = dict(AdvanceSerializer(obj).data)  # type: ignore

        serializer = AdvanceSerializer(obj, data=request.data, partial=True)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            serializer.save()

            if trips_quantity is not None:
                initial_movement = (
                    AdvanceMovement.objects.filter(advance=obj, type_movement='ingreso')
                    .order_by('id').first()
                )
                if initial_movement:
                    initial_movement.trips_quantity = trips_quantity
                    initial_movement.save(update_fields=['trips_quantity'])

                # Mantiene sincronizado el cupo esperado que lee "Reporte
                # Físico" (apps.physical_reports.Advance.expected_trips_quantity)
                # con este mismo dato — son "el mismo número" desde la óptica
                # del usuario (ver AdvanceListCreateView.post, que lo fija
                # igual al crear). Sin este `save`, corregir aquí el N° de
                # viajes no se reflejaba nunca en Reporte Físico.
                obj.expected_trips_quantity = trips_quantity
                obj.save(update_fields=['expected_trips_quantity'])

            obj.refresh_from_db()
            fresh_data = AdvanceSerializer(obj).data  # type: ignore
            log_action(
                request, 'update', 'Advance',
                object_id=obj.id,
                previous_data=previous,
                new_data=dict(fresh_data),
            )

        return Response(fresh_data)


class AdvanceBalanceView(APIView):
    """
    Estado de cuenta de anticipos del cliente (RF-33, extendido en Fase 3
    para el modelo de "anticipo activo + deuda pendiente"):
    - `advances`: todos los anticipos del cliente (activo y congelados) con
      su saldo individual, calculado en vivo igual que antes.
    - `pending_debts`: viajes pagados con "anticipo del cliente" que
      todavía no se han podido liquidar contra ningún anticipo.
    - `net_balance`: suma de saldos de todos los anticipos MENOS el total
      de deuda pendiente — el número que de verdad resume la posición del
      cliente con la empresa.
    """
    permission_classes = [IsAuthenticated]

    @extend_schema(summary="Consultar el estado de cuenta de anticipos de un cliente.")
    def get(self, request, client_id):
        """Consultar el estado de cuenta de anticipos de un cliente."""
        from apps.trips.models import Trip  # import diferido: evita ciclo con trips.models

        # FASE 6.2: saldo de todos los anticipos del cliente en una sola
        # consulta agregada (antes: una query de ingresos + una de egresos
        # POR anticipo dentro del for de abajo).
        advances = list(annotate_available_balance(
            Advance.objects.filter(client_id=client_id).order_by('-date', '-id')
        ))
        active_advance_id = advances[0].id if advances else None

        advances_detail = []
        total_advances_balance = Decimal('0')
        for adv in advances:
            balance = (adv._annotated_ingresos or Decimal('0')) - (adv._annotated_egresos or Decimal('0'))  # type: ignore[attr-defined]
            total_advances_balance += balance
            advances_detail.append({
                'id': adv.id,
                'date': adv.date,
                'value': str(adv.value),
                'transfer_num': adv.transfer_num,
                'available_balance': str(balance),
                'is_active': adv.id == active_advance_id,
            })

        pending_trips = Trip.objects.filter(
            client_id=client_id, state=True, advance__isnull=True, payment__is_advance=True,
        ).order_by('date_register')
        pending_debts_detail = [
            {
                'trip': trip.id,
                'voucher_num': trip.voucher_num,
                'date': trip.date,
                'value': str(trip.value),
                'justification': trip.pending_debt_justification,
            }
            for trip in pending_trips
        ]
        total_pending_debt = sum((t.value for t in pending_trips), Decimal('0'))

        return Response({
            'client_id': client_id,
            'advances': advances_detail,
            'total_advances_balance': str(total_advances_balance),
            'pending_debts': pending_debts_detail,
            'total_pending_debt': str(total_pending_debt),
            'net_balance': str(total_advances_balance - total_pending_debt),
        })


class AdvancePendingDebtsSummaryView(APIView):
    """
    GET /advances/pending-debts/
    Deuda pendiente total por cliente, en una sola consulta — usado por el
    listado general de "Estado de Cuenta" (AdvancesPage.vue) para restar la
    deuda del saldo de cada cliente sin pedir el balance uno por uno.
    """
    permission_classes = [IsAuthenticated]

    @extend_schema(summary="Consultar la deuda pendiente total por cliente.")
    def get(self, request):
        """Consultar la deuda pendiente total por cliente."""
        summary = get_pending_debts_by_client()
        return Response({str(client_id): str(total) for client_id, total in summary.items()})


class AdvanceCorrectValueView(APIView):
    """
    FASE 9C — corrige el valor original de un anticipo (típicamente un
    error de digitación) creando un movimiento de ajuste, sin editar ni
    borrar ningún AdvanceMovement existente (ver correct_active_advance_value
    en advances/services.py).

    Endpoint separado y explícito (POST .../correct-value/) en vez de
    extender AdvanceDetailView.patch: el PATCH genérico ya bloquea `value`
    de plano en cuanto el anticipo tiene movimientos (Fase 9.3) — meter
    este flujo ahí exigiría una excepción especial al bloqueo justo en el
    mismo lugar que lo declara, lo cual es más difícil de leer y más fácil
    de des-sincronizar a futuro que un endpoint aparte, con su propio
    contrato de entrada (correct_value + justification, siempre
    obligatoria, sin los demás campos editables de un Advance normal).
    """
    permission_classes = [IsAuthenticated]

    @extend_schema(summary="Corregir el valor de un anticipo activo.")
    def post(self, request, pk):
        """Corregir el valor de un anticipo activo."""
        # Mismos 3 roles ya autorizados para gestionar anticipos en general
        # (ver can_manage_advances arriba) — la Fase 9C no amplía ni reduce
        # ese conjunto, solo lo reutiliza para esta operación puntual.
        if not can_manage_advances(request.user):
            log_action(request, 'access_denied', 'Advance', object_id=pk)
            return Response(
                {'error': 'No tiene permisos para corregir el valor de anticipos.'},
                status=status.HTTP_403_FORBIDDEN
            )

        try:
            advance = Advance.objects.get(pk=pk)
        except Advance.DoesNotExist:
            return Response(
                {'error': 'Anticipo no encontrado.'},
                status=status.HTTP_404_NOT_FOUND
            )

        serializer = AdvanceValueCorrectionSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        correct_value = serializer.validated_data['correct_value']  # type: ignore
        justification = serializer.validated_data['justification']  # type: ignore

        try:
            result = correct_active_advance_value(
                advance,
                correct_value=correct_value,
                justification=justification,
                request=request,
            )
        except AdvanceNotActiveError:
            return Response({
                'error': (
                    'Solo se puede corregir el anticipo activo del cliente '
                    '(el más reciente). Este anticipo ya fue reemplazado por '
                    'uno más nuevo y quedó congelado.'
                )
            }, status=status.HTTP_400_BAD_REQUEST)
        except NoValueChangeError:
            return Response({
                'error': 'El valor corregido es igual al valor ya registrado: no hay nada que ajustar.'
            }, status=status.HTTP_400_BAD_REQUEST)

        advance.refresh_from_db()
        return Response({
            'advance': AdvanceSerializer(advance).data,
            'movement': AdvanceMovementSerializer(result['movement']).data,
            'unlinked_trips': result['unlinked_trips'],
            'settled_trips': result['settled_trips'],
        }, status=status.HTTP_200_OK)


class AdvanceCorrectValuePreviewView(APIView):
    """
    POST /advances/<id>/correct-value/preview/
    Simula (sin escribir nada) el impacto de corregir el valor de un
    anticipo a `correct_value` — mismo cálculo que hace
    correct_active_advance_value antes de escribir (compute_unlink_impact),
    para que el frontend pueda mostrar una advertencia clara ("estos viajes
    quedarán como deuda pendiente") ANTES de que el usuario confirme y
    escriba la justificación.
    """
    permission_classes = [IsAuthenticated]

    @extend_schema(summary="Simular el impacto de corregir el valor de un anticipo.")
    def post(self, request, pk):
        """Simular el impacto de corregir el valor de un anticipo."""
        if not can_manage_advances(request.user):
            return Response(
                {'error': 'No tiene permisos para corregir el valor de anticipos.'},
                status=status.HTTP_403_FORBIDDEN
            )

        try:
            advance = Advance.objects.get(pk=pk)
        except Advance.DoesNotExist:
            return Response(
                {'error': 'Anticipo no encontrado.'},
                status=status.HTTP_404_NOT_FOUND
            )

        correct_value = request.data.get('correct_value')
        try:
            correct_value = Decimal(str(correct_value))
        except Exception:
            return Response(
                {'error': 'correct_value debe ser un número válido.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        impact = compute_unlink_impact(advance, correct_value)
        return Response({
            'balance_before': str(impact['balance_before']),
            'prospective_balance': str(impact['prospective_balance']),
            'trips_to_unlink': [
                {
                    'trip': t.id,
                    'voucher_num': t.voucher_num,
                    'date': t.date,
                    'value': str(t.value),
                }
                for t in impact['trips_to_unlink']
            ],
        })
