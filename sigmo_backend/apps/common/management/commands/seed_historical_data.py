import random
import string
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
from apps.masters.models import City, MaterialType, OriginSite, PaymentMethod, Tariff, Vehicle, VehicleType
from apps.trips.models import Trip
from apps.users.models import User

EXPENSE_DESCRIPTIONS = [
    'Combustible', 'Peajes', 'Mantenimiento vehículo', 'Papelería',
    'Alimentación conductor', 'Lavado de vehículo', 'Imprevistos operativos',
]

CITY_NAMES = ['BOGOTÁ', 'MEDELLÍN']
ORIGIN_SITE_NAMES = ['Proyecto Norte', 'Proyecto Sur', 'Zona Industrial']
MATERIAL_TYPE_NAMES = ['Escombros', 'Material de excavación', 'Tierra negra', 'Lodo', 'Arena']
VEHICLE_TYPES = [('Volqueta Sencilla', Decimal('7.00')), ('Volqueta Doble', Decimal('15.00')), ('4 Manos', Decimal('20.00'))]
PAYMENT_METHODS = [('Efectivo', False), ('Transferencia', False), ('Anticipo', True)]
CLIENT_SEEDS = [
    ('CLIENTE DEMO 1', 'CLI1', '9001112223'),
    ('CLIENTE DEMO 2', 'CLI2', '9004445556'),
    ('CLIENTE DEMO 3', 'CLI3', '9007778889'),
]


def round_money(value) -> Decimal:
    return Decimal(value).quantize(Decimal('1'), rounding=ROUND_HALF_UP)


def generate_plaque(existing: set) -> str:
    while True:
        candidate = ''.join(random.choices(string.ascii_uppercase, k=3)) + ''.join(random.choices(string.digits, k=3))
        if candidate not in existing:
            existing.add(candidate)
            return candidate


class Command(BaseCommand):
    help = (
        'Genera datos históricos de prueba (viajes, anticipos consumidos, '
        'gastos, facturas y cierres de caja) reusando la lógica real del '
        'proyecto. Si no hay clientes/catálogos de masters, los crea desde '
        'cero (placas formato LLLNNN, sin pines). Requiere usuarios activos '
        'ya existentes — se recomienda correr clean_test_data antes.'
    )

    def add_arguments(self, parser):
        parser.add_argument('--days', type=int, default=60, help='Días hacia atrás a generar (default 60).')
        parser.add_argument('--seed', type=int, default=None, help='Semilla random para reproducibilidad.')

    def _ensure_catalog(self, admin_user, cashier_like):
        if not City.objects.exists():
            for name in CITY_NAMES:
                City.objects.create(name=name)
            self.stdout.write(f'  {len(CITY_NAMES)} ciudades creadas.')

        if not OriginSite.objects.exists():
            for name in ORIGIN_SITE_NAMES:
                OriginSite.objects.create(name=name)
            self.stdout.write(f'  {len(ORIGIN_SITE_NAMES)} sitios de origen creados.')

        if not MaterialType.objects.exists():
            for name in MATERIAL_TYPE_NAMES:
                MaterialType.objects.create(name=name)
            self.stdout.write(f'  {len(MATERIAL_TYPE_NAMES)} tipos de material creados.')

        if not VehicleType.objects.exists():
            for name, capacity in VEHICLE_TYPES:
                VehicleType.objects.create(name=name, capacity=capacity)
            self.stdout.write(f'  {len(VEHICLE_TYPES)} tipos de vehículo creados.')

        if not PaymentMethod.objects.exists():
            for name, is_advance in PAYMENT_METHODS:
                PaymentMethod.objects.create(name=name, is_advance=is_advance)
            self.stdout.write(f'  {len(PAYMENT_METHODS)} métodos de pago creados.')

        # Placas formato LLLNNN (3 letras + 3 números), sin pin asignado
        # (dumper=None) — la tabla de pines (PinsDumper) se deja vacía a
        # propósito, no se crea ningún registro ahí.
        if not Vehicle.objects.exists():
            vehicle_types = list(VehicleType.objects.all())
            existing_plaques = set(Vehicle.objects.values_list('plaque', flat=True))
            for _ in range(5):
                Vehicle.objects.create(
                    plaque=generate_plaque(existing_plaques),
                    vehicle_type=random.choice(vehicle_types),
                    dumper=None,
                )
            self.stdout.write('  5 vehículos creados (sin pin asignado).')

        if not Tariff.objects.exists():
            vehicle_types = list(VehicleType.objects.all())
            base_start = timezone.localdate() - timedelta(days=730)
            for vt in vehicle_types:
                Tariff.objects.create(
                    vehicle_type=vt, value=round_money(vt.capacity * Decimal('20000')),
                    start_date=base_start, state=True,
                )
            self.stdout.write(f'  {len(vehicle_types)} tarifas creadas.')

        if not Client.objects.exists():
            cities = list(City.objects.all())
            for name, abrev, nit in CLIENT_SEEDS:
                Client.objects.create(
                    user=random.choice(cashier_like), nit=nit, name=name, abrev_name=abrev,
                    address='CALLE FALSA 123', phone=random.randint(3000000000, 3199999999),
                    city=random.choice(cities) if cities else None,
                    facturation_name=name, email=f'{abrev.lower()}@example.com',
                    validate_certification=True, state=True,
                )
            self.stdout.write(f'  {len(CLIENT_SEEDS)} clientes creados.')

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError('DEBUG=False: este comando solo corre contra una base de desarrollo.')

        if options['seed'] is not None:
            random.seed(options['seed'])

        admin_user = User.objects.filter(role='superuser', state=True).order_by('id').first()
        cashier_like = list(User.objects.filter(state=True, role__in=['cashier', 'commercial_admin', 'superuser']))
        accountant_like = list(User.objects.filter(state=True, role__in=['accountant', 'superuser']))
        any_active_user = list(User.objects.filter(state=True))

        if admin_user is None or not any_active_user:
            raise CommandError(
                'No hay usuarios activos (se requiere al menos un superuser activo). '
                'Este comando no crea usuarios, solo clientes/catálogos/histórico.'
            )

        self.stdout.write('Verificando catálogos base...')
        self._ensure_catalog(admin_user, cashier_like or any_active_user)

        clients = list(Client.objects.filter(state=True))
        vehicles = list(Vehicle.objects.filter(vehicle_type__state=True))
        material_types = list(MaterialType.objects.filter(state=True))
        origin_sites = list(OriginSite.objects.filter(state=True))
        payment_methods = list(PaymentMethod.objects.filter(state=True))

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
                            client=client, user=random.choice(cashier_like or any_active_user), value=value_,
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
                user=random.choice(accountant_like or any_active_user), number=f'FAC-{invoice_seq:05d}',
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
            f'Listo. Clientes: {Client.objects.count()}, Vehículos: {Vehicle.objects.count()}, '
            f'Viajes: {Trip.objects.count()}, Anticipos: {Advance.objects.count()}, '
            f'Facturas: {Invoice.objects.count()}, Gastos: {Expense.objects.count()}, '
            f'Cierres de caja: {closed} (ya existentes/saltados: {skipped}).'
        ))
