from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.utils import timezone
from apps.audit.services import log_action
from typing import cast
from django.db import transaction

from .models import Trip
from .serializers import TripReadSerializer, TripWriteSerializer
from apps.advances.models import Advance, AdvanceMovement


def can_register_trips(user):
    return user.role in ['superuser', 'cashier']


class TripListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        trips = Trip.objects.select_related(
            'client', 'payment', 'vehicle', 'material_type', 'origin_site'
        ).all().order_by('-date_register')

        client_id  = request.query_params.get('client')
        date_from  = request.query_params.get('date_from')
        date_to    = request.query_params.get('date_to')
        date       = request.query_params.get('date')
        state      = request.query_params.get('state')
        invoice_id = request.query_params.get('invoice')

        if client_id:
            trips = trips.filter(client_id=client_id)
        if date:
            trips = trips.filter(date=date)
        if date_from:
            trips = trips.filter(date__gte=date_from)
        if date_to:
            trips = trips.filter(date__lte=date_to)
        if state is not None:
            trips = trips.filter(state=state.lower() == 'true')
        if invoice_id:
            trips = trips.filter(invoice_id=invoice_id)

        serializer = TripReadSerializer(trips, many=True)
        return Response(serializer.data)

    def post(self, request):
        if not can_register_trips(request.user):
            log_action(request, 'access_denied', 'Trip')
            return Response(
                {'error': 'No tiene permisos para registrar viajes.'},
                status=status.HTTP_403_FORBIDDEN
            )

        # Validar el serializer antes del atomic para retornar errores claros
        data = request.data.copy()
        data['voucher_num'] = 0  # temporal, se reemplaza dentro del atomic
        serializer = TripWriteSerializer(data=data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        payment = serializer.validated_data.get('payment')  # type: ignore
        advance = serializer.validated_data.get('advance')  # type: ignore
        value   = serializer.validated_data.get('value')    # type: ignore

        # RF-31B: validar saldo ANTES del atomic — es solo lectura, no necesita lock
        if payment and payment.is_advance and advance:
            from apps.advances.serializers import AdvanceSerializer
            advance_data: dict = dict(AdvanceSerializer(advance).data)  # type: ignore
            raw_balance = advance_data.get('available_balance') or 0
            balance = float(raw_balance)  # type: ignore
            if float(value) > balance:  # type: ignore
                return Response({
                    'error': 'Saldo insuficiente.',
                    'saldo_disponible': balance,
                    'valor_viaje': str(value),
                    'diferencia': str(float(value) - balance),  # type: ignore
                }, status=status.HTTP_400_BAD_REQUEST)

        # Solo entrar al atomic para las escrituras
        try:
            with transaction.atomic():
                last_trip = Trip.objects.select_for_update().order_by('-voucher_num').first()
                next_voucher = (last_trip.voucher_num + 1) if last_trip else 1

                trip = cast(Trip, serializer.save(
                    date_register=timezone.now().date(),
                    voucher_num=next_voucher,
                ))

                if payment and payment.is_advance and advance:
                    AdvanceMovement.objects.create(
                        advance=advance,
                        trip=trip,
                        type_movement='egreso',
                        amount=trip.value,
                        trips_quantity=1,
                        date=trip.date,
                        description=f'Descuento por viaje #{trip.voucher_num}',
                    )

                log_action(
                    request, 'create', 'Trip',
                    object_id=trip.id,
                    new_data=dict(TripReadSerializer(trip).data),  # type: ignore
                )

                return Response(
                    TripReadSerializer(trip).data,
                    status=status.HTTP_201_CREATED
                )

        except Exception:
            return Response(
                {'error': 'Error al registrar el viaje. Intente nuevamente.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class TripDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get_object(self, pk):
        try:
            return Trip.objects.get(pk=pk)
        except Trip.DoesNotExist:
            return None

    def get(self, request, pk):
        obj = self.get_object(pk)
        if not obj:
            return Response(
                {'error': 'Viaje no encontrado.'},
                status=status.HTTP_404_NOT_FOUND
            )
        return Response(TripReadSerializer(obj).data)

    def patch(self, request, pk):
        obj = self.get_object(pk)
        if not obj:
            return Response(
                {'error': 'Viaje no encontrado.'},
                status=status.HTTP_404_NOT_FOUND
            )

        # RF-37: registros anulados no pueden modificarse
        if not obj.state:
            return Response(
                {'error': 'No se puede modificar un viaje anulado.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # RF-36: operador de caja solo puede editar registros del día en curso
        if request.user.role == 'cashier':
            if obj.date_register != timezone.now().date():
                log_action(request, 'access_denied', 'Trip', object_id=obj.id)
                return Response(
                    {'error': 'Solo puede modificar registros del día en curso.'},
                    status=status.HTTP_403_FORBIDDEN
                )

        # RF-36: operador de caja no puede anular
        if request.user.role == 'cashier' and request.data.get('state') is False:
            log_action(request, 'access_denied', 'Trip', object_id=obj.id)
            return Response(
                {'error': 'No tiene permisos para anular viajes.'},
                status=status.HTTP_403_FORBIDDEN
            )

        # Capturar datos anteriores antes de modificar (RF-38)
        previous = dict(TripReadSerializer(obj).data)  # type: ignore

        # RF-37: si es anulación, registrar como 'annul'
        is_annulment = request.data.get('state') is False
        action = 'annul' if is_annulment else 'update'

        # RF-37: justificación obligatoria para ajuste histórico de superusuario
        justification = request.data.get('justification', None)
        INVOICE_ONLY_FIELDS = {'invoice', 'invoice_pos'}
        incoming_fields = set(request.data.keys()) - {'justification'}
        is_invoice_only_patch = incoming_fields.issubset(INVOICE_ONLY_FIELDS)

        if request.user.role == 'superuser' and obj.date_register != timezone.now().date():
            if not justification and not is_invoice_only_patch:
                return Response(
                    {'error': 'Se requiere justificación para modificar registros históricos.'},
                    status=status.HTTP_400_BAD_REQUEST
                )

        serializer = TripWriteSerializer(obj, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            log_action(
                request, action, 'Trip',
                object_id=obj.id,
                previous_data=previous,
                new_data=dict(TripReadSerializer(obj).data),  # type: ignore
                justification=justification,
            )
            return Response(TripReadSerializer(obj).data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)