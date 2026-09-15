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
from .models import Certificate


class CertificateNumberUniquenessTests(TestCase):
    """Mismo patrón que InvoiceNumberUniquenessTests (apps/invoices/tests.py):
    Certificate.number es unique=True, crear un segundo certificado con el
    mismo número debe fallar con un 400 claro, nunca con un 500 sin capturar."""

    def setUp(self):
        self.certifier = User.objects.create_user(
            username='cert1', email='cert1@test.com', name='Certificador',
            role='certifier', password='x12345',
        )
        self.api = APIClient()
        self.api.force_authenticate(user=self.certifier)

    def test_duplicate_number_at_model_level_raises_integrity_error(self):
        Certificate.objects.create(user=self.certifier, number='CERT-100')
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Certificate.objects.create(user=self.certifier, number='CERT-100')

    def test_creating_second_certificate_with_same_number_via_api_returns_clear_400(self):
        resp1 = self.api.post('/api/certificates/', {'number': 'CERT-200'}, format='json')
        self.assertEqual(resp1.status_code, status.HTTP_201_CREATED, resp1.data)

        resp2 = self.api.post('/api/certificates/', {'number': 'CERT-200'}, format='json')
        self.assertEqual(resp2.status_code, status.HTTP_400_BAD_REQUEST, resp2.data)
        self.assertIn('ya existe', str(resp2.data).lower())

    def test_creating_second_certificate_with_same_number_lowercase_uppercased_by_model_save(self):
        # Certificate.save() uppercasea 'number' (uppercase_fields), así que
        # 'cert-300' y 'CERT-300' colisionan igual que si se mandaran iguales.
        resp1 = self.api.post('/api/certificates/', {'number': 'cert-300'}, format='json')
        self.assertEqual(resp1.status_code, status.HTTP_201_CREATED, resp1.data)

        resp2 = self.api.post('/api/certificates/', {'number': 'CERT-300'}, format='json')
        self.assertEqual(resp2.status_code, status.HTTP_400_BAD_REQUEST, resp2.data)


