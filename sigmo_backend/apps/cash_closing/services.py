from django.db import transaction
from django.db.models import Sum

from .models import DailySummary, DailySummaryPayment
from apps.trips.models import Trip
from apps.expenses.models import Expense
from apps.masters.models import PaymentMethod


class AlreadyClosedError(Exception):
    """El día ya tiene un cierre de caja registrado."""


def execute_close(date) -> DailySummary:
    """
    Ejecuta el cierre de caja para `date`.
    Lanza AlreadyClosedError si ya existe un cierre para esa fecha.
    """
    if DailySummary.objects.filter(date=date).exists():
        raise AlreadyClosedError(f'Ya existe un cierre de caja para {date}.')

    trips = Trip.objects.filter(date=date, state=True)

    total_trips   = trips.count()
    total_volume  = trips.aggregate(
        total=Sum('vehicle__vehicle_type__capacity')
    )['total'] or 0
    avg_trip_value = (
        trips.aggregate(total=Sum('value'))['total'] or 0
    ) / total_trips if total_trips > 0 else 0
    total_expenses = Expense.objects.filter(
        date=date
    ).aggregate(total=Sum('value'))['total'] or 0

    with transaction.atomic():
        summary = DailySummary.objects.create(
            date=date,
            total_trips=total_trips,
            total_volume=total_volume,
            avg_trip_value=avg_trip_value,
            total_expenses=total_expenses,
        )

        for payment_method in PaymentMethod.objects.filter(state=True):
            total = trips.filter(
                payment=payment_method
            ).aggregate(total=Sum('value'))['total'] or 0
            if total > 0:
                DailySummaryPayment.objects.create(
                    summary=summary,
                    payment_method=payment_method,
                    total=total,
                )

        trips.update(summary=summary)

    return summary
