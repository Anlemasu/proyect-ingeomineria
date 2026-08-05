import threading
from decimal import Decimal

from django.db import connection
from django.test import TestCase, TransactionTestCase
from django.utils import timezone

from apps.users.models import User
from apps.clients.models import Client
from apps.masters.models import VehicleType, Vehicle, MaterialType, PaymentMethod, OriginSite
from apps.trips.models import Trip
from .models import DailySummary
from .services import execute_close, AlreadyClosedError


def _build_common_fixtures():
    """Fixtures mínimas para poder crear un TRIP y correr un cierre.
    Se usa tanto en TestCase (transacción única) como en TransactionTestCase
    (cada llamada debe volver a crear todo porque las tablas se truncan
    entre tests)."""
    user = User.objects.create_user(
        username='super1', email='super1@test.com', name='Super',
        role='superuser', password='x12345',
    )
    owner = User.objects.create_user(
        username='owner1', email='owner1@test.com', name='Owner',
        role='commercial_admin', password='x12345',
    )
    client_obj = Client.objects.create(
        user=owner, nit='900123456', name='Cliente Test', abrev_name='CT',
        address='Calle 1', phone=3000000000,
    )
    vehicle_type = VehicleType.objects.create(name='Volqueta', capacity=Decimal('10.00'))
    vehicle = Vehicle.objects.create(vehicle_type=vehicle_type, plaque='ABC123')
    material = MaterialType.objects.create(name='Material Test')
    origin = OriginSite.objects.create(name='Origen Test')
    payment_cash = PaymentMethod.objects.create(name='Efectivo', is_advance=False)

    today = timezone.localdate()
    Trip.objects.create(
        payment=payment_cash, origin_site=origin, material_type=material,
        client=client_obj, vehicle=vehicle, voucher_num=1, value=Decimal('100000'),
        date_register=timezone.now(), date=today, state=True,
    )
    return today


class SequentialDoubleCloseTests(TestCase):
    """BUG 1: cerrar el mismo día dos veces (una tras otra) debe fallar
    limpio en el segundo intento y nunca duplicar el DailySummary."""

    def setUp(self):
        self.today = _build_common_fixtures()

    def test_second_close_raises_already_closed_and_no_duplicate_row(self):
        summary = execute_close(self.today, source='manual')
        self.assertEqual(DailySummary.objects.filter(date=self.today).count(), 1)

        with self.assertRaises(AlreadyClosedError):
            execute_close(self.today, source='manual')

        self.assertEqual(DailySummary.objects.filter(date=self.today).count(), 1)
        summary.refresh_from_db()
        self.assertEqual(summary.state, DailySummary.STATE_CLOSED)


class ConcurrentDoubleCloseRaceTests(TransactionTestCase):
    """
    Simula la condición de carrera real del BUG 1: dos requests de cierre
    (p. ej. un cajero cerrando manualmente justo cuando corre el cron de
    auto_close_cash) llegan casi al mismo tiempo para el mismo día.

    Se usa TransactionTestCase (no TestCase) porque los hilos necesitan
    conexiones de base de datos independientes que de verdad hagan commit;
    TestCase envuelve todo el test en una única transacción no confirmada,
    lo que no reproduce una carrera real entre conexiones distintas.

    La garantía que se prueba es la del índice único de DailySummary.date:
    sin importar el orden de llegada, la base de datos deja pasar un solo
    INSERT y el otro hilo debe recibir AlreadyClosedError (traducido desde
    IntegrityError), nunca una segunda fila.
    """

    def setUp(self):
        self.today = _build_common_fixtures()

    def test_only_one_of_two_concurrent_closes_succeeds(self):
        results = []
        start_barrier = threading.Barrier(2)

        def worker():
            start_barrier.wait()
            try:
                execute_close(self.today, source='manual')
                results.append('ok')
            except AlreadyClosedError:
                results.append('already_closed')
            except Exception as e:  # pragma: no cover - solo para diagnóstico si algo más falla
                results.append(f'error:{e!r}')
            finally:
                connection.close()

        t1 = threading.Thread(target=worker)
        t2 = threading.Thread(target=worker)
        t1.start()
        t2.start()
        t1.join(timeout=10)
        t2.join(timeout=10)

        self.assertEqual(sorted(results), ['already_closed', 'ok'], results)
        self.assertEqual(DailySummary.objects.filter(date=self.today).count(), 1)
