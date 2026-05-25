from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.utils import timezone
from django.db.models import Sum
from apps.audit.services import log_action

from .models import DailySummary
from .serializers import DailySummarySerializer
from apps.trips.models import Trip
from apps.expenses.models import Expense


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

        if DailySummary.objects.filter(date=today).exists():
            return Response(
                {'error': 'Ya existe un cierre de caja para el día de hoy.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        trips = Trip.objects.filter(date=today, state=True)

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

        trips.update(summary=summary)

        # RF-41: registrar el cierre en auditoría
        log_action(
            request, 'create', 'DailySummary',
            object_id=summary.id,
            new_data=dict(DailySummarySerializer(summary).data),  # type: ignore
        )

        return Response(
            DailySummarySerializer(summary).data,
            status=status.HTTP_201_CREATED
        )