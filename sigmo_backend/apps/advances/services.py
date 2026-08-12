from decimal import Decimal

from django.db import transaction
from django.db.models import Case, DecimalField, QuerySet, Sum, Value, When
from django.utils import timezone

from apps.audit.services import log_action
from apps.clients.models import Client
from .models import Advance, AdvanceMovement


class AdvanceNotActiveError(Exception):
    """
    9C — solo el anticipo ACTIVO de un cliente (el más reciente, ver
    get_active_advance) puede corregirse por este mecanismo. Uno congelado
    (ya no es el más reciente) sigue el mismo principio de "una vez
    congelado, no se vuelve a tocar" que ya rige en el resto del sistema
    (ver get_active_advance) — se rechaza explícitamente en vez de permitir
    que un ajuste retroactivo reabra un anticipo histórico.
    """


class NoValueChangeError(Exception):
    """9C — el valor corregido es igual al valor ya registrado: no hay
    ningún ajuste real que aplicar, así que no tiene sentido crear un
    AdvanceMovement de monto cero ni dejar una entrada de auditoría vacía."""


def get_available_balance(advance: Advance) -> Decimal:
    """
    RF-30: saldo disponible = suma de ingresos - suma de egresos de los
    AdvanceMovement del anticipo. Se calcula siempre en vivo a partir de
    los movimientos (nunca desde Advance.value) para que quede trazable
    movimiento por movimiento en el AuditLog/historial.

    Extraída como función independiente (antes vivía solo dentro de
    AdvanceSerializer.get_available_balance) para poder reutilizarla desde
    trips/services.py al validar/revertir el saldo de un viaje pagado con
    anticipo, sin tener que instanciar un serializer solo para leer un
    campo.
    """
    movs = AdvanceMovement.objects.filter(advance=advance)

    ingresos = movs.filter(
        type_movement='ingreso'
    ).aggregate(total=Sum('amount'))['total'] or Decimal('0')

    egresos = movs.filter(
        type_movement='egreso'
    ).aggregate(total=Sum('amount'))['total'] or Decimal('0')

    return ingresos - egresos


def annotate_available_balance(queryset: QuerySet) -> QuerySet:
    """
    FASE 6.2: mismo cálculo que get_available_balance (ingresos - egresos de
    AdvanceMovement) pero en una sola consulta agregada para listas, en vez
    de dos queries por anticipo (N+1 al listar varios anticipos, ej. panel
    de alertas de saldo bajo en el Dashboard).

    Los dos Sum() condicionales (Case/When) van en el mismo annotate() para
    que compartan un único JOIN a AdvanceMovement — si fueran dos
    annotate() separados, Django haría un JOIN por cada uno y el resultado
    se multiplicaría (bug clásico de agregación sobre relaciones inversas).

    Agrega `_annotated_ingresos` y `_annotated_egresos` a cada objeto del
    queryset; AdvanceSerializer.get_available_balance los usa si están
    presentes y si no, cae de vuelta a get_available_balance(obj) (por
    ejemplo cuando se serializa un Advance individual sin pasar por acá).
    """
    zero = Value(Decimal('0'), output_field=DecimalField(max_digits=15, decimal_places=2))
    return queryset.annotate(
        _annotated_ingresos=Sum(
            Case(
                When(advancemovement__type_movement='ingreso', then='advancemovement__amount'),
                default=zero,
                output_field=DecimalField(max_digits=15, decimal_places=2),
            )
        ),
        _annotated_egresos=Sum(
            Case(
                When(advancemovement__type_movement='egreso', then='advancemovement__amount'),
                default=zero,
                output_field=DecimalField(max_digits=15, decimal_places=2),
            )
        ),
    )


def get_active_advance(client) -> Advance | None:
    """
    FASE 3 — reemplaza el supuesto de "un solo anticipo por cliente": ahora
    un cliente puede tener varios ADVANCE a lo largo del tiempo, pero solo
    el más reciente es el "anticipo activo" que descuenta viajes nuevos.
    Cualquier anticipo anterior queda congelado permanentemente en cuanto
    se crea uno nuevo — nunca vuelve a recibir descuentos, sin importar el
    saldo que le quede (ese saldo simplemente queda como historial).

    Criterio de "más reciente": mayor `date` y, a igualdad de fecha, mayor
    `id` (el creado después). Devuelve None si el cliente no tiene ningún
    anticipo registrado.
    """
    return Advance.objects.filter(client=client).order_by('-date', '-id').first()


