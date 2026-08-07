from decimal import Decimal

from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.users.models import User
from apps.clients.models import Client
from apps.masters.models import VehicleType, Vehicle, MaterialType, PaymentMethod, OriginSite
from apps.trips.models import Trip
from .models import Invoice


class InvoiceNumberUniquenessTests(TestCase):
    """FASE 5.2: Invoice.number ahora es unique=True. Crear una segunda
    factura con el mismo número debe fallar con un mensaje claro (400),
    nunca con un 500 por IntegrityError sin capturar."""

    def setUp(self):
        self.accountant = User.objects.create_user(
            username='acc1', email='acc1@test.com', name='Contador',
            role='accountant', password='x12345',
        )
        self.api = APIClient()
        self.api.force_authenticate(user=self.accountant)

    def test_duplicate_number_at_model_level_raises_integrity_error(self):
        Invoice.objects.create(user=self.accountant, number='FAC-100')
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Invoice.objects.create(user=self.accountant, number='FAC-100')

    def test_creating_second_invoice_with_same_number_via_api_returns_clear_400(self):
        resp1 = self.api.post('/api/invoices/', {'number': 'FAC-200'}, format='json')
        self.assertEqual(resp1.status_code, status.HTTP_201_CREATED, resp1.data)

        resp2 = self.api.post('/api/invoices/', {'number': 'FAC-200'}, format='json')
        self.assertEqual(resp2.status_code, status.HTTP_400_BAD_REQUEST, resp2.data)
        self.assertIn('ya existe', str(resp2.data).lower())

    def test_creating_second_invoice_with_same_number_lowercase_uppercased_by_model_save(self):
        # Invoice.save() uppercasea 'number' (uppercase_fields), así que
        # 'fac-300' y 'FAC-300' colisionan igual que si se mandaran iguales.
        resp1 = self.api.post('/api/invoices/', {'number': 'fac-300'}, format='json')
        self.assertEqual(resp1.status_code, status.HTTP_201_CREATED, resp1.data)

        resp2 = self.api.post('/api/invoices/', {'number': 'FAC-300'}, format='json')
        self.assertEqual(resp2.status_code, status.HTTP_400_BAD_REQUEST, resp2.data)


