from decimal import Decimal

from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.users.models import User
from apps.clients.models import Client
from apps.masters.models import VehicleType, Vehicle, MaterialType, PaymentMethod, OriginSite
from apps.trips.models import Trip
from apps.advances.models import Advance
from .models import PhysicalCountEntry, PhysicalCountClosure
from .services import (
    register_entry,
    get_cumulative_entered,
    get_open_physical_reports,
    get_trips_on_other_advances,
    close_advance,
    undo_close_advance,
    reopen_advance,
    is_closed,
    ENTRY_ADJUSTMENT_WINDOW_MINUTES,
    ClosedTrackingError,
    JustificationRequiredError,
    NotClosedError,
    UndoWindowExpiredError,
)


class PhysicalReportsFixturesMixin:
    def setUp(self):
        self.superuser = User.objects.create_user(
            username='super1', email='super1@test.com', name='Super',
            role='superuser', password='x12345',
        )
        self.cashier = User.objects.create_user(
            username='cash1', email='cash1@test.com', name='Cajero',
            role='cashier', password='x12345',
        )
        self.auditor = User.objects.create_user(
            username='audit1', email='audit1@test.com', name='Auditor',
            role='auditor', password='x12345',
        )
        self.client_obj = Client.objects.create(
            user=self.superuser, nit='900123456', name='Cliente Test',
            abrev_name='CT', address='Calle 1', phone=3000000000,
        )
        self.today = timezone.localdate()
        self.advance = Advance.objects.create(
            client=self.client_obj, user=self.superuser, value=Decimal('1000000'),
            transfer_num=1, date=self.today, expected_trips_quantity=10,
        )

        self.cashier_api = APIClient()
        self.cashier_api.force_authenticate(user=self.cashier)
        self.auditor_api = APIClient()
        self.auditor_api.force_authenticate(user=self.auditor)


class RegisterEntryServiceTests(PhysicalReportsFixturesMixin, TestCase):
    def test_first_entry_for_a_date_does_not_require_justification(self):
        entry = register_entry(self.advance, date=self.today, count=4, user=self.cashier)
        self.assertEqual(entry.count, 4)
        self.assertEqual(get_cumulative_entered(self.advance), 4)

    def test_correcting_within_adjustment_window_does_not_require_justification(self):
        # Dentro de la ventana de ajuste rápido (30 min), el campo se trata
        # como si siguiera "abierto": no hace falta justificar.
        register_entry(self.advance, date=self.today, count=4, user=self.cashier)
        entry = register_entry(self.advance, date=self.today, count=6, user=self.cashier)
        self.assertEqual(entry.count, 6)
        self.assertEqual(get_cumulative_entered(self.advance), 6)

    def test_correcting_after_adjustment_window_without_justification_fails(self):
        first = register_entry(self.advance, date=self.today, count=4, user=self.cashier)
        PhysicalCountEntry.objects.filter(pk=first.pk).update(
            created_at=timezone.now() - timezone.timedelta(minutes=ENTRY_ADJUSTMENT_WINDOW_MINUTES + 1)
        )
        with self.assertRaises(JustificationRequiredError):
            register_entry(self.advance, date=self.today, count=6, user=self.cashier)

    def test_correcting_after_adjustment_window_with_justification_creates_a_new_entry(self):
        first = register_entry(self.advance, date=self.today, count=4, user=self.cashier)
        PhysicalCountEntry.objects.filter(pk=first.pk).update(
            created_at=timezone.now() - timezone.timedelta(minutes=ENTRY_ADJUSTMENT_WINDOW_MINUTES + 1)
        )
        register_entry(
            self.advance, date=self.today, count=6, user=self.cashier,
            justification='Se contaron 2 vales más al final del día.',
        )
        # El acumulado usa el VIGENTE (el último), no la suma de ambos.
        self.assertEqual(get_cumulative_entered(self.advance), 6)
        self.assertEqual(PhysicalCountEntry.objects.filter(advance=self.advance).count(), 2)

    def test_resaving_the_same_count_is_a_noop(self):
        # "Guardar todos" puede reenviar filas que no se tocaron: no debe
        # crear un registro duplicado ni exigir justificación por nada.
        first = register_entry(self.advance, date=self.today, count=4, user=self.cashier)
        again = register_entry(self.advance, date=self.today, count=4, user=self.cashier)
        self.assertEqual(first.id, again.id)
        self.assertEqual(PhysicalCountEntry.objects.filter(advance=self.advance).count(), 1)

    def test_entries_on_different_dates_accumulate(self):
        yesterday = self.today - timezone.timedelta(days=1)
        register_entry(self.advance, date=yesterday, count=4, user=self.cashier)
        register_entry(self.advance, date=self.today, count=2, user=self.cashier)
        self.assertEqual(get_cumulative_entered(self.advance), 6)

    def test_cumulative_as_of_a_past_date_excludes_later_entries(self):
        yesterday = self.today - timezone.timedelta(days=1)
        register_entry(self.advance, date=yesterday, count=4, user=self.cashier)
        register_entry(self.advance, date=self.today, count=2, user=self.cashier)
        self.assertEqual(get_cumulative_entered(self.advance, as_of_date=yesterday), 4)
        self.assertEqual(get_cumulative_entered(self.advance), 6)

    def test_closed_advance_rejects_new_entries(self):
        close_advance(self.advance, self.cashier)
        with self.assertRaises(ClosedTrackingError):
            register_entry(self.advance, date=self.today, count=1, user=self.cashier)


