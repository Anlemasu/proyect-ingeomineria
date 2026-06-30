from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.utils import timezone
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

        today = timezone.now().date()
        try:
            summary = execute_close(today)
            log_action(
                request, 'create', 'DailySummary',
                object_id=summary.id,
                new_data=dict(DailySummarySerializer(summary).data),  # type: ignore
            )
            return Response(DailySummarySerializer(summary).data, status=status.HTTP_201_CREATED)
        except AlreadyClosedError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception:
            return Response(
                {'error': 'Error al ejecutar el cierre de caja. Intente nuevamente.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class DailySummaryTodayView(APIView):
    """
    GET /api/cash-closing/today/
    Resumen en tiempo real del día en curso sin crear cierre (RF-43, RF-46)
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        today = timezone.now().date()
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

        # Verificar si ya existe cierre para hoy
        already_closed = DailySummary.objects.filter(date=today).exists()

        return Response({
            'date': today,
            'already_closed': already_closed,
            'total_trips': total_trips,
            'total_volume': total_volume,
            'avg_trip_value': avg_trip_value,
            'total_expenses': total_expenses,
            'payment_details': payment_details,
        })