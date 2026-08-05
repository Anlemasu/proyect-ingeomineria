from decimal import Decimal

from django.db.models import Sum

from apps.audit.services import log_action
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
    transaction.atomic() con `advance` ya bloqueado por select_for_update()
    (mismo patrón de Fase 1), para que dos anticipos creándose casi al
    mismo tiempo para el mismo cliente no liquiden la misma deuda dos veces.

    Devuelve la lista de AdvanceMovement creados (una por deuda liquidada).
    """
    from apps.trips.models import Trip  # import diferido: evita ciclo con trips.models, que importa advances.models a nivel de módulo

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