class OpenPhysicalReportsListTests(PhysicalReportsFixturesMixin, TestCase):
    def test_advance_with_remaining_trips_appears_in_open_list(self):
        register_entry(self.advance, date=self.today, count=4, user=self.cashier)
        rows = get_open_physical_reports()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['remaining'], 6)

    def test_advance_with_quota_fully_reached_disappears_automatically(self):
        register_entry(self.advance, date=self.today, count=10, user=self.cashier)
        rows = get_open_physical_reports()
        self.assertEqual(rows, [])

    def test_manually_closed_advance_disappears_even_with_remaining_trips(self):
        register_entry(self.advance, date=self.today, count=4, user=self.cashier)
        close_advance(self.advance, self.cashier)
        rows = get_open_physical_reports()
        self.assertEqual(rows, [])

    def test_active_advance_without_quota_or_entries_still_appears(self):
        # Un anticipo activo sin cupo definido y sin ningún conteo todavía
        # debe poder encontrarse en "Pendientes" para poder usar "Definir
        # cupo" por primera vez — si no apareciera aquí, nunca habría forma
        # de llegar a él desde la pantalla.
        Advance.objects.filter(pk=self.advance.pk).update(expected_trips_quantity=None)
        self.advance.refresh_from_db()
        rows = get_open_physical_reports()
        self.assertEqual(len(rows), 1)
        self.assertIsNone(rows[0]['expected_trips_quantity'])
        self.assertIsNone(rows[0]['remaining'])

    def test_frozen_advance_without_quota_or_entries_does_not_appear(self):
        # A diferencia del activo, un anticipo YA CONGELADO (reemplazado por
        # uno más nuevo del mismo cliente) sin cupo ni conteos no tiene nada
        # que reconciliar todavía, así que no debe listarse.
        Advance.objects.filter(pk=self.advance.pk).update(expected_trips_quantity=None)
        newer = Advance.objects.create(
            client=self.client_obj, user=self.cashier, value=Decimal('500000'),
            transfer_num=2, date=self.today,
        )
        rows = get_open_physical_reports()
        advance_ids = [r['advance'].id for r in rows]
        self.assertNotIn(self.advance.id, advance_ids)
        self.assertIn(newer.id, advance_ids)  # el nuevo SÍ es candidato: es el activo


