from decimal import Decimal

from django.db import transaction

from .models import Trip
from apps.advances.models import Advance, AdvanceMovement
from apps.advances.services import get_available_balance, get_active_advance
from apps.audit.services import log_action


class InsufficientBalanceError(Exception):
    """El nuevo valor del viaje excede el saldo disponible del anticipo."""

    def __init__(self, balance: Decimal, required: Decimal):
        self.balance = balance
        self.required = required
        self.difference = required - balance
        super().__init__('Saldo insuficiente.')


class UnsupportedAdvanceChangeError(Exception):
    """
    Cambiar el anticipo (o quitar/poner el medio de pago 'anticipo') de un
    viaje que YA está financiado por un anticipo no está soportado por esta
    reversión automática: no hay forma de saber, solo mirando el PATCH, si
    la intención es "corregir un error de captura" o "refinanciar el viaje
    contra otro cliente/anticipo", y cada caso requiere un tratamiento
    contable distinto. Se rechaza explícitamente en vez de aplicar un
    supuesto silencioso; la vía soportada es anular el viaje (que sí revierte
    el saldo correctamente) y registrarlo de nuevo.
    """


def sync_advance_movement_on_trip_change(
    trip: Trip,
    *,
    was_advance_funded: bool,
    old_value: Decimal,
    old_advance: Advance | None,
    new_advance: Advance | None,
    is_annulment: bool,
    force: bool,
    is_superuser: bool,
    request=None,
) -> None:
    """
    BUG 2 — mantiene sincronizado el saldo del anticipo cuando se anula o se
    edita el valor de un viaje que fue pagado con anticipo. Debe llamarse
    DESPUÉS de guardar los cambios del Trip (para que `trip.value` y
    `trip.state` ya reflejen el nuevo estado) pero DENTRO del mismo
    transaction.atomic() que envuelve el guardado, para que un fallo de
    saldo revierta también el cambio del viaje.

    Invariante que esta función mantiene: mientras un viaje esté activo y
    financiado por anticipo, la suma neta (ingresos - egresos) de los
    AdvanceMovement asociados a ese viaje específico (trip=<este viaje>)
    es siempre igual a trip.value. Por eso "revertir" una anulación es
    simplemente llevar esa suma a 0, y "ajustar" una edición de valor es
    llevarla al nuevo valor — en ambos casos el monto del movimiento nuevo
    es la diferencia entre el valor viejo y el valor objetivo.

    Por qué select_for_update() sobre Advance (mismo patrón que el
    select_for_update() sobre el último Trip al numerar voucher_num):
    dos ediciones concurrentes que afectan el mismo anticipo (p. ej. anular
    dos viajes de un mismo cliente al mismo tiempo) podrían leer el mismo
    saldo "viejo" antes de que ninguna haya escrito su movimiento, y ambas
    aprobar montos que ya no caben juntos. Bloquear la fila del Advance
    serializa esas operaciones.

    No modifica ni borra el AdvanceMovement original: se crea siempre un
    movimiento nuevo, preservando la trazabilidad completa exigida por
    auditoría. Además de crear el movimiento, deja su propio evento
    'update'/'Advance' en el AuditLog (BUG 2, punto 5) — independiente del
    evento 'update'/'annul' que el caller ya deja para el Trip — con el
    saldo antes/después, para que quede trazable por qué cambió el saldo
    de un anticipo sin haber tocado el anticipo directamente.
    """
    if not was_advance_funded:
        return

    if new_advance is not None and old_advance is not None and new_advance.id != old_advance.id:
        raise UnsupportedAdvanceChangeError()

    target_value = Decimal('0') if is_annulment else Decimal(trip.value)
    diff = target_value - Decimal(old_value)
    if diff == 0:
        return

    with transaction.atomic():
        advance = Advance.objects.select_for_update().get(pk=old_advance.pk)  # type: ignore[union-attr]
        balance_before = get_available_balance(advance)

        if diff > 0:
            # El nuevo valor es mayor: hace falta descontar más saldo.
            if diff > balance_before and not (force and is_superuser):
                raise InsufficientBalanceError(balance_before, diff)
            movement = AdvanceMovement.objects.create(
                advance=advance,
                trip=trip,
                type_movement='egreso',
                amount=diff,
                trips_quantity=0,
                date=trip.date,
                description=f'Ajuste por edición de viaje #{trip.voucher_num} (incremento de valor)',
            )
        else:
            movement = AdvanceMovement.objects.create(
                advance=advance,
                trip=trip,
                type_movement='ingreso',
                amount=-diff,
                trips_quantity=0,
                date=trip.date,
                description=(
                    f'Reversión por anulación de viaje #{trip.voucher_num}'
                    if is_annulment else
                    f'Ajuste por edición de viaje #{trip.voucher_num} (disminución de valor)'
                ),
            )

        log_action(
            request, 'update', 'Advance',
            object_id=advance.id,
            previous_data={'available_balance': str(balance_before)},
            new_data={
                'available_balance': str(get_available_balance(advance)),
                'movement_created': {
                    'type_movement': movement.type_movement,
                    'amount': str(movement.amount),
                    'trip': trip.id,
                    'description': movement.description,
                },
            },
        )


