from datetime import datetime

from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.utils import timezone
from django.db import transaction
from django.db.models import Sum
from apps.audit.services import log_action

from .models import DailySummary, DailySummaryPayment
from .serializers import DailySummarySerializer
from .services import execute_close, AlreadyClosedError
from apps.trips.models import Trip
from apps.expenses.models import Expense
from apps.masters.models import PaymentMethod


class DailySummaryListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        summaries = DailySummary.objects.all().order_by('-date')
        serializer = DailySummarySerializer(summaries, many=True)
        return Response(serializer.data)


class DailySummaryCloseView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        if request.user.role not in ['superuser', 'cashier']:
            log_action(request, 'access_denied', 'DailySummary')
            return Response(
                {'error': 'No tiene permisos para ejecutar el cierre de caja.'},
                status=status.HTTP_403_FORBIDDEN
            )

        # `date` es opcional: sin ella se cierra el día de hoy (comportamiento
        # original, usado por el frontend y por auto_close_cash). Con ella,
        # permite volver a cerrar una fecha pasada que fue revertida
        # (REQUISITO NUEVO 3.3) sin depender de que sea "hoy".
        date_param = request.data.get('date')
        if date_param:
            try:
                target_date = datetime.strptime(date_param, '%Y-%m-%d').date()
            except (TypeError, ValueError):
                return Response(
                    {'error': 'Formato de fecha inválido. Use YYYY-MM-DD.'},
                    status=status.HTTP_400_BAD_REQUEST
                )
        else:
            target_date = timezone.localdate()

        try:
            summary = execute_close(target_date, request=request, source='manual')
            return Response(DailySummarySerializer(summary).data, status=status.HTTP_201_CREATED)
        except AlreadyClosedError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception:
            return Response(
                {'error': 'Error al ejecutar el cierre de caja. Intente nuevamente.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class DailySummaryRevertView(APIView):
    """
    POST /api/cash-closing/<id>/revert/
    Revierte un cierre de caja (state: closed -> reverted), exclusivo para
    superuser y con justificación obligatoria (REQUISITO NUEVO 3.3).

    No elimina el DailySummary ni sus DailySummaryPayment: se conserva el
    histórico de que el día tuvo un cierre. Tras revertir, los viajes y
    gastos de esa fecha vuelven a poder crearse (el bloqueo de
    TripListCreateView/ExpenseListCreateView solo mira state='closed').
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        if request.user.role != 'superuser':
            log_action(request, 'access_denied', 'DailySummary', object_id=pk)
            return Response(
                {'error': 'Solo el Superusuario puede revertir un cierre de caja.'},
                status=status.HTTP_403_FORBIDDEN
            )

        # Decisión: revertir un cierre ya no exige justificación (queda
        # concentrada en la anulación de viajes, ver TripDetailView.patch).
        # Se sigue aceptando y guardando si el caller la manda, solo dejó
        # de ser obligatoria.
        justification = request.data.get('justification', None)

        try:
            with transaction.atomic():
                summary = DailySummary.objects.select_for_update().filter(pk=pk).first()
                if not summary:
                    return Response(
                        {'error': 'Cierre de caja no encontrado.'},
                        status=status.HTTP_404_NOT_FOUND
                    )
                if summary.state != DailySummary.STATE_CLOSED:
                    return Response(
                        {'error': 'Este cierre ya está revertido.'},
                        status=status.HTTP_400_BAD_REQUEST
                    )

                previous = dict(DailySummarySerializer(summary).data)  # type: ignore
                summary.state = DailySummary.STATE_REVERTED
                summary.save(update_fields=['state'])

                log_action(
                    request, 'revert', 'DailySummary',
                    object_id=summary.id,
                    previous_data=previous,
                    new_data=dict(DailySummarySerializer(summary).data),  # type: ignore
                    justification=justification,
                )
                return Response(DailySummarySerializer(summary).data)
        except Exception:
            return Response(
                {'error': 'Error al revertir el cierre de caja. Intente nuevamente.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class DailySummaryTodayView(APIView):
    """
    GET /api/cash-closing/today/
    Resumen en tiempo real del día en curso sin crear cierre (RF-43, RF-46)
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        today = timezone.localdate()
        trips = Trip.objects.filter(date=today, state=True)

        total_trips = trips.count()
        total_volume = trips.aggregate(
            total=Sum('vehicle__vehicle_type__capacity')
        )['total'] or 0
        avg_trip_value = (
            trips.aggregate(total=Sum('value'))['total'] or 0
        ) / total_trips if total_trips > 0 else 0
        total_expenses = Expense.objects.filter(
            date=today
        ).aggregate(total=Sum('value'))['total'] or 0

        # Desglose dinámico por método de pago
        payment_details = []
        for payment_method in PaymentMethod.objects.filter(state=True):
            total = trips.filter(
                payment=payment_method
            ).aggregate(total=Sum('value'))['total'] or 0
            if total > 0:
                payment_details.append({
                    'payment_method': payment_method.id,
                    'payment_method_name': payment_method.name,
                    'total': total,
                })

        # Verificar si ya existe cierre vigente para hoy
        already_closed = DailySummary.objects.filter(
            date=today, state=DailySummary.STATE_CLOSED
        ).exists()

        return Response({
            'date': today,
            'already_closed': already_closed,
            'total_trips': total_trips,
            'total_volume': total_volume,
            'avg_trip_value': avg_trip_value,
            'total_expenses': total_expenses,
            'payment_details': payment_details,
        })