class ClosureServiceTests(PhysicalReportsFixturesMixin, TestCase):
    def test_undo_close_immediately_reopens_without_justification(self):
        close_advance(self.advance, self.cashier)
        undo_close_advance(self.advance, self.cashier)
        self.assertFalse(is_closed(self.advance))

    def test_undo_close_by_a_different_user_is_rejected(self):
        close_advance(self.advance, self.cashier)
        with self.assertRaises(UndoWindowExpiredError):
            undo_close_advance(self.advance, self.superuser)

    def test_reopen_without_justification_fails(self):
        close_advance(self.advance, self.cashier)
        with self.assertRaises(JustificationRequiredError):
            reopen_advance(self.advance, self.cashier, '')

    def test_reopen_with_justification_succeeds_even_long_after_closing(self):
        closure = close_advance(self.advance, self.cashier)
        PhysicalCountClosure.objects.filter(pk=closure.pk).update(
            created_at=timezone.now() - timezone.timedelta(days=5)
        )
        reopen_advance(self.advance, self.cashier, 'Se necesita seguir contando: quedaban vales por confirmar.')
        self.assertFalse(is_closed(self.advance))

    def test_cannot_close_an_already_closed_advance(self):
        close_advance(self.advance, self.cashier)
        with self.assertRaises(ClosedTrackingError):
            close_advance(self.advance, self.cashier)

    def test_cannot_reopen_an_advance_that_is_not_closed(self):
        with self.assertRaises(NotClosedError):
            reopen_advance(self.advance, self.cashier, 'justificación')


class PhysicalReportEndpointPermissionTests(PhysicalReportsFixturesMixin, TestCase):
    def test_auditor_can_list_but_not_register_entries(self):
        list_response = self.auditor_api.get('/api/physical-reports/')
        self.assertEqual(list_response.status_code, status.HTTP_200_OK)

        post_response = self.auditor_api.post(
            f'/api/physical-reports/{self.advance.id}/entries/',
            {'date': str(self.today), 'count': 4}, format='json',
        )
        self.assertEqual(post_response.status_code, status.HTTP_403_FORBIDDEN)

    def test_cashier_can_register_entries(self):
        response = self.cashier_api.post(
            f'/api/physical-reports/{self.advance.id}/entries/',
            {'date': str(self.today), 'count': 4}, format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)


