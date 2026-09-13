from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.audit.services import log_action
from .models import PendingEntry


class PendingEntryNotPendingError(Exception):
    """El pendiente ya fue ejecutado o cancelado — no admite una segunda ejecución/cancelación."""


class PendingEntryTypeMismatchError(Exception):
    """Se intentó ejecutar un pendiente de tipo 'advance' contra un Trip, o de tipo 'transfer' contra un Advance."""


class PendingEntryClientMismatchError(Exception):
    """El cliente del Advance/Trip que se está creando no coincide con el del pendiente."""


class PendingEntryValueMismatchError(Exception):
    """RN#5: el valor del viaje debe coincidir exactamente con el de la transferencia pendiente."""

    def __init__(self, pending_value: Decimal, actual_value: Decimal):
        self.pending_value = pending_value
        self.actual_value = actual_value
        super().__init__('El valor no coincide con la transferencia pendiente.')


def execute_pending_advance(pending_entry: PendingEntry, advance, *, request=None) -> PendingEntry:
    """
    Marca `pending_entry` (entry_type='advance') como ejecutado y lo
    vincula al Advance recién creado. No exige que pending_entry.value
    coincida con advance.value (RN#4: el anticipo es saldo acumulable, el
    valor real puede ser distinto al avisado).

    select_for_update() sobre la propia fila de PendingEntry: si dos
    requests intentaran ejecutar el MISMO pendiente casi al mismo tiempo, el
    segundo debe encontrarlo ya en status='executed' y fallar explícitamente
    en vez de pisar el vínculo del primero. El caller debe llamar esto
    dentro de su propio transaction.atomic() (el de AdvanceListCreateView.post)
    para que un fallo tumbe también la creación del Advance.
    """
    locked = PendingEntry.objects.select_for_update().get(pk=pending_entry.pk)

    if locked.status != 'pending':
        raise PendingEntryNotPendingError()
    if locked.entry_type != 'advance':
        raise PendingEntryTypeMismatchError()
    if locked.client_id != advance.client_id:
        raise PendingEntryClientMismatchError()

    previous = {'status': locked.status, 'executed_advance': None}
    locked.status = 'executed'
    locked.executed_advance = advance
    locked.executed_by = getattr(request, 'user', None) if request else None
    locked.executed_at = timezone.now()
    locked.save(update_fields=['status', 'executed_advance', 'executed_by', 'executed_at'])

    log_action(
        request, 'update', 'PendingEntry', object_id=locked.id,
        previous_data=previous,
        new_data={'status': 'executed', 'executed_advance': advance.id},
        justification=f'Ejecutado automáticamente al registrar el anticipo #{advance.id}.',
    )
    return locked


def execute_pending_transfer(pending_entry: PendingEntry, trip, *, request=None) -> PendingEntry:
    """
    Igual que execute_pending_advance pero para entry_type='transfer', con
    la validación adicional de RN#5: el valor del Trip debe coincidir
    EXACTAMENTE con pending_entry.value (comparación Decimal, sin
    tolerancia). No hay override/force para este caso — a diferencia del
    saldo insuficiente de anticipos, un valor distinto siempre es un error
    de captura y se rechaza sin excepción posible.
    """
    locked = PendingEntry.objects.select_for_update().get(pk=pending_entry.pk)

    if locked.status != 'pending':
        raise PendingEntryNotPendingError()
    if locked.entry_type != 'transfer':
        raise PendingEntryTypeMismatchError()
    if locked.client_id != trip.client_id:
        raise PendingEntryClientMismatchError()
    if locked.value != trip.value:
        raise PendingEntryValueMismatchError(locked.value, trip.value)

    previous = {'status': locked.status, 'executed_trip': None}
    locked.status = 'executed'
    locked.executed_trip = trip
    locked.executed_by = getattr(request, 'user', None) if request else None
    locked.executed_at = timezone.now()
    locked.save(update_fields=['status', 'executed_trip', 'executed_by', 'executed_at'])

    log_action(
        request, 'update', 'PendingEntry', object_id=locked.id,
        previous_data=previous,
        new_data={'status': 'executed', 'executed_trip': trip.id},
        justification=f'Ejecutado automáticamente al registrar el viaje #{trip.voucher_num}.',
    )
    return locked


def cancel_pending_entry(pending_entry: PendingEntry, *, justification: str, request=None) -> PendingEntry:
    """Soft-cancel: nunca se borra la fila (mismo principio que el resto del sistema)."""
    with transaction.atomic():
        locked = PendingEntry.objects.select_for_update().get(pk=pending_entry.pk)
        if locked.status != 'pending':
            raise PendingEntryNotPendingError()

        previous = {'status': locked.status}
        locked.status = 'cancelled'
        locked.cancelled_by = getattr(request, 'user', None) if request else None
        locked.cancelled_at = timezone.now()
        locked.cancellation_justification = justification
        locked.save(update_fields=['status', 'cancelled_by', 'cancelled_at', 'cancellation_justification'])

        log_action(
            request, 'update', 'PendingEntry', object_id=locked.id,
            previous_data=previous, new_data={'status': 'cancelled'},
            justification=justification,
        )
        return locked
