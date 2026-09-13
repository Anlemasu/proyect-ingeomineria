from datetime import timedelta

from django.db import transaction
from django.db.models import Max, OuterRef, Exists, Q
from django.utils import timezone

from apps.advances.models import Advance
from apps.advances.services import get_active_advance
from apps.audit.services import log_action
from .models import PhysicalCountEntry, PhysicalCountClosure

# Ventana para "deshacer" un cierre sin justificación (ver reglas de negocio
# en el plan): pasado este tiempo, reabrir un anticipo cerrado exige
# justificación auditada (reopen_advance) en vez de un deshacer simple
# (undo_close_advance).
UNDO_WINDOW_MINUTES = 15

# Ventana de "ajuste rápido" de un conteo físico ya guardado: dentro de este
# tiempo, corregir el valor de un día ya contado NO exige justificación (se
# trata como si el campo siguiera "abierto" mientras se termina de cargar el
# día) — pasada la ventana, la única forma de ajustarlo es individualmente
# desde el detalle (el "ojito"), con justificación obligatoria. Ver
# register_entry / is_entry_editable.
ENTRY_ADJUSTMENT_WINDOW_MINUTES = 30


class ClosedTrackingError(Exception):
    """El anticipo tiene el conteo físico cerrado: no admite nuevas entradas hasta reabrirse."""


class JustificationRequiredError(Exception):
    """Ya existía un conteo para esta fecha (o se intenta reabrir fuera de la ventana de deshacer): se exige justificación."""


class QuotaAlreadySetError(Exception):
    """El anticipo ya tiene un cupo esperado definido: esta operación solo permite agregarlo cuando falta."""


class NotClosedError(Exception):
    """La acción exige que el anticipo esté cerrado (deshacer cierre / reabrir) y no lo está."""


class UndoWindowExpiredError(Exception):
    """Ya pasó la ventana para deshacer el cierre sin justificación: usar reopen_advance."""


def get_latest_entries_by_date(advance: Advance) -> dict:
    """
    Devuelve {date: PhysicalCountEntry} con el registro VIGENTE (el de mayor
    id) para cada fecha distinta del anticipo — una corrección posterior a
    una fecha ya contada agrega un registro nuevo en vez de editar el
    anterior, así que "vigente" siempre es el último por id.
    """
    latest_ids = (
        PhysicalCountEntry.objects.filter(advance=advance)
        .values('date')
        .annotate(latest_id=Max('id'))
        .values_list('latest_id', flat=True)
    )
    entries = PhysicalCountEntry.objects.filter(id__in=list(latest_ids))
    return {entry.date: entry for entry in entries}


def get_cumulative_entered(advance: Advance, *, as_of_date=None) -> int:
    """
    Suma de los conteos vigentes (uno por fecha distinta) del anticipo. Con
    `as_of_date`, solo suma las fechas hasta esa fecha inclusive — para
    poder mostrar "cómo iba el acumulado" en una fecha puntual del pasado,
    sin que eso afecte el acumulado real (de hoy) que se usa para decidir
    qué anticipos siguen pendientes (ver get_open_physical_reports).
    """
    entries = get_latest_entries_by_date(advance)
    if as_of_date is not None:
        entries = {d: e for d, e in entries.items() if d <= as_of_date}
    return sum(entry.count for entry in entries.values())


def is_entry_editable(entry: PhysicalCountEntry | None) -> bool:
    """
    True si todavía no hay ningún conteo guardado para ese día (entry=None),
    o si el que hay se guardó dentro de la ventana de ajuste rápido
    (ENTRY_ADJUSTMENT_WINDOW_MINUTES). Pasada esa ventana, corregirlo exige
    justificación — ver register_entry.
    """
    if entry is None:
        return True
    return timezone.now() - entry.created_at <= timedelta(minutes=ENTRY_ADJUSTMENT_WINDOW_MINUTES)


def get_trips_on_other_advances(advance: Advance, date) -> list:
    """
    Viajes del MISMO cliente y la MISMA fecha, pero vinculados a OTRO
    anticipo (no a `advance`) — la señal concreta de que se podría estar
    mirando/registrando el conteo físico del anticipo equivocado.

    Caso real que motivó esto: un cliente con dos anticipos visibles en
    Reporte Físico (el activo + uno congelado que seguía abierto); los 3
    viajes del día se habían descontado contra el activo, pero el conteo
    físico se cargó en el congelado — ese anticipo mostraba "0 viajes en el
    sistema" (correcto para ÉL) sin ninguna pista de que los viajes SÍ
    existían, solo que en el otro anticipo del mismo cliente.
    """
    from apps.trips.models import Trip
    return list(
        Trip.objects.filter(client=advance.client, date=date, state=True)
        .exclude(advance=advance)
        .exclude(advance__isnull=True)
        .select_related('advance')
    )


