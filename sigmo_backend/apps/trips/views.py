from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.utils import timezone

from .models import Trip, Transfer
from .serializers import TripReadSerializer, TripWriteSerializer
from apps.advances.models import Advance, AdvanceMovement


def can_register_trips(user):
    # RF-26: Superusuario y Operador de Caja
    return user.role in ['superuser', 'cashier']


class TripListCreateView(APIView):
    """
    GET  /api/trips/  → lista viajes con filtros (RF-42, RF-43, RF-44)
    POST /api/trips/  → registra un viaje (RF-26)
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        trips = Trip.objects.select_related(
            'client', 'payment', 'vehicle', 'material_type', 'origin_site'
        ).all().order_by('-date_register')

        # Filtros opcionales
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
            return Response(
                {'error': 'No tiene permisos para registrar viajes.'},
                status=status.HTTP_403_FORBIDDEN
            )
        last_trip = Trip.objects.order_by('-voucher_num').first()
        next_voucher = (last_trip.voucher_num + 1) if last_trip else 1

            # Inyectar el voucher en los datos antes de pasarlos al serializer
        data = request.data.copy()
        data['voucher_num'] = next_voucher

        serializer = TripWriteSerializer(data=request.data)
        if serializer.is_valid():
            payment = serializer.validated_data.get('payment')  # type: ignore
            advance = serializer.validated_data.get('advance')  # type: ignore
            value   = serializer.validated_data.get('value')    # type: ignore

            # RF-31B: validar saldo suficiente si el pago es anticipo
            if payment and payment.is_advance and advance:
                from apps.advances.serializers import AdvanceSerializer
                advance_data: dict = dict(AdvanceSerializer(advance).data)  # type: ignore
                raw_balance = advance_data.get('available_balance') or 0  # ← or 0 cubre el None
                balance = float(raw_balance)  # type: ignore
                if float(value) > balance:  # type: ignore
                    return Response({
                        'error': 'Saldo insuficiente.',
                        'saldo_disponible': balance,
                        'valor_viaje': str(value),
                        'diferencia': str(float(value) - balance),  # type: ignore
                    }, status=status.HTTP_400_BAD_REQUEST)

            # Guardar el viaje con fecha de registro automática
            trip: Trip = serializer.save(date_register=timezone.now().date())  # type: ignore

            # RF-31: descontar anticipo automáticamente
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

            return Response(
                TripReadSerializer(trip).data,
                status=status.HTTP_201_CREATED
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class TripDetailView(APIView):
    """
    GET   /api/trips/<id>/  → detalle del viaje
    PATCH /api/trips/<id>/  → ajuste del viaje (RF-36, RF-37)
    """
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
                return Response(
                    {'error': 'Solo puede modificar registros del día en curso.'},
                    status=status.HTTP_403_FORBIDDEN
                )

        # RF-36: operador de caja no puede anular, solo marcar como requiere revisión
        if request.user.role == 'cashier' and request.data.get('state') is False:
            return Response(
                {'error': 'No tiene permisos para anular viajes.'},
                status=status.HTTP_403_FORBIDDEN
            )

        serializer = TripWriteSerializer(obj, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(TripReadSerializer(obj).data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)