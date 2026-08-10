import random
from datetime import timedelta, time
from decimal import Decimal, ROUND_HALF_UP

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.advances.models import Advance, AdvanceMovement
from apps.cash_closing.services import execute_close, AlreadyClosedError
from apps.clients.models import Client
from apps.expenses.models import Expense
from apps.invoices.models import Invoice
from apps.masters.models import Vehicle, MaterialType, OriginSite, PaymentMethod, Tariff
from apps.trips.models import Trip
from apps.users.models import User

EXPENSE_DESCRIPTIONS = [
    'Combustible', 'Peajes', 'Mantenimiento vehículo', 'Papelería',
    'Alimentación conductor', 'Lavado de vehículo', 'Imprevistos operativos',
]


def round_money(value) -> Decimal:
    return Decimal(value).quantize(Decimal('1'), rounding=ROUND_HALF_UP)


class Command(BaseCommand):
    help = (
        'Genera datos históricos de prueba (viajes, anticipos consumidos, '
        'gastos, facturas y cierres de caja) reusando la lógica real del '
        'proyecto. Requiere que ya existan clientes, usuarios y catálogos '
        '(masters) activos — se recomienda correr clean_test_data antes.'
    )

    def add_arguments(self, parser):
        parser.add_argument('--days', type=int, default=60, help='Días hacia atrás a generar (default 60).')
        parser.add_argument('--seed', type=int, default=None, help='Semilla random para reproducibilidad.')

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError('DEBUG=False: este comando solo corre contra una base de desarrollo.')

        if options['seed'] is not None:
            random.seed(options['seed'])

        clients = list(Client.objects.filter(state=True))
        vehicles = list(Vehicle.objects.filter(vehicle_type__state=True))
        material_types = list(MaterialType.objects.filter(state=True))
        origin_sites = list(OriginSite.objects.filter(state=True))
        payment_methods = list(PaymentMethod.objects.filter(state=True))
        admin_user = User.objects.filter(role='superuser', state=True).order_by('id').first()
        cashier_like = list(User.objects.filter(state=True, role__in=['cashier', 'commercial_admin', 'superuser']))
        accountant_like = list(User.objects.filter(state=True, role__in=['accountant', 'superuser']))
        any_active_user = list(User.objects.filter(state=True))

        missing = [
            name for name, values in [
                ('clientes activos', clients), ('vehículos activos', vehicles),
                ('tipos de material activos', material_types), ('sitios de origen activos', origin_sites),
                ('métodos de pago activos', payment_methods), ('usuarios activos', any_active_user),
            ] if not values
        ]
        if missing or admin_user is None:
            if admin_user is None:
                missing.append('un usuario superuser activo')
            raise CommandError(
                'Faltan catálogos base para poder sembrar datos históricos: ' + ', '.join(missing) + '.'
            )

        tariff_by_vehicle_type = {
            t.vehicle_type_id: t.value
            for t in Tariff.objects.filter(state=True).order_by('id')
        }
        default_tariff = Decimal('150000')

        advance_payment_methods = [p for p in payment_methods if p.is_advance]
        regular_payment_methods = [p for p in payment_methods if not p.is_advance]

        end_date = timezone.localdate() - timedelta(days=1)
        start_date = end_date - timedelta(days=options['days'] - 1)
        business_days = [
            start_date + timedelta(days=i)
            for i in range((end_date - start_date).days + 1)
            if (start_date + timedelta(days=i)).weekday() < 5
        ]
        if not business_days:
            raise CommandError('El rango de fechas no contiene días hábiles.')

        next_voucher = (Trip.objects.order_by('-voucher_num').values_list('voucher_num', flat=True).first() or 0) + 1
        advance_cycles: dict[int, dict] = {}
        trips_by_group: dict[tuple, list[Trip]] = {}

        self.stdout.write(f'Generando viajes/anticipos/gastos entre {start_date} y {end_date}...')

        for day in business_days:
            for _ in range(random.randint(3, 6)):
                client = random.choice(clients)
                vehicle = random.choice(vehicles)
                material = random.choice(material_types)
                origin = random.choice(origin_sites)
                tariff_value = tariff_by_vehicle_type.get(vehicle.vehicle_type_id, default_tariff)

                use_advance = advance_payment_methods and random.random() < 0.35
                if use_advance:
                    payment = random.choice(advance_payment_methods)
                    cycle = advance_cycles.get(client.id)
                    if cycle is None or cycle['remaining'] <= 0:
                        value_ = round_money(random.randint(15, 40) * Decimal('100000'))
                        transfer_num = random.randint(100000, 999999)
                        advance = Advance.objects.create(
                            client=client, user=random.choice(cashier_like), value=value_,
                            transfer_num=transfer_num, date=day,
                            observations='Anticipo de prueba (seed histórico).',
                        )
                        AdvanceMovement.objects.create(
                            advance=advance, type_movement='ingreso', amount=value_,
                            trips_quantity=0, date=day,
                            description=f'Anticipo registrado. Ref: {transfer_num}',
                        )
                        cycle = {'advance': advance, 'remaining': value_}
                        advance_cycles[client.id] = cycle

                    trip_value = tariff_value if cycle['remaining'] >= tariff_value else cycle['remaining']
                    trip_value = round_money(trip_value)
                    advance_used = cycle['advance']
                else:
                    payment = random.choice(regular_payment_methods or payment_methods)
                    trip_value = round_money(tariff_value * Decimal(str(round(random.uniform(0.9, 1.15), 2))))
                    advance_used = None

                voucher_num = next_voucher
                next_voucher += 1
                register_time = time(hour=random.randint(7, 17), minute=random.randint(0, 59))
                date_register = timezone.make_aware(timezone.datetime.combine(day, register_time))

                trip = Trip.objects.create(
                    payment=payment, origin_site=origin, material_type=material, client=client,
                    vehicle=vehicle, advance=advance_used, voucher_num=voucher_num, value=trip_value,
                    date_register=date_register, date=day, state=True,
                )

                if advance_used:
                    AdvanceMovement.objects.create(
                        advance=advance_used, trip=trip, type_movement='egreso', amount=trip_value,
                        trips_quantity=1, date=day, description=f'Descuento por viaje #{voucher_num}',
                    )
                    advance_cycles[client.id]['remaining'] -= trip_value

                group_key = (client.id, day.isocalendar()[:2])
                trips_by_group.setdefault(group_key, []).append(trip)

            for _ in range(random.randint(0, 2)):
                Expense.objects.create(
                    user=random.choice(any_active_user),
                    value=round_money(random.randint(4, 35) * Decimal('10000')),
                    description=random.choice(EXPENSE_DESCRIPTIONS),
                    date=day, state=True,
                )

        # Cierra cada anticipo que quedó activo al final de la ventana con un
        # viaje final por el saldo exacto, para que "anticipos ya finalizados"
        # sea literal: ningún Advance queda con saldo colgado sin consumir.
        closing_day = business_days[-1]
        for client in clients:
            cycle = advance_cycles.get(client.id)
            if not cycle or cycle['remaining'] <= 0:
                continue
            vehicle = random.choice(vehicles)
            material = random.choice(material_types)
            origin = random.choice(origin_sites)
            payment = random.choice(advance_payment_methods)
            trip_value = round_money(cycle['remaining'])
            voucher_num = next_voucher
            next_voucher += 1
            register_time = time(hour=random.randint(7, 17), minute=random.randint(0, 59))
            date_register = timezone.make_aware(timezone.datetime.combine(closing_day, register_time))

            trip = Trip.objects.create(
                payment=payment, origin_site=origin, material_type=material, client=client,
                vehicle=vehicle, advance=cycle['advance'], voucher_num=voucher_num, value=trip_value,
                date_register=date_register, date=closing_day, state=True,
                observations='Viaje de cierre para liquidar el anticipo (seed histórico).',
            )
            AdvanceMovement.objects.create(
                advance=cycle['advance'], trip=trip, type_movement='egreso', amount=trip_value,
                trips_quantity=1, date=closing_day, description=f'Descuento por viaje #{voucher_num}',
            )
            cycle['remaining'] -= trip_value
            trips_by_group.setdefault((client.id, closing_day.isocalendar()[:2]), []).append(trip)

        self.stdout.write('Generando facturas...')
        invoice_seq = 1
        for group_trips in trips_by_group.values():
            if random.random() >= 0.6:
                continue
            invoice = Invoice.objects.create(
                user=random.choice(accountant_like), number=f'FAC-{invoice_seq:05d}',
            )
            invoice_seq += 1
            for pos, trip in enumerate(group_trips, start=1):
                trip.invoice = invoice
                trip.invoice_pos = pos
                trip.save(update_fields=['invoice', 'invoice_pos'])

        self.stdout.write('Cerrando caja día por día...')
        closed, skipped = 0, 0
        for day in business_days:
            try:
                execute_close(day, user=admin_user, source='manual')
                closed += 1
            except AlreadyClosedError:
                skipped += 1
            except Exception as exc:
                self.stderr.write(self.style.WARNING(f'No se pudo cerrar {day}: {exc}'))

        self.stdout.write(self.style.SUCCESS(
            f'Listo. Viajes: {Trip.objects.count()}, Anticipos: {Advance.objects.count()}, '
            f'Facturas: {Invoice.objects.count()}, Gastos: {Expense.objects.count()}, '
            f'Cierres de caja: {closed} (ya existentes/saltados: {skipped}).'
        ))