def reallocate_advance_on_client_change(
    trip: Trip,
    *,
    old_advance: Advance | None,
    was_advance_funded: bool,
    old_value: Decimal,
    justification: str | None,
    request=None,
) -> None:
    """
    Cuando el PATCH de un viaje cambia el cliente, no hay "mismo anticipo"
    que ajustar por diferencia (a diferencia de sync_advance_movement_on_trip_change):
    el saldo debe devolverse por completo al anticipo que financiaba al
    viaje bajo el cliente anterior, y el viaje se reevalúa desde cero
    contra el anticipo activo del cliente nuevo — exactamente las mismas
    reglas que un registro nuevo (ver TripListCreateView.post): si el
    saldo alcanza, se descuenta del anticipo activo; si no alcanza, queda
    como deuda pendiente (advance=NULL) con la justificación capturada.

    Debe llamarse DENTRO del mismo transaction.atomic() que envuelve el
    guardado del Trip, después de serializer.save(). El caller es
    responsable de haber verificado ANTES del atomic (igual que en el
    registro) que si el nuevo cliente no tiene saldo suficiente, ya venga
    una justificación — esta función asume que esa validación ya pasó.

    No toca la liquidación FIFO de deudas pendientes (settle_pending_debts)
    ni el criterio de "anticipo activo = el más reciente del cliente"
    (get_active_advance): ambos siguen aplicando tal cual sobre el
    resultado que esta función deja.
    """
    if was_advance_funded:
        advance = Advance.objects.select_for_update().get(pk=old_advance.pk)  # type: ignore[union-attr]
        balance_before = get_available_balance(advance)
        AdvanceMovement.objects.create(
            advance=advance,
            trip=trip,
            type_movement='ingreso',
            amount=old_value,
            trips_quantity=0,
            date=trip.date,
            description=f'Reversión por cambio de cliente del viaje #{trip.voucher_num}',
        )
        log_action(
            request, 'update', 'Advance',
            object_id=advance.id,
            previous_data={'available_balance': str(balance_before)},
            new_data={'available_balance': str(get_available_balance(advance))},
        )

    if trip.payment.is_advance:
        new_advance = get_active_advance(trip.client)
        available = get_available_balance(new_advance) if new_advance else Decimal('0')

        if trip.value <= available:
            balance_before = available
            AdvanceMovement.objects.create(
                advance=new_advance,
                trip=trip,
                type_movement='egreso',
                amount=trip.value,
                trips_quantity=1,
                date=trip.date,
                description=f'Descuento por cambio de cliente del viaje #{trip.voucher_num}',
            )
            trip.advance = new_advance
            trip.pending_debt_justification = None
            log_action(
                request, 'update', 'Advance',
                object_id=new_advance.id,  # type: ignore[union-attr]
                previous_data={'available_balance': str(balance_before)},
                new_data={'available_balance': str(get_available_balance(new_advance))},
            )
        else:
            trip.advance = None
            trip.pending_debt_justification = justification
    else:
        trip.advance = None
        trip.pending_debt_justification = None

    trip.save(update_fields=['advance', 'pending_debt_justification'])
