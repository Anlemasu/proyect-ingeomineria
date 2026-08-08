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

    pending_trips = Trip.objects.filter(
        client=advance.client,
        state=True,
        advance__isnull=True,
        payment__is_advance=True,
    ).order_by('date_register')

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


def correct_active_advance_value(
    advance: Advance, *, correct_value: Decimal, justification: str, request=None,
) -> AdvanceMovement:
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

    Además del movimiento, actualiza `Advance.value` al valor corregido:
    es necesario para que una SEGUNDA corrección futura calcule el diff
    contra el valor ya corregido, no contra el original equivocado (si no
    se actualizara, una corrección posterior "revertiría" silenciosamente
    la anterior). Esto se hace a nivel de modelo (`.save(update_fields=...)`),
    no a través de AdvanceSerializer — el bloqueo de edición de `value` de
    la Fase 9.3 vive en el serializer (vía AdvanceDetailView.patch, el PATCH
    genérico) y sigue intacto; este es un mecanismo explícito y separado,
    auditado aparte, no un bypass silencioso de ese bloqueo.

    Un saldo resultante negativo (la corrección hacia abajo deja al
    cliente debiendo más de lo que ya se había descontado) se PERMITE
    igual — mismo criterio que ya rige en sync_advance_movement_on_trip_change
    cuando un ajuste de valor de viaje deja el anticipo en negativo: es
    información real, no un error a bloquear.

    Bloqueo: primero la fila del Client (mismo patrón que
    settle_pending_debts) para que la pregunta "¿sigue siendo el anticipo
    activo?" se responda de forma consistente aunque se esté creando un
    anticipo nuevo para el mismo cliente casi al mismo tiempo; después la
    fila del propio Advance (mismo patrón que
    sync_advance_movement_on_trip_change) para serializar contra un
    descuento de viaje concurrente que esté a punto de escribir su propio
    AdvanceMovement contra este mismo anticipo. El caller debe llamar esto
    dentro de su propio transaction.atomic() — aquí se abre uno propio para
    mantener la función autocontenida, igual que reverse_advance_discount.
    """
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
            },
            justification=justification,
        )

        return movement