def settle_pending_debts(advance: Advance, *, request=None) -> list[AdvanceMovement]:
    """
    FASE 3 — al crear un anticipo nuevo, liquida ANTES que nada las deudas
    pendientes del cliente: viajes pagados con "Anticipo del cliente" que
    se guardaron sin descontar nada porque, en su momento, ningún anticipo
    activo tenía saldo suficiente (ver TripListCreateView.post). El saldo
    que le quede a `advance` después de esto es el que queda disponible
    para viajes futuros.

    Deuda pendiente = Trip activo, pagado con medio "anticipo", con
    `advance` en NULL (ver Trip.pending_debt_justification / decisión de
    modelo de datos documentada en trips/models.py).

    Orden de liquidación: FIFO estricto por `date_register` del viaje, el
    más antiguo primero. Es "estricto" en el sentido de que si el saldo no
    alcanza para el siguiente viaje pendiente en la fila, la liquidación
    SE DETIENE ahí — no salta ese viaje para liquidar uno más barato que
    esté más adelante en la fila. Esto es una decisión explícita (el
    enunciado de la Fase 3 pide "en orden", y el test de aceptación de dos
    deudas confirma este comportamiento) y no un límite técnico.

    El caller controla la transacción: debe llamarse dentro de un
    transaction.atomic(). El select_for_update() sobre la fila de `advance`
    que ya hace el caller (AdvanceListCreateView.post) NO alcanza para
    prevenir la doble liquidación: cada anticipo nuevo es una fila distinta,
    así que dos anticipos creándose casi al mismo tiempo para el MISMO
    cliente no generan ninguna contención entre sí bloqueando cada uno el
    suyo, y ambos pueden leer el mismo Trip pendiente antes de que
    cualquiera escriba. Por eso esta función bloquea, ella misma, la fila
    del Client del anticipo (select_for_update) antes de leer
    `pending_trips`: un lock por cliente (no global, no por-anticipo), para
    que dos anticipos del mismo cliente se serialicen entre sí sin bloquear
    a otros clientes.

    Devuelve la lista de AdvanceMovement creados (una por deuda liquidada).
    """
    from apps.trips.models import Trip  # import diferido: evita ciclo con trips.models, que importa advances.models a nivel de módulo

    # BUG 2 — ver docstring arriba: serializa por cliente la lectura+escritura
    # de los Trip pendientes, que es la sección crítica real de esta función.
    Client.objects.select_for_update().get(pk=advance.client_id)

    # 'id' como desempate: dos viajes con el mismo date_register (posible si
    # dos requests caen en el mismo timestamp) antes quedaban en orden
    # indeterminado — con 'id' el orden de creación siempre desempata igual.
    pending_trips = Trip.objects.filter(
        client=advance.client,
        state=True,
        advance__isnull=True,
        payment__is_advance=True,
    ).order_by('date_register', 'id')

    remaining = get_available_balance(advance)
    created_movements: list[AdvanceMovement] = []

    for trip in pending_trips:
        if trip.value > remaining:
            break

        movement = AdvanceMovement.objects.create(
            advance=advance,
            trip=trip,
            type_movement='egreso',
            amount=trip.value,
            trips_quantity=1,
            date=advance.date,
            description=f'Liquidación de deuda pendiente — viaje #{trip.voucher_num}',
        )
        trip.advance = advance
        trip.save(update_fields=['advance'])
        remaining -= trip.value
        created_movements.append(movement)

        log_action(
            request, 'update', 'Trip',
            object_id=trip.id,
            previous_data={'advance': None, 'pending_debt': True},
            new_data={'advance': advance.id, 'pending_debt': False, 'amount_settled': str(trip.value)},
            justification=f'Liquidado automáticamente (FIFO) contra el anticipo #{advance.id}.',
        )

    return created_movements


def get_pending_debts_by_client() -> dict[int, Decimal]:
    """
    Deuda pendiente total (viajes sin liquidar contra ningún anticipo, ver
    settle_pending_debts) agrupada por cliente, en UNA sola consulta — para
    el listado general de "Estado de Cuenta" (AdvancesPage.vue), que antes
    solo sumaba el available_balance de los anticipos sin restar esta deuda.
    AdvanceBalanceView.get ya calcula lo mismo pero para un único cliente a
    la vez; esto evita hacer esa misma consulta cliente por cliente.
    """
    from apps.trips.models import Trip  # import diferido: evita ciclo con trips.models

    rows = Trip.objects.filter(
        state=True, advance__isnull=True, payment__is_advance=True,
    ).values('client').annotate(total=Sum('value'))
    return {row['client']: row['total'] for row in rows}


