from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.utils import timezone
from django.db.models import Sum, Count

from .models import DailySummary
from .serializers import DailySummarySerializer
from apps.trips.models import Trip
from apps.expenses.models import Expense


class DailySummaryListView(APIView):
    """
    GET /api/cash-closing/  → lista cierres históricos
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        summaries = DailySummary.objects.all().order_by('-date')
        serializer = DailySummarySerializer(summaries, many=True)
        return Response(serializer.data)


class DailySummaryCloseView(APIView):
    """
    POST /api/cash-closing/close/  → ejecuta el cierre de caja del día (RF-41)
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        if request.user.role not in ['superuser', 'cashier']:
            return Response(
                {'error': 'No tiene permisos para ejecutar el cierre de caja.'},
                status=status.HTTP_403_FORBIDDEN
            )

        today = timezone.now().date()

        # Verificar que no exista ya un cierre para hoy
        if DailySummary.objects.filter(date=today).exists():
            return Response(
                {'error': 'Ya existe un cierre de caja para el día de hoy.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Obtener todos los viajes activos del día
        trips = Trip.objects.filter(date=today, state=True)

        # Calcular totales por medio de pago
        income_cash = trips.filter(
            payment__is_advance=False,
            payment__name__icontains='efectivo'
        ).aggregate(total=Sum('value'))['total'] or 0

        income_transfer = trips.filter(
            payment__is_advance=False,
            payment__name__icontains='transferencia'
        ).aggregate(total=Sum('value'))['total'] or 0

        income_advance = trips.filter(
            payment__is_advance=True
        ).aggregate(total=Sum('value'))['total'] or 0

        total_trips   = trips.count()
        total_volume  = trips.aggregate(
            total=Sum('vehicle__vehicle_type__capacity')
        )['total'] or 0

        avg_trip_value = (
            trips.aggregate(total=Sum('value'))['total'] or 0
        ) / total_trips if total_trips > 0 else 0

        total_expenses = Expense.objects.filter(
            date=today
        ).aggregate(total=Sum('value'))['total'] or 0

        # Crear el cierre
        summary = DailySummary.objects.create(
            date=today,
            total_trips=total_trips,
            total_volume=total_volume,
            income_cash=income_cash,
            income_transfer=income_transfer,
            income_advance=income_advance,
            avg_trip_value=avg_trip_value,
            total_expenses=total_expenses,
        )

        # Asociar los viajes del día al cierre
        trips.update(summary=summary)

        return Response(
            DailySummarySerializer(summary).data,
            status=status.HTTP_201_CREATED
        )