class BulkEntryEndpointTests(PhysicalReportsFixturesMixin, TestCase):
    def test_bulk_save_registers_all_valid_entries_in_one_request(self):
        other_advance = Advance.objects.create(
            client=self.client_obj, user=self.superuser, value=Decimal('500000'),
            transfer_num=2, date=self.today - timezone.timedelta(days=1),
            expected_trips_quantity=5,
        )
        response = self.cashier_api.post(
            '/api/physical-reports/bulk-entries/',
            {
                'date': str(self.today),
                'entries': [
                    {'advance': self.advance.id, 'count': 3},
                    {'advance': other_advance.id, 'count': 2},
                ],
            },
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        statuses = {r['advance']: r['status'] for r in response.data}
        self.assertEqual(statuses, {self.advance.id: 'ok', other_advance.id: 'ok'})
        self.assertEqual(get_cumulative_entered(self.advance), 3)
        self.assertEqual(get_cumulative_entered(other_advance), 2)

    def test_bulk_save_reports_per_row_errors_without_failing_the_rest(self):
        close_advance(self.advance, self.cashier)
        other_advance = Advance.objects.create(
            client=self.client_obj, user=self.superuser, value=Decimal('500000'),
            transfer_num=2, date=self.today - timezone.timedelta(days=1),
            expected_trips_quantity=5,
        )
        response = self.cashier_api.post(
            '/api/physical-reports/bulk-entries/',
            {
                'date': str(self.today),
                'entries': [
                    {'advance': self.advance.id, 'count': 3},  # cerrado: debe fallar
                    {'advance': other_advance.id, 'count': 2},  # debe pasar igual
                ],
            },
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        statuses = {r['advance']: r['status'] for r in response.data}
        self.assertEqual(statuses, {self.advance.id: 'error', other_advance.id: 'ok'})

    def test_auditor_cannot_bulk_save(self):
        response = self.auditor_api.post(
            '/api/physical-reports/bulk-entries/',
            {'date': str(self.today), 'entries': [{'advance': self.advance.id, 'count': 1}]},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class CrossAdvanceValidationTests(PhysicalReportsFixturesMixin, TestCase):
    """
    Bug reportado: un cliente con dos anticipos visibles en Reporte Físico
    (el activo + uno congelado que seguía abierto) — los viajes del día se
    descontaron contra UNO, pero el conteo físico se cargó en el OTRO. Ese
    anticipo mostraba "0 viajes en el sistema" sin ninguna pista de que en
    realidad sí existían, solo que en el otro anticipo del mismo cliente.
    get_trips_on_other_advances / PhysicalReportDetailView.day_detail
    ahora detectan y avisan este caso.
    """

    def setUp(self):
        super().setUp()
        self.vehicle_type = VehicleType.objects.create(name='Volqueta', capacity=Decimal('10.00'))
        self.vehicle = Vehicle.objects.create(vehicle_type=self.vehicle_type, plaque='XYZ999')
        self.material = MaterialType.objects.create(name='Material Test')
        self.origin = OriginSite.objects.create(name='Origen Test')
        self.payment_advance = PaymentMethod.objects.create(name='Anticipo', is_advance=True)

    def _create_trip(self, *, advance, voucher_num):
        return Trip.objects.create(
            payment=self.payment_advance, origin_site=self.origin, material_type=self.material,
            client=self.client_obj, vehicle=self.vehicle, advance=advance,
            voucher_num=voucher_num, value=Decimal('100000'),
            date_register=timezone.now(), date=self.today,
        )

    def test_detects_trips_linked_to_a_different_advance_of_the_same_client(self):
        # self.advance queda CONGELADO en cuanto se crea el segundo anticipo
        # (get_active_advance del cliente pasa a ser `newer`).
        newer = Advance.objects.create(
            client=self.client_obj, user=self.superuser, value=Decimal('500000'),
            transfer_num=2, date=self.today,
        )
        self._create_trip(advance=newer, voucher_num=501)
        self._create_trip(advance=newer, voucher_num=502)

        other_trips = get_trips_on_other_advances(self.advance, self.today)
        self.assertEqual(len(other_trips), 2)
        self.assertEqual({t.advance_id for t in other_trips}, {newer.id})

    def test_no_warning_when_all_trips_belong_to_this_advance(self):
        self._create_trip(advance=self.advance, voucher_num=601)
        other_trips = get_trips_on_other_advances(self.advance, self.today)
        self.assertEqual(other_trips, [])

    def test_detail_endpoint_surfaces_the_cross_advance_warning(self):
        newer = Advance.objects.create(
            client=self.client_obj, user=self.superuser, value=Decimal('500000'),
            transfer_num=2, date=self.today,
        )
        self._create_trip(advance=newer, voucher_num=701)
        self._create_trip(advance=newer, voucher_num=702)
        self._create_trip(advance=newer, voucher_num=703)

        response = self.cashier_api.get(
            f'/api/physical-reports/{self.advance.id}/', {'date': str(self.today)},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        day_detail = response.data['day_detail']
        self.assertEqual(day_detail['system_count'], 0)  # correcto PARA ESTE anticipo
        self.assertEqual(day_detail['other_advance_trips_count'], 3)
        self.assertEqual(day_detail['other_advance_ids'], [newer.id])
        # self.advance ya no es el activo del cliente: `newer` lo reemplazó.
        self.assertFalse(response.data['is_active'])


class ActiveAdvanceFlagTests(PhysicalReportsFixturesMixin, TestCase):
    def test_single_advance_is_flagged_active(self):
        rows = get_open_physical_reports()
        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0]['is_active'])

    def test_frozen_advance_is_flagged_inactive_once_a_newer_one_exists(self):
        newer = Advance.objects.create(
            client=self.client_obj, user=self.superuser, value=Decimal('500000'),
            transfer_num=2, date=self.today, expected_trips_quantity=5,
        )
        rows = {r['advance'].id: r for r in get_open_physical_reports()}
        self.assertFalse(rows[self.advance.id]['is_active'])
        self.assertTrue(rows[newer.id]['is_active'])