def compute_unlink_impact(advance: Advance, correct_value: Decimal) -> dict:
    """
    Calcula, SIN escribir nada, qué viajes de `advance` quedarían como deuda
    pendiente si se corrigiera su valor a `correct_value` — usado tanto por
    la previsualización (AdvanceCorrectValuePreviewView) como por
    correct_active_advance_value (que repite este cálculo ya bajo lock, por
    si algo cambió entre la previsualización y el envío real).

    Si la reducción deja el saldo disponible en negativo, se sueltan los
    viajes vinculados a este anticipo MÁS RECIENTES primero (orden LIFO por
    date_register) — son los que "empujaron" el saldo hasta lo que ahora no
    alcanza a cubrirse — hasta cubrir el faltante o quedarse sin viajes que
    soltar. Si ni soltando todos alcanza, el resto de la reducción
    simplemente se aplica igual (saldo negativo real, mismo criterio que ya
    regía en esta función antes de esta lógica).
    """
    from apps.trips.models import Trip  # import diferido: evita ciclo con trips.models

    diff = correct_value - advance.value
    balance_before = get_available_balance(advance)
    prospective_balance = balance_before + diff

    trips_to_unlink: list = []
    if diff < 0 and prospective_balance < 0:
        shortfall = -prospective_balance
        for trip in Trip.objects.filter(advance=advance, state=True).order_by('-date_register'):
            if shortfall <= 0:
                break
            trips_to_unlink.append(trip)
            shortfall -= trip.value

    return {
        'diff': diff,
        'balance_before': balance_before,
        'prospective_balance': prospective_balance,
        'trips_to_unlink': trips_to_unlink,
    }