class CertificateCreationRoleGateTests(TestCase):
    """Quién puede registrar certificados (can_manage_certificates): solo
    superuser/certifier."""

    def test_cashier_cannot_create_certificate(self):
        cashier = User.objects.create_user(
            username='cash_cert1', email='cash_cert1@test.com', name='Cajero',
            role='cashier', password='x12345',
        )
        api = APIClient()
        api.force_authenticate(user=cashier)

        resp = api.post('/api/certificates/', {'number': 'CERT-400'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN, resp.data)
        self.assertEqual(Certificate.objects.count(), 0)

    def test_accountant_cannot_create_certificate(self):
        # El rol de facturación (accountant) no gestiona certificados de
        # disposición final — son roles y flujos independientes.
        accountant = User.objects.create_user(
            username='acc_cert1', email='acc_cert1@test.com', name='Contador',
            role='accountant', password='x12345',
        )
        api = APIClient()
        api.force_authenticate(user=accountant)

        resp = api.post('/api/certificates/', {'number': 'CERT-401'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN, resp.data)


class CertificateTripAssignmentFixturesMixin:
    """Fixtures para probar la asociación atómica de viajes al crear (o
    reutilizar) un certificado. Mismo patrón que
    InvoiceTripAssignmentFixturesMixin (apps/invoices/tests.py)."""

    def setUp(self):
        self.certifier = User.objects.create_user(
            username='certifier_cert1', email='certifier_cert1@test.com', name='Certificador',
            role='certifier', password='x12345',
        )
        self.owner_user = User.objects.create_user(
            username='owner_cert1', email='owner_cert1@test.com', name='Owner',
            role='commercial_admin', password='x12345',
        )
        self.client_obj = Client.objects.create(
            user=self.owner_user, nit='900666666', name='Cliente Certificación',
            abrev_name='CC', address='Calle 1', phone=3000000000,
        )
        vehicle_type = VehicleType.objects.create(name='Volqueta', capacity=Decimal('10.00'))
        self.vehicle = Vehicle.objects.create(vehicle_type=vehicle_type, plaque='CRT123')
        self.material = MaterialType.objects.create(name='Material Test')
        self.origin = OriginSite.objects.create(name='Origen Test')
        self.payment_cash = PaymentMethod.objects.create(name='Efectivo', is_advance=False)
        self.today = timezone.localdate()

        self.api = APIClient()
        self.api.force_authenticate(user=self.certifier)
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


class CertificateTripAssignmentAtomicityTests(CertificateTripAssignmentFixturesMixin, TestCase):
    """Crear un certificado y asociarle viajes corre en una sola transacción
    atómica (mismo patrón que la facturación, ver 8B.6)."""

    def test_new_certificate_with_trip_ids_associates_all_atomically(self):
        trip1 = self._create_trip('100000')
        trip2 = self._create_trip('200000')

        resp = self.api.post('/api/certificates/', {
            'number': 'CERT-ASSIGN-1',
            'trip_ids': [trip1, trip2],
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        certificate_id = resp.data['id']

        t1 = Trip.objects.get(pk=trip1)
        t2 = Trip.objects.get(pk=trip2)
        self.assertEqual(t1.certificate_id, certificate_id)
        self.assertEqual(t1.certificate_pos, 1)
        self.assertEqual(t2.certificate_id, certificate_id)
        self.assertEqual(t2.certificate_pos, 2)

    def test_trip_already_certified_rejects_whole_request_leaves_nothing_partial(self):
        trip1 = self._create_trip('100000')
        trip2 = self._create_trip('200000')

        first_resp = self.api.post('/api/certificates/', {
            'number': 'CERT-ASSIGN-2',
            'trip_ids': [trip1],
        }, format='json')
        self.assertEqual(first_resp.status_code, status.HTTP_201_CREATED, first_resp.data)

        # trip1 ya está certificado con CERT-ASSIGN-2 — este segundo intento
        # (certificado nuevo, trip1 + trip2) debe fallar por completo.
        resp = self.api.post('/api/certificates/', {
            'number': 'CERT-ASSIGN-3',
            'trip_ids': [trip1, trip2],
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST, resp.data)

        self.assertFalse(
            Certificate.objects.filter(number='CERT-ASSIGN-3').exists(),
            'no debe quedar un certificado huérfano si la asignación de viajes falla',
        )
        t2 = Trip.objects.get(pk=trip2)
        self.assertIsNone(t2.certificate_id, 'trip2 no debe quedar parcialmente certificado')

    def test_adding_more_trips_to_an_existing_certificate(self):
        trip1 = self._create_trip('100000')
        create_resp = self.api.post('/api/certificates/', {
            'number': 'CERT-ASSIGN-4', 'trip_ids': [trip1],
        }, format='json')
        certificate_id = create_resp.data['id']

        trip2 = self._create_trip('150000')
        resp = self.api.post('/api/certificates/', {
            'certificate_id': certificate_id, 'trip_ids': [trip1, trip2],
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        self.assertEqual(Certificate.objects.count(), 1, 'no debe crear un certificado nuevo al reutilizar certificate_id')

        t2 = Trip.objects.get(pk=trip2)
        self.assertEqual(t2.certificate_id, certificate_id)

    def test_missing_trip_id_rejects_without_creating_certificate(self):
        resp = self.api.post('/api/certificates/', {
            'number': 'CERT-ASSIGN-5',
            'trip_ids': [999999],
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST, resp.data)
        self.assertFalse(Certificate.objects.filter(number='CERT-ASSIGN-5').exists())


class CertificateUnlinkFromTripTests(CertificateTripAssignmentFixturesMixin, TestCase):
    """Desvincular un certificado de un viaje (PATCH /trips/<id>/ con
    certificate=null) es una operación separada de can_update_trips, igual
    que desvincular una factura (ver can_unlink_certificate en
    apps/trips/views.py)."""

    def test_certifier_can_unlink_certificate(self):
        trip1 = self._create_trip('100000')
        self.api.post('/api/certificates/', {
            'number': 'CERT-UNLINK-1', 'trip_ids': [trip1],
        }, format='json')

        resp = self.api.patch(f'/api/trips/{trip1}/', {'certificate': None}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)

        t1 = Trip.objects.get(pk=trip1)
        self.assertIsNone(t1.certificate_id)
        self.assertIsNone(t1.certificate_pos)

    def test_cashier_cannot_unlink_certificate(self):
        trip1 = self._create_trip('100000')
        self.api.post('/api/certificates/', {
            'number': 'CERT-UNLINK-2', 'trip_ids': [trip1],
        }, format='json')

        cashier = User.objects.create_user(
            username='cash_cert2', email='cash_cert2@test.com', name='Cajero',
            role='cashier', password='x12345',
        )
        cashier_api = APIClient()
        cashier_api.force_authenticate(user=cashier)

        resp = cashier_api.patch(f'/api/trips/{trip1}/', {'certificate': None}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN, resp.data)

        t1 = Trip.objects.get(pk=trip1)
        self.assertIsNotNone(t1.certificate_id, 'no debe desvincularse sin permisos')

    def test_accountant_cannot_unlink_certificate(self):
        # accountant gestiona facturas (can_unlink_invoice), no certificados.
        trip1 = self._create_trip('100000')
        self.api.post('/api/certificates/', {
            'number': 'CERT-UNLINK-3', 'trip_ids': [trip1],
        }, format='json')

        accountant = User.objects.create_user(
            username='acc_cert2', email='acc_cert2@test.com', name='Contador',
            role='accountant', password='x12345',
        )
        accountant_api = APIClient()
        accountant_api.force_authenticate(user=accountant)

        resp = accountant_api.patch(f'/api/trips/{trip1}/', {'certificate': None}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN, resp.data)
