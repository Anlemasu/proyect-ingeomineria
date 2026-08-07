from decimal import Decimal

from django.db.models import Case, DecimalField, QuerySet, Sum, Value, When

from apps.audit.services import log_action
from apps.clients.models import Client
from .models import Advance, AdvanceMovement


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
