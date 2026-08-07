from decimal import Decimal

from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.users.models import User
from apps.clients.models import Client
from apps.audit.models import AuditLog
from .models import VehicleType, Tariff


class TariffFixturesMixin:
    def setUp(self):
        self.superuser = User.objects.create_user(
            username='super_tar1', email='super_tar1@test.com', name='Super',
            role='superuser', password='x12345',
        )
        self.cashier = User.objects.create_user(
            username='cash_tar1', email='cash_tar1@test.com', name='Cajero',
            role='cashier', password='x12345',
        )
        self.client_obj = Client.objects.create(
            user=self.superuser, nit='900888888', name='Cliente Tarifas',
            abrev_name='CT', address='Calle 1', phone=3000000000,
        )
        self.vehicle_type = VehicleType.objects.create(name='Volqueta', capacity=Decimal('10.00'))
        self.today = timezone.localdate()

        self.api = APIClient()
        self.api.force_authenticate(user=self.superuser)
        self.cashier_api = APIClient()
        self.cashier_api.force_authenticate(user=self.cashier)


class TariffCreationValidationTests(TariffFixturesMixin, TestCase):
    """8B.5 (diagnóstico de solo lectura): el descarte silencioso de
    tarifas inválidas vivía en el frontend (TariffsPage.vue), no en el
    backend — el backend en sí ya rechazaba valores <= 0 con un 400
    explícito. Estos tests confirman ese comportamiento del backend, que
    es la base sobre la que se apoya el fix del frontend."""

    def test_zero_value_tariff_is_rejected_with_clear_error(self):
        resp = self.api.post('/api/masters/tariffs/', {
            'client': self.client_obj.id, 'vehicle_type': self.vehicle_type.id,
            'value': '0', 'start_date': str(self.today),
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST, resp.data)
        self.assertIn('mayor a cero', str(resp.data).lower())
        self.assertFalse(Tariff.objects.exists())

    def test_negative_value_tariff_is_rejected(self):
        resp = self.api.post('/api/masters/tariffs/', {
            'client': self.client_obj.id, 'vehicle_type': self.vehicle_type.id,
            'value': '-5000', 'start_date': str(self.today),
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST, resp.data)
        self.assertFalse(Tariff.objects.exists())

    def test_cashier_cannot_create_tariff(self):
        resp = self.cashier_api.post('/api/masters/tariffs/', {
            'client': self.client_obj.id, 'vehicle_type': self.vehicle_type.id,
            'value': '50000', 'start_date': str(self.today),
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN, resp.data)


class TariffDeleteFallsBackToGeneralTests(TariffFixturesMixin, TestCase):
    """8B.5: nuevo DELETE /masters/tariffs/<id>/ — elimina (soft-delete)
    una tarifa personalizada de cliente SIN reemplazo, para que ese
    cliente vuelva a usar la tarifa general. Distinto de PATCH (RF-21),
    que siempre cierra la vieja Y crea una nueva."""

    def setUp(self):
        super().setUp()
        create_resp = self.api.post('/api/masters/tariffs/', {
            'client': self.client_obj.id, 'vehicle_type': self.vehicle_type.id,
            'value': '80000', 'start_date': str(self.today),
        }, format='json')
        assert create_resp.status_code == status.HTTP_201_CREATED, create_resp.data
        self.tariff_id = create_resp.data['id']

    def test_superuser_can_delete_tariff_and_it_becomes_inactive(self):
        resp = self.api.delete(f'/api/masters/tariffs/{self.tariff_id}/')
        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT, resp.data)

        tariff = Tariff.objects.get(pk=self.tariff_id)
        self.assertFalse(tariff.state)
        self.assertEqual(tariff.end_date, self.today)

        self.assertTrue(
            AuditLog.objects.filter(action='delete', model_name='Tariff', object_id=self.tariff_id).exists()
        )

    def test_no_replacement_tariff_is_created(self):
        self.api.delete(f'/api/masters/tariffs/{self.tariff_id}/')
        active_for_client = Tariff.objects.filter(
            client=self.client_obj, vehicle_type=self.vehicle_type, state=True
        )
        self.assertEqual(active_for_client.count(), 0, 'no debe crearse ninguna tarifa de reemplazo')

    def test_cashier_cannot_delete_tariff(self):
        resp = self.cashier_api.delete(f'/api/masters/tariffs/{self.tariff_id}/')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN, resp.data)
        tariff = Tariff.objects.get(pk=self.tariff_id)
        self.assertTrue(tariff.state)

    def test_deleting_already_inactive_tariff_is_rejected(self):
        self.api.delete(f'/api/masters/tariffs/{self.tariff_id}/')
        resp2 = self.api.delete(f'/api/masters/tariffs/{self.tariff_id}/')
        self.assertEqual(resp2.status_code, status.HTTP_400_BAD_REQUEST, resp2.data)