class InvoiceCreationRoleGateTests(TestCase):
    """FASE 6.4: quién puede registrar facturas (can_manage_invoices) no
    tenía ningún test — solo superuser/accountant."""

    def test_cashier_cannot_create_invoice(self):
        cashier = User.objects.create_user(
            username='cash1', email='cash1@test.com', name='Cajero',
            role='cashier', password='x12345',
        )
        api = APIClient()
        api.force_authenticate(user=cashier)

        resp = api.post('/api/invoices/', {'number': 'FAC-400'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN, resp.data)
        self.assertEqual(Invoice.objects.count(), 0)


class InvoiceTripAssignmentFixturesMixin:
    """8B.6: fixtures para probar la asociación atómica de viajes al crear
    (o reutilizar) una factura."""

    def setUp(self):
        self.accountant = User.objects.create_user(
            username='acc_inv1', email='acc_inv1@test.com', name='Contador',
            role='accountant', password='x12345',
        )
        self.owner_user = User.objects.create_user(
            username='owner_inv1', email='owner_inv1@test.com', name='Owner',
            role='commercial_admin', password='x12345',
        )
        self.client_obj = Client.objects.create(
            user=self.owner_user, nit='900555555', name='Cliente Facturación',
            abrev_name='CF', address='Calle 1', phone=3000000000,
        )
        vehicle_type = VehicleType.objects.create(name='Volqueta', capacity=Decimal('10.00'))
        self.vehicle = Vehicle.objects.create(vehicle_type=vehicle_type, plaque='INV123')
        self.material = MaterialType.objects.create(name='Material Test')
        self.origin = OriginSite.objects.create(name='Origen Test')
        self.payment_cash = PaymentMethod.objects.create(name='Efectivo', is_advance=False)
        self.today = timezone.localdate()

        self.api = APIClient()
        self.api.force_authenticate(user=self.accountant)
        self.trips_api = APIClient()
        self.trips_api.force_authenticate(user=self.owner_user)

    def _create_trip(self, value='100000'):
        resp = self.trips_api.post('/api/trips/', {
            'payment': self.payment_cash.id,
            'origin_site': self.origin.id,
            'material_type': self.material.id,
            'client': self.client_obj.id,
            'vehicle': self.vehicle.id,
            'value': value,
            'date': str(self.today),
        }, format='json')
        assert resp.status_code == status.HTTP_201_CREATED, resp.data
        return resp.data['id']


class InvoiceTripAssignmentAtomicityTests(InvoiceTripAssignmentFixturesMixin, TestCase):
    """8B.6 (diagnóstico de solo lectura): crear una factura y asociarle
    viajes no corría en una transacción única — antes era 1 POST /invoices/
    seguido de N PATCH /trips/<id>/ en paralelo, orquestados desde el
    frontend, sin ninguna transacción en común entre ellos. Ahora
    POST /invoices/ acepta `trip_ids` (factura nueva) o `invoice_id` +
    `trip_ids` (factura existente) y hace todo en un solo
    transaction.atomic()."""

    def test_new_invoice_with_trip_ids_associates_all_atomically(self):
        trip1 = self._create_trip('100000')
        trip2 = self._create_trip('200000')

        resp = self.api.post('/api/invoices/', {
            'number': 'FAC-ASSIGN-1',
            'trip_ids': [trip1, trip2],
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        invoice_id = resp.data['id']

        t1 = Trip.objects.get(pk=trip1)
        t2 = Trip.objects.get(pk=trip2)
        self.assertEqual(t1.invoice_id, invoice_id)
        self.assertEqual(t1.invoice_pos, 1)
        self.assertEqual(t2.invoice_id, invoice_id)
        self.assertEqual(t2.invoice_pos, 2)

    def test_trip_already_invoiced_rejects_whole_request_leaves_nothing_partial(self):
        trip1 = self._create_trip('100000')
        trip2 = self._create_trip('200000')

        first_resp = self.api.post('/api/invoices/', {
            'number': 'FAC-ASSIGN-2',
            'trip_ids': [trip1],
        }, format='json')
        self.assertEqual(first_resp.status_code, status.HTTP_201_CREATED, first_resp.data)

        # trip1 ya está facturado con FAC-ASSIGN-2 — este segundo intento
        # (factura nueva, trip1 + trip2) debe fallar por completo.
        resp = self.api.post('/api/invoices/', {
            'number': 'FAC-ASSIGN-3',
            'trip_ids': [trip1, trip2],
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST, resp.data)

        self.assertFalse(
            Invoice.objects.filter(number='FAC-ASSIGN-3').exists(),
            'no debe quedar una factura huérfana si la asignación de viajes falla',
        )
        t2 = Trip.objects.get(pk=trip2)
        self.assertIsNone(t2.invoice_id, 'trip2 no debe quedar parcialmente facturado')

    def test_adding_more_trips_to_an_existing_invoice(self):
        trip1 = self._create_trip('100000')
        create_resp = self.api.post('/api/invoices/', {
            'number': 'FAC-ASSIGN-4', 'trip_ids': [trip1],
        }, format='json')
        invoice_id = create_resp.data['id']

        trip2 = self._create_trip('150000')
        resp = self.api.post('/api/invoices/', {
            'invoice_id': invoice_id, 'trip_ids': [trip1, trip2],
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        self.assertEqual(Invoice.objects.count(), 1, 'no debe crear una factura nueva al reutilizar invoice_id')

        t2 = Trip.objects.get(pk=trip2)
        self.assertEqual(t2.invoice_id, invoice_id)

    def test_missing_trip_id_rejects_without_creating_invoice(self):
        resp = self.api.post('/api/invoices/', {
            'number': 'FAC-ASSIGN-5',
            'trip_ids': [999999],
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST, resp.data)
        self.assertFalse(Invoice.objects.filter(number='FAC-ASSIGN-5').exists())