def get_last_closure_action(advance: Advance) -> PhysicalCountClosure | None:
    return (
        PhysicalCountClosure.objects.filter(advance=advance)
        .order_by('-id')
        .first()
    )


def is_closed(advance: Advance) -> bool:
    last = get_last_closure_action(advance)
    return last is not None and last.action == 'close'


def _candidate_advances():
    """
    Anticipos relevantes para "Reporte Físico":
    - el anticipo ACTIVO actual de cada cliente (ver get_active_advance en
      apps.advances.services) SIEMPRE es candidato, aunque todavía no tenga
      cupo ni ningún conteo — así el cajero puede encontrarlo en "Pendientes"
      y usar "Definir cupo" la primera vez; si no se incluyera aquí, un
      anticipo activo sin cupo ni conteos nunca aparecería en ningún lado.
    - un anticipo YA NO activo (congelado por uno más nuevo) solo es
      candidato si tiene cupo definido o al menos un conteo registrado — es
      el mismo criterio que antes, para no listar cada anticipo histórico
      del sistema sin ningún dato de conciliación.
    """
    advance_ids_with_entries = PhysicalCountEntry.objects.values_list('advance_id', flat=True)
    # "Activo" = no existe, para el mismo cliente, un anticipo más nuevo
    # (mayor fecha, o misma fecha con mayor id) — mismo criterio de
    # desempate que get_active_advance.
    newer_advance_exists = Advance.objects.filter(client=OuterRef('client')).filter(
        Q(date__gt=OuterRef('date')) | Q(date=OuterRef('date'), id__gt=OuterRef('id'))
    )
    return Advance.objects.annotate(
        _is_active=~Exists(newer_advance_exists)
    ).filter(
        Q(_is_active=True)
        | Q(expected_trips_quantity__isnull=False)
        | Q(id__in=advance_ids_with_entries)
    ).select_related('client').distinct()


def _summarize(advance: Advance, *, as_of_date=None) -> dict:
    cumulative = get_cumulative_entered(advance, as_of_date=as_of_date)
    expected = advance.expected_trips_quantity
    remaining = (expected - cumulative) if expected is not None else None
    active = get_active_advance(advance.client)
    row = {
        'advance': advance,
        'expected_trips_quantity': expected,
        'cumulative_entered': cumulative,
        'remaining': remaining,
        # Si el cliente tiene más de un anticipo visible en Reporte Físico
        # (el activo + uno congelado que todavía se está terminando de
        # contar), esto le permite al frontend distinguirlos con una
        # etiqueta — evita registrar por error contra el que ya no
        # descuenta viajes nuevos (ver bug reportado: un conteo físico
        # cargado en el anticipo equivocado mostraba "0 viajes" aunque sí
        # se habían registrado, porque esos viajes en realidad se
        # descontaron contra el otro anticipo del cliente).
        'is_active': active is not None and active.id == advance.id,
    }
    if as_of_date is not None:
        # Dato puntual de la fecha seleccionada (no acumulado): lo que ya
        # se guardó exactamente ese día, y si el campo de registro rápido
        # (inline, en la tabla) todavía puede editarse sin justificación —
        # ver ENTRY_ADJUSTMENT_WINDOW_MINUTES.
        entry = get_latest_entries_by_date(advance).get(as_of_date)
        row['day_count'] = entry.count if entry else None
        row['day_editable'] = is_entry_editable(entry)
    return row