def correct_active_advance_value(
    advance: Advance, *, correct_value: Decimal, justification: str, request=None,
) -> dict:
    """
    FASE 9C — corrige el valor original de un anticipo cuando se detectó un
    error de digitación, aunque ya se hayan descontado viajes contra él.

    Sigue el mismo principio que el resto del proyecto para corregir
    saldos (ver sync_advance_movement_on_trip_change, reverse_advance_discount):
    NUNCA se edita/borra un AdvanceMovement ya existente — se crea uno
    NUEVO de ajuste (ingreso o egreso) que deja el saldo correcto,
    preservando el historial completo intacto.

    La corrección se expresa como "el valor correcto debería ser X", no
    como un delta. El monto del movimiento de ajuste es
    `correct_value - advance.value` (el valor ORIGINAL registrado, no el
    saldo disponible en vivo): así, lo que ya se consumió (egresos por
    viajes) no se ve afectado por la corrección — solo se corrige el monto
    de fondeo, y el saldo disponible resultante queda automáticamente en
    `correct_value - lo_ya_consumido`, tal como pide el negocio. Si el
    ajuste calculado fuera contra el saldo disponible en vez de contra
    `advance.value`, lo ya consumido se sumaría o restaría dos veces.

    REQUISITO NUEVO — si la reducción deja el saldo disponible en negativo,
    antes de aplicar el ajuste se sueltan (ver compute_unlink_impact) los
    viajes vinculados más recientes como deuda pendiente: se crea un
    movimiento de "ingreso" que reversa (nunca borra) su egreso original, el
    viaje pasa a `advance=None` con la misma justificación, y queda listo
    para liquidarse automáticamente (FIFO) contra el próximo anticipo del
    cliente — reutiliza settle_pending_debts, el mismo mecanismo que ya
    existe para viajes registrados sin saldo suficiente.

    Además del movimiento de ajuste, actualiza `Advance.value` al valor
    corregido: es necesario para que una SEGUNDA corrección futura calcule
    el diff contra el valor ya corregido, no contra el original equivocado
    (si no se actualizara, una corrección posterior "revertiría"
    silenciosamente la anterior). Esto se hace a nivel de modelo
    (`.save(update_fields=...)`), no a través de AdvanceSerializer — el
    bloqueo de edición de `value` de la Fase 9.3 vive en el serializer (vía
    AdvanceDetailView.patch, el PATCH genérico) y sigue intacto; este es un
    mecanismo explícito y separado, auditado aparte, no un bypass silencioso
    de ese bloqueo.

    Un saldo resultante negativo que ni soltando todos los viajes
    vinculados alcanza a cubrir se PERMITE igual — mismo criterio que ya
    regía en sync_advance_movement_on_trip_change cuando un ajuste de valor
    de viaje deja el anticipo en negativo: es información real, no un error
    a bloquear.

    Bloqueo: primero la fila del Client (mismo patrón que
    settle_pending_debts) para que la pregunta "¿sigue siendo el anticipo
    activo?" se responda de forma consistente aunque se esté creando un
    anticipo nuevo para el mismo cliente casi al mismo tiempo; después la
    fila del propio Advance (mismo patrón que
    sync_advance_movement_on_trip_change) para serializar contra un
    descuento de viaje concurrente que esté a punto de escribir su propio
    AdvanceMovement contra este mismo anticipo; y los viajes candidatos a
    soltar también con select_for_update() por la misma razón. El caller
    debe llamar esto dentro de su propio transaction.atomic() — aquí se abre
    uno propio para mantener la función autocontenida, igual que
    reverse_advance_discount.
    """
    from apps.trips.models import Trip  # import diferido: evita ciclo con trips.models

    with transaction.atomic():
        Client.objects.select_for_update().get(pk=advance.client_id)

        active_advance = get_active_advance(advance.client)
        if active_advance is None or active_advance.id != advance.id:
            raise AdvanceNotActiveError()

        locked_advance = Advance.objects.select_for_update().get(pk=advance.pk)

        old_value = locked_advance.value
        diff = correct_value - old_value
        if diff == 0:
            raise NoValueChangeError()

        balance_before = get_available_balance(locked_advance)

        unlinked_trips: list[dict] = []
        impact = compute_unlink_impact(locked_advance, correct_value)
        if impact['trips_to_unlink']:
            trip_ids = [t.id for t in impact['trips_to_unlink']]
            # Vuelve a traer los mismos viajes bajo lock — compute_unlink_impact
            # los leyó sin bloquear, así que se relee bajo select_for_update()
            # antes de escribir, preservando el orden LIFO ya calculado.
            locked_trips = {
                t.id: t for t in Trip.objects.select_for_update().filter(id__in=trip_ids)
            }
            for trip_id in trip_ids:
                trip = locked_trips[trip_id]
                AdvanceMovement.objects.create(
                    advance=locked_advance,
                    trip=trip,
                    type_movement='ingreso',
                    amount=trip.value,
                    trips_quantity=0,
                    date=timezone.localdate(),
                    description=(
                        f'Reversión por corrección de valor del anticipo '
                        f'#{locked_advance.id} — viaje #{trip.voucher_num} '
                        f'pasa a deuda pendiente.'
                    ),
                )
                previous_trip_data = {'advance': trip.advance_id, 'pending_debt': False}
                trip.advance = None
                trip.pending_debt_justification = justification
                trip.save(update_fields=['advance', 'pending_debt_justification'])
                unlinked_trips.append({
                    'trip': trip.id,
                    'voucher_num': trip.voucher_num,
                    'value': str(trip.value),
                })
                log_action(
                    request, 'update', 'Trip',
                    object_id=trip.id,
                    previous_data=previous_trip_data,
                    new_data={'advance': None, 'pending_debt': True, 'amount_released': str(trip.value)},
                    justification=justification,
                )

        movement = AdvanceMovement.objects.create(
            advance=locked_advance,
            type_movement='ingreso' if diff > 0 else 'egreso',
            amount=abs(diff),
            trips_quantity=0,
            date=timezone.localdate(),
            description=f'Corrección de valor original del anticipo #{locked_advance.id}: {justification}',
        )

        locked_advance.value = correct_value
        locked_advance.save(update_fields=['value'])

        # Si la corrección AUMENTÓ el valor, la capacidad nueva debe poder
        # liquidar deuda pendiente del cliente igual que ya hace
        # AdvanceListCreateView.post al crear un anticipo — antes esto solo
        # se disparaba al crear uno nuevo, así que corregir hacia arriba el
        # valor de uno YA existente nunca liquidaba nada, aunque el saldo
        # resultante alcanzara para cubrir la deuda.
        settled_movements: list[AdvanceMovement] = []
        if diff > 0:
            settled_movements = settle_pending_debts(locked_advance, request=request)

        balance_after = get_available_balance(locked_advance)

        log_action(
            request, 'update', 'Advance',
            object_id=locked_advance.id,
            previous_data={
                'value': str(old_value),
                'available_balance': str(balance_before),
            },
            new_data={
                'value': str(correct_value),
                'available_balance': str(balance_after),
                'difference': str(diff),
                'role': getattr(getattr(request, 'user', None), 'role', None),
                'movement_created': {
                    'id': movement.id,
                    'type_movement': movement.type_movement,
                    'amount': str(movement.amount),
                },
                'unlinked_trips': unlinked_trips,
                'settled_trips': [m.trip_id for m in settled_movements],
            },
            justification=justification,
        )

        return {
            'movement': movement,
            'unlinked_trips': unlinked_trips,
            'settled_trips': [
                {'trip': m.trip_id, 'amount': str(m.amount)} for m in settled_movements
            ],
        }
