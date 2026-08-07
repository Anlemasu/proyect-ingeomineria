from decimal import Decimal

from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db import transaction
from apps.audit.services import log_action

from .models import Advance, AdvanceMovement
from .serializers import AdvanceSerializer, AdvanceMovementSerializer
from .services import annotate_available_balance, settle_pending_debts


def can_manage_advances(user):
    return user.role in ['superuser', 'accountant', 'commercial_admin']


class AdvanceListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        advances = Advance.objects.select_related('client', 'user').all().order_by('-date')
        client_id = request.query_params.get('client')
        if client_id:
            advances = advances.filter(client_id=client_id)
        # FASE 6.2: saldo de todos los anticipos en una sola consulta
        # agregada en vez de una query por anticipo (ver AdvanceSerializer).
        advances = annotate_available_balance(advances)
        serializer = AdvanceSerializer(advances, many=True)
        return Response(serializer.data)

    def post(self, request):
        if not can_manage_advances(request.user):
            log_action(request, 'access_denied', 'Advance')
            return Response(
                {'error': 'No tiene permisos para registrar anticipos.'},
                status=status.HTTP_403_FORBIDDEN
            )
        serializer = AdvanceSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        try:
            trips_quantity = int(request.data.get('trips_quantity', 0))
            if trips_quantity < 0:
                trips_quantity = 0
        except (TypeError, ValueError):
            trips_quantity = 0

        try:
            with transaction.atomic():
                advance: Advance = serializer.save(user=request.user)  # type: ignore

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

            advance.refresh_from_db()
            return Response(AdvanceSerializer(advance).data, status=status.HTTP_201_CREATED)
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

    def get(self, request, pk):
        obj = self.get_object(pk)
        if not obj:
            return Response(
                {'error': 'Anticipo no encontrado.'},
                status=status.HTTP_404_NOT_FOUND
            )
        return Response(AdvanceSerializer(obj).data)

    def patch(self, request, pk):
        if request.user.role != 'superuser':
            log_action(request, 'access_denied', 'Advance', object_id=pk)
            return Response(
                {'error': 'Solo el Superusuario puede modificar anticipos.'},
                status=status.HTTP_403_FORBIDDEN
            )
        obj = self.get_object(pk)
        if not obj:
            return Response(
                {'error': 'Anticipo no encontrado.'},
                status=status.HTTP_404_NOT_FOUND
            )

        # Capturar datos anteriores antes de modificar (RF-32B)
        previous = dict(AdvanceSerializer(obj).data)  # type: ignore

        serializer = AdvanceSerializer(obj, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            log_action(
                request, 'update', 'Advance',
                object_id=obj.id,
                previous_data=previous,
                new_data=dict(serializer.data),  # type: ignore
            )
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


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

    def get(self, request, client_id):
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