def get_open_physical_reports(*, as_of_date=None) -> list[dict]:
    """
    Anticipos con el conteo físico abierto (no cerrado) que además, si
    tienen cupo definido, todavía les faltan viajes por confirmar
    (remaining > 0) — un anticipo que ya llegó a 0 restantes desaparece solo
    de esta lista sin necesitar cierre manual (ver reglas de negocio del
    plan). Es la lista que alimenta la vista principal de "Reporte Físico".

    `as_of_date`, si se pasa, NO cambia qué anticipos aparecen (eso siempre
    se decide con el acumulado real/de hoy) — solo cambia lo que se
    muestra en 'cumulative_entered'/'remaining'/'day_count'/'day_editable'
    de cada fila, para poder consultar "cómo iba" en una fecha puntual.
    """
    result = []
    for advance in _candidate_advances():
        if is_closed(advance):
            continue
        current = _summarize(advance)
        if current['remaining'] is not None and current['remaining'] <= 0:
            continue
        result.append(_summarize(advance, as_of_date=as_of_date) if as_of_date is not None else current)
    return result


def get_closed_physical_reports(*, as_of_date=None) -> list[dict]:
    """Anticipos con el conteo físico cerrado — alimenta la vista de 'Cerrados' (reabrir)."""
    return [
        _summarize(advance, as_of_date=as_of_date)
        for advance in _candidate_advances() if is_closed(advance)
    ]


@transaction.atomic
def register_entry(advance: Advance, *, date, count: int, user, justification: str | None = None) -> PhysicalCountEntry:
    locked_advance = Advance.objects.select_for_update().get(pk=advance.pk)
    if is_closed(locked_advance):
        raise ClosedTrackingError()

    previous = (
        PhysicalCountEntry.objects.filter(advance=locked_advance, date=date)
        .order_by('-id')
        .first()
    )
    if previous is not None:
        if previous.count == count:
            # Sin cambio real (p.ej. reenviado por "Guardar todos" sin haber
            # tocado este valor): no crea un registro duplicado ni exige
            # justificación por nada.
            return previous
        if not is_entry_editable(previous) and not (justification or '').strip():
            raise JustificationRequiredError()

    entry = PhysicalCountEntry.objects.create(
        advance=locked_advance,
        date=date,
        count=count,
        user=user,
        justification=justification.strip() if justification else None,
    )
    log_action(
        None, 'create', 'PhysicalCountEntry',
        object_id=entry.id,
        user=user,
        previous_data={'count': previous.count} if previous else None,
        new_data={'advance': locked_advance.id, 'date': str(date), 'count': count},
        justification=justification,
    )
    return entry


@transaction.atomic
def set_expected_quantity(advance: Advance, quantity: int, user) -> Advance:
    locked_advance = Advance.objects.select_for_update().get(pk=advance.pk)
    if locked_advance.expected_trips_quantity is not None:
        raise QuotaAlreadySetError()

    locked_advance.expected_trips_quantity = quantity
    locked_advance.save(update_fields=['expected_trips_quantity'])
    log_action(
        None, 'update', 'Advance',
        object_id=locked_advance.id,
        user=user,
        previous_data={'expected_trips_quantity': None},
        new_data={'expected_trips_quantity': quantity},
    )
    return locked_advance


@transaction.atomic
def close_advance(advance: Advance, user) -> PhysicalCountClosure:
    if is_closed(advance):
        raise ClosedTrackingError()
    closure = PhysicalCountClosure.objects.create(advance=advance, action='close', user=user)
    log_action(None, 'update', 'PhysicalCountClosure', object_id=closure.id, user=user,
                new_data={'advance': advance.id, 'action': 'close'})
    return closure


@transaction.atomic
def undo_close_advance(advance: Advance, user) -> PhysicalCountClosure:
    last = get_last_closure_action(advance)
    if last is None or last.action != 'close':
        raise NotClosedError()
    if last.user_id != user.id or timezone.now() - last.created_at > timedelta(minutes=UNDO_WINDOW_MINUTES):
        raise UndoWindowExpiredError()

    closure = PhysicalCountClosure.objects.create(advance=advance, action='undo_close', user=user)
    log_action(None, 'update', 'PhysicalCountClosure', object_id=closure.id, user=user,
                new_data={'advance': advance.id, 'action': 'undo_close'})
    return closure


@transaction.atomic
def reopen_advance(advance: Advance, user, justification: str) -> PhysicalCountClosure:
    if not is_closed(advance):
        raise NotClosedError()
    if not (justification or '').strip():
        raise JustificationRequiredError()

    closure = PhysicalCountClosure.objects.create(
        advance=advance, action='reopen', user=user, justification=justification.strip(),
    )
    log_action(None, 'update', 'PhysicalCountClosure', object_id=closure.id, user=user,
                new_data={'advance': advance.id, 'action': 'reopen'}, justification=justification)
    return closure
