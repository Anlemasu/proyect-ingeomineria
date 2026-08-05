from django.db import transaction, IntegrityError
from django.db.models import Sum

from .models import DailySummary, DailySummaryPayment
from .serializers import DailySummarySerializer
from apps.trips.models import Trip
from apps.expenses.models import Expense
from apps.masters.models import PaymentMethod
from apps.audit.services import log_action


class AlreadyClosedError(Exception):
    """El día ya tiene un cierre de caja registrado."""


_SOURCE_NOTES = {
    'manual': None,
    'auto': 'Cierre automático (comando auto_close_cash).',
    'recovery': 'Cierre retroactivo (comando recover_missed_closings, reparación de un día huérfano).',
}


def recalculate_daily_summary(date, summary: DailySummary) -> DailySummary:
    """
    Recalcula desde cero los totales de un DailySummary a partir de los
    TRIP activos y los EXPENSE de su fecha, y reemplaza su desglose por
    método de pago.

    Función reutilizada por tres flujos (para no duplicar la lógica de
    sumatorias): el cierre normal (execute_close), la reparación de
    cierres huérfanos (recover_missed_closings) y el resync automático
    cuando un ajuste histórico de superusuario (RF-37) toca un viaje de
    un día ya cerrado (ver resync_if_closed).

    El caller es responsable de bloquear `summary` con select_for_update()
    dentro de un transaction.atomic() antes de llamar esta función, para
    que dos recálculos concurrentes del mismo día (p. ej. un cierre y un
    ajuste histórico simultáneos) no se pisen. No se usa select_for_update()
    sobre los TRIP aquí porque PostgreSQL no permite combinar `FOR UPDATE`
    con funciones de agregación (Sum/Count) en la misma consulta — bloquear
    la fila del DailySummary ya es suficiente para serializar los recálculos.
    """
    trips = Trip.objects.filter(date=date, state=True)

    total_trips = trips.count()
    total_volume = trips.aggregate(
        total=Sum('vehicle__vehicle_type__capacity')
    )['total'] or 0
    total_value = trips.aggregate(total=Sum('value'))['total'] or 0
    avg_trip_value = (total_value / total_trips) if total_trips > 0 else 0
    total_expenses = Expense.objects.filter(
        date=date
    ).aggregate(total=Sum('value'))['total'] or 0

    summary.total_trips = total_trips
    summary.total_volume = total_volume
    summary.avg_trip_value = avg_trip_value
    summary.total_expenses = total_expenses
    summary.save()

    # Se recrea el desglose por método de pago en vez de intentar
    # actualizarlo in-place: es más simple y seguro que un día que antes
    # tenía pagos en "anticipo" y ya no tiene ninguno no deje una fila en
    # cero colgada.
    summary.payment_details.all().delete()
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


def execute_close(date, *, request=None, user=None, source: str = 'manual') -> DailySummary:
    """
    Ejecuta (o re-ejecuta tras una reversión) el cierre de caja para `date`.
    Lanza AlreadyClosedError si el día ya tiene un cierre vigente (state='closed').

    Por qué transaction.atomic() + select_for_update() aquí:
    - select_for_update() sobre la fila existente de DailySummary (si la
      hay) sirve para serializar dos intentos de cierre concurrentes sobre
      un día que ya fue cerrado antes y luego revertido: el segundo espera
      a que el primero termine y ve el estado ya actualizado.
    - Pero si el día NUNCA se ha cerrado, no existe fila que bloquear —
      select_for_update() no puede evitar que dos transacciones intenten
      crear la fila al mismo tiempo. Por eso la guarda real en ese caso es
      el `unique=True` de DailySummary.date a nivel de base de datos: dejamos
      que ambas intenten el INSERT, solo una gana, y la otra recibe un
      IntegrityError que traducimos a AlreadyClosedError (409 en la vista).
      El INSERT se hace en un atomic() anidado (savepoint) para que ese
      IntegrityError no invalide el resto de la transacción externa.
    - Todo el proceso (crear/reabrir el resumen, recalcular totales, crear
      los DailySummaryPayment y marcar los TRIP del día) queda en una sola
      transacción: si algo falla a mitad de camino, el rollback deshace
      todo junto y nunca queda un viaje con `summary` asignado sin que
      exista el DailySummary correspondiente (o viceversa).
    """
    with transaction.atomic():
        existing = DailySummary.objects.select_for_update().filter(date=date).first()

        if existing and existing.state == DailySummary.STATE_CLOSED:
            raise AlreadyClosedError(f'Ya existe un cierre de caja para {date}.')

        if existing:
            # Estaba en 'reverted': se reabre y se recalcula desde cero.
            summary = existing
            summary.state = DailySummary.STATE_CLOSED
            summary.save(update_fields=['state'])
            action = 'update'
        else:
            try:
                with transaction.atomic():
                    summary = DailySummary.objects.create(
                        date=date,
                        state=DailySummary.STATE_CLOSED,
                        total_trips=0,
                        total_volume=0,
                        avg_trip_value=0,
                        total_expenses=0,
                    )
            except IntegrityError:
                raise AlreadyClosedError(f'Ya existe un cierre de caja para {date}.')
            action = 'create'

        recalculate_daily_summary(date, summary)

        log_action(
            request, action, 'DailySummary',
            object_id=summary.id,
            new_data=dict(DailySummarySerializer(summary).data),  # type: ignore
            justification=_SOURCE_NOTES.get(source),
            user=user,
        )

    return summary


def resync_if_closed(date, *, request=None, user=None, trigger_note: str = '') -> DailySummary | None:
    """
    Si `date` tiene un DailySummary vigente (state='closed'), lo recalcula
    desde cero y deja un evento 'recalculo_cierre' en el AuditLog explicando
    qué lo disparó. No hace nada si el día nunca se cerró o si su cierre
    está revertido (un día revertido no debe mostrar totales "vivos").

    Se usa después de guardar un ajuste histórico (RF-37) sobre un viaje ya
    existente de un día cerrado: el bloqueo de creación (execute_close /
    TripListCreateView) impide viajes NUEVOS en un día cerrado, pero el
    ajuste histórico de un viaje YA registrado sigue permitido y por lo
    tanto el DailySummary de ese día puede quedar desactualizado si no se
    recalcula aquí.

    IMPORTANTE para el caller: si el ajuste también generó un
    AdvanceMovement de reversión (viaje pagado con anticipo, BUG 2), este
    resync debe llamarse DESPUÉS de crear ese movimiento — el total por
    método de pago "anticipo" del día depende del valor/estado vigente
    del viaje en ese instante.
    """
    summary = DailySummary.objects.select_for_update().filter(date=date).first()
    if not summary or summary.state != DailySummary.STATE_CLOSED:
        return None

    recalculate_daily_summary(date, summary)

    log_action(
        request, 'recalculo_cierre', 'DailySummary',
        object_id=summary.id,
        new_data=dict(DailySummarySerializer(summary).data),  # type: ignore
        justification=trigger_note,
        user=user,
    )
    return summary
