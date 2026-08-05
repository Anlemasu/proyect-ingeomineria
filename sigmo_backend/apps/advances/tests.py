from decimal import Decimal

from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.users.models import User
from apps.clients.models import Client
from apps.masters.models import VehicleType, Vehicle, MaterialType, PaymentMethod, OriginSite
from apps.trips.models import Trip
from apps.audit.models import AuditLog
from .models import Advance, AdvanceMovement
from .services import get_available_balance


class PendingDebtFixturesMixin:
    """
    FASE 3: fixtures para probar "anticipo activo + deuda pendiente".
    A diferencia de trips/tests.py::TripAdvanceFixturesMixin, aquí NO se
    crea ningún Advance en setUp — cada test crea los que necesita a través
    de la API, porque lo que se está probando es precisamente el orden y
    los efectos de crear varios anticipos para el mismo cliente.
    """

    def setUp(self):
        self.superuser = User.objects.create_user(
            username='super1', email='super1@test.com', name='Super',
            role='superuser', password='x12345',
        )
        self.cashier = User.objects.create_user(
            username='cash1', email='cash1@test.com', name='Cajero',
            role='cashier', password='x12345',
        )
        self.owner_user = User.objects.create_user(
            username='owner1', email='owner1@test.com', name='Owner',
            role='commercial_admin', password='x12345',
        )
        self.client_obj = Client.objects.create(
            user=self.owner_user, nit='900123456', name='Cliente Test',
            abrev_name='CT', address='Calle 1', phone=3000000000,
        )
        self.vehicle_type = VehicleType.objects.create(name='Volqueta', capacity=Decimal('10.00'))
        self.vehicle = Vehicle.objects.create(vehicle_type=self.vehicle_type, plaque='ABC123')
        self.material = MaterialType.objects.create(name='Material Test')
        self.origin = OriginSite.objects.create(name='Origen Test')
        self.payment_advance = PaymentMethod.objects.create(name='Anticipo', is_advance=True)
        self.payment_cash = PaymentMethod.objects.create(name='Efectivo', is_advance=False)
        self.today = timezone.localdate()

        self.api = APIClient()
        self.api.force_authenticate(user=self.superuser)
        self.cashier_api = APIClient()
        self.cashier_api.force_authenticate(user=self.cashier)

        self._transfer_num = 0

    def _create_advance(self, value, *, api=None):
        api = api or self.api
        self._transfer_num += 1
        return api.post('/api/advances/', {
            'client': self.client_obj.id,
            'value': str(value),
            'transfer_num': self._transfer_num,
            'date': str(self.today),
        }, format='json')

    def _create_trip(self, value, *, api=None, justification=None, date=None):
        api = api or self.api
        payload = {
            'payment': self.payment_advance.id,
            'origin_site': self.origin.id,
            'material_type': self.material.id,
            'client': self.client_obj.id,
            'vehicle': self.vehicle.id,
            'value': str(value),
            'date': str(date or self.today),
        }
        if justification:
            payload['justification'] = justification
        return api.post('/api/trips/', payload, format='json')


class SequentialAdvanceSettlementTests(PendingDebtFixturesMixin, TestCase):
    """Casos 1-2 del enunciado: descuento normal contra el anticipo activo,
    y deuda pendiente cuando no alcanza."""

    def test_trip_settles_against_advance_with_sufficient_balance(self):
        resp_a = self._create_advance(1000000)
        self.assertEqual(resp_a.status_code, status.HTTP_201_CREATED, resp_a.data)
        advance_a_id = resp_a.data['id']

        trip_resp = self._create_trip(300000)
        self.assertEqual(trip_resp.status_code, status.HTTP_201_CREATED, trip_resp.data)
        self.assertEqual(trip_resp.data['advance'], advance_a_id)
        self.assertFalse(trip_resp.data['is_pending_debt'])

        self.assertEqual(
            get_available_balance(Advance.objects.get(pk=advance_a_id)),
            Decimal('700000'),
        )

    def test_trip_becomes_pending_debt_when_advance_insufficient(self):
        resp_a = self._create_advance(100000)
        advance_a_id = resp_a.data['id']

        # Sin justificación: rechazado.
        resp_no_just = self._create_trip(300000)
        self.assertEqual(resp_no_just.status_code, status.HTTP_400_BAD_REQUEST, resp_no_just.data)

        # Con justificación: se guarda como deuda pendiente, sin tocar A.
        resp_trip = self._create_trip(300000, justification='Anticipo insuficiente, cliente autoriza')
        self.assertEqual(resp_trip.status_code, status.HTTP_201_CREATED, resp_trip.data)
        self.assertIsNone(resp_trip.data['advance'])
        self.assertTrue(resp_trip.data['is_pending_debt'])

        self.assertEqual(
            get_available_balance(Advance.objects.get(pk=advance_a_id)),
            Decimal('100000'),
            'el anticipo activo no debe tocarse si el viaje queda pendiente',
        )
        self.assertFalse(AdvanceMovement.objects.filter(trip_id=resp_trip.data['id']).exists())


class PendingDebtSettlementOnNewAdvanceTests(PendingDebtFixturesMixin, TestCase):
    """Casos 3-4: liquidación automática FIFO al crear un anticipo nuevo."""

    def test_new_advance_settles_single_pending_debt(self):
        self._create_advance(100000)  # A: no alcanza para lo que sigue
        trip_resp = self._create_trip(300000, justification='Sin saldo suficiente')
        trip_id = trip_resp.data['id']

        resp_b = self._create_advance(500000)  # B
        advance_b_id = resp_b.data['id']

        trip = Trip.objects.get(pk=trip_id)
        self.assertEqual(trip.advance_id, advance_b_id)
        self.assertTrue(
            AdvanceMovement.objects.filter(
                advance_id=advance_b_id, trip_id=trip_id, type_movement='egreso', amount=Decimal('300000')
            ).exists()
        )
        self.assertEqual(
            get_available_balance(Advance.objects.get(pk=advance_b_id)),
            Decimal('200000'),  # 500000 - 300000
        )
        self.assertTrue(
            AuditLog.objects.filter(action='update', model_name='Trip', object_id=trip_id).exists()
        )

    def test_two_pending_debts_settled_strictly_fifo(self):
        resp1 = self._create_trip(300000, justification='Deuda 1 (más antigua)')
        trip1_id = resp1.data['id']
        resp2 = self._create_trip(200000, justification='Deuda 2 (más nueva)')
        trip2_id = resp2.data['id']

        # Alcanza justo para la deuda 1 (300000), no para ambas (500000).
        resp_c = self._create_advance(300000)
        advance_c_id = resp_c.data['id']

        trip1 = Trip.objects.get(pk=trip1_id)
        trip2 = Trip.objects.get(pk=trip2_id)
        self.assertEqual(trip1.advance_id, advance_c_id, 'la deuda más antigua debe liquidarse primero (FIFO)')
        self.assertIsNone(trip2.advance_id, 'la deuda más nueva debe seguir pendiente: no alcanzó el saldo')

        self.assertEqual(
            get_available_balance(Advance.objects.get(pk=advance_c_id)),
            Decimal('0'),
        )


class PendingDebtInteractionWithAnnulmentTests(PendingDebtFixturesMixin, TestCase):
    """Caso 5: anular un viaje ya liquidado contra un anticipo CONGELADO
    (no el activo actual) revierte contra el que realmente lo cubrió."""

    def test_annul_reverts_against_frozen_advance_not_current_active(self):
        resp_a = self._create_advance(1000000)
        advance_a_id = resp_a.data['id']
        trip_resp = self._create_trip(300000)  # se descuenta de A, activo en ese momento
        trip_id = trip_resp.data['id']
        self.assertEqual(trip_resp.data['advance'], advance_a_id)

        resp_b = self._create_advance(500000)  # B pasa a ser el activo; A queda congelado
        advance_b_id = resp_b.data['id']

        annul_resp = self.api.patch(
            f'/api/trips/{trip_id}/',
            {'state': False, 'justification': 'Anulación de prueba'},
            format='json',
        )
        self.assertEqual(annul_resp.status_code, status.HTTP_200_OK, annul_resp.data)

        self.assertEqual(
            get_available_balance(Advance.objects.get(pk=advance_a_id)),
            Decimal('1000000'),
            'debe revertirse contra A, el anticipo que realmente cubrió el viaje',
        )
        self.assertEqual(
            get_available_balance(Advance.objects.get(pk=advance_b_id)),
            Decimal('500000'),
            'B nunca cubrió este viaje, no debe verse afectado',
        )

    def test_annul_pending_debt_trip_creates_no_movement(self):
        trip_resp = self._create_trip(150000, justification='Sin anticipo')
        trip_id = trip_resp.data['id']
        self.assertTrue(trip_resp.data['is_pending_debt'])

        annul_resp = self.api.patch(
            f'/api/trips/{trip_id}/',
            {'state': False, 'justification': 'Anulación de prueba'},
            format='json',
        )
        self.assertEqual(annul_resp.status_code, status.HTTP_200_OK, annul_resp.data)
        self.assertFalse(AdvanceMovement.objects.filter(trip_id=trip_id).exists())

        # Al quedar anulado (state=False), ya no debe contar como deuda
        # pendiente en el estado de cuenta.
        resp = self.api.get(f'/api/advances/balance/{self.client_obj.id}/')
        self.assertEqual(Decimal(resp.data['total_pending_debt']), Decimal('0'))


class AccountStatementTests(PendingDebtFixturesMixin, TestCase):
    """Caso 6: estado de cuenta (RF-33)."""

    def test_account_statement_reflects_balances_and_pending_debt(self):
        resp_a = self._create_advance(200000)
        self._create_trip(150000)  # se descuenta de A -> saldo A = 50000
        pending_resp = self._create_trip(300000, justification='Sin saldo suficiente')

        resp = self.api.get(f'/api/advances/balance/{self.client_obj.id}/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        data = resp.data

        self.assertEqual(len(data['advances']), 1)
        self.assertTrue(data['advances'][0]['is_active'])
        self.assertEqual(Decimal(data['advances'][0]['available_balance']), Decimal('50000'))
        self.assertEqual(Decimal(data['total_advances_balance']), Decimal('50000'))

        self.assertEqual(len(data['pending_debts']), 1)
        self.assertEqual(data['pending_debts'][0]['trip'], pending_resp.data['id'])
        self.assertEqual(Decimal(data['total_pending_debt']), Decimal('300000'))

        self.assertEqual(Decimal(data['net_balance']), Decimal('50000') - Decimal('300000'))


class CashierInsufficientBalanceAuditTests(PendingDebtFixturesMixin, TestCase):
    """Caso 7: cashier registra un viaje con saldo insuficiente."""

    def test_cashier_insufficient_balance_requires_justification_and_is_audited(self):
        # Sin ningún anticipo creado: el saldo activo es 0.
        resp_no_just = self._create_trip(150000, api=self.cashier_api)
        self.assertEqual(resp_no_just.status_code, status.HTTP_400_BAD_REQUEST, resp_no_just.data)

        resp = self._create_trip(
            150000, api=self.cashier_api, justification='Cliente sin anticipo, autoriza deuda'
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        trip_id = resp.data['id']
        self.assertTrue(resp.data['is_pending_debt'])

        log = AuditLog.objects.filter(action='create', model_name='Trip', object_id=trip_id).first()
        self.assertIsNotNone(log)
        self.assertEqual(log.user_id, self.cashier.id)
        self.assertEqual(log.justification, 'Cliente sin anticipo, autoriza deuda')
        self.assertEqual(log.new_data['insufficient_balance_registration']['role'], 'cashier')
