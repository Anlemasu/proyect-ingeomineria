import threading
from decimal import Decimal

from django.db import connection
from django.test import TestCase, TransactionTestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.users.models import User
from apps.clients.models import Client
from apps.masters.models import VehicleType, Vehicle, MaterialType, PaymentMethod, OriginSite
from apps.trips.models import Trip
from apps.audit.models import AuditLog
from .models import Advance, AdvanceMovement
from .services import annotate_available_balance, get_available_balance


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


class ReversedTripDoesNotGetResettledByNewAdvanceTests(PendingDebtFixturesMixin, TestCase):
    """BUG 1 (diagnóstico de solo lectura): antes de este fix, cambiar el
    medio de pago de un viaje financiado dejaba `advance=NULL` sin revertir
    el descuento y sin tocar `payment` — el viaje quedaba pareciendo una
    deuda pendiente genuina, y el siguiente anticipo del cliente lo volvía a
    liquidar (doble descuento). Este test prueba que, tras la reversión
    correcta, un anticipo nuevo del mismo cliente NO vuelve a tocar ese
    viaje."""

    def test_new_advance_does_not_resettle_a_trip_whose_payment_left_advance(self):
        resp_a = self._create_advance(1000000)
        advance_a_id = resp_a.data['id']

        trip_resp = self._create_trip(300000)
        trip_id = trip_resp.data['id']
        self.assertEqual(trip_resp.data['advance'], advance_a_id)
        self.assertEqual(get_available_balance(Advance.objects.get(pk=advance_a_id)), Decimal('700000'))

        patch_resp = self.api.patch(
            f'/api/trips/{trip_id}/', {'payment': self.payment_cash.id}, format='json'
        )
        self.assertEqual(patch_resp.status_code, status.HTTP_200_OK, patch_resp.data)
        self.assertEqual(get_available_balance(Advance.objects.get(pk=advance_a_id)), Decimal('1000000'))

        resp_b = self._create_advance(500000)
        advance_b_id = resp_b.data['id']

        trip = Trip.objects.get(pk=trip_id)
        self.assertIsNone(trip.advance_id, 'el viaje ya no debe volver a quedar financiado')
        self.assertFalse(
            AdvanceMovement.objects.filter(advance_id=advance_b_id, trip_id=trip_id).exists(),
            'el anticipo nuevo no debe generar ningún movimiento contra este viaje',
        )
        self.assertEqual(
            get_available_balance(Advance.objects.get(pk=advance_b_id)),
            Decimal('500000'),
            'el anticipo nuevo debe quedar intacto: no había ninguna deuda pendiente real que liquidar',
        )


class ConcurrentAdvanceCreationSettlementRaceTests(TransactionTestCase):
    """
    BUG 2 (diagnóstico de solo lectura): settle_pending_debts solo bloqueaba
    la fila del Advance recién creado — una fila NUEVA y distinta en cada
    request, así que dos anticipos creados casi al mismo tiempo para el
    MISMO cliente no generaban ninguna contención entre sí, y ambos podían
    leer el mismo Trip pendiente antes de que cualquiera escribiera su
    liquidación (doble egreso contra el mismo viaje, cargado a dos
    anticipos distintos).

    TransactionTestCase (no TestCase) y usernames únicos, mismo motivo
    documentado en trips/tests.py::ConcurrentTripAdvanceBalanceCheckTests:
    los hilos necesitan conexiones de BD independientes con commits reales
    para reproducir la carrera.
    """

    def setUp(self):
        self.superuser = User.objects.create_user(
            username='super_race701', email='super_race701@test.com', name='Super',
            role='superuser', password='x12345',
        )
        self.owner_user = User.objects.create_user(
            username='owner_race701', email='owner_race701@test.com', name='Owner',
            role='commercial_admin', password='x12345',
        )
        self.client_obj = Client.objects.create(
            user=self.owner_user, nit='900123458', name='Cliente Test Concurrencia Anticipos',
            abrev_name='CTCA', address='Calle 1', phone=3000000003,
        )
        vehicle_type = VehicleType.objects.create(name='Volqueta', capacity=Decimal('10.00'))
        self.vehicle = Vehicle.objects.create(vehicle_type=vehicle_type, plaque='XYZ701')
        self.material = MaterialType.objects.create(name='Material Test')
        self.origin = OriginSite.objects.create(name='Origen Test')
        self.payment_advance = PaymentMethod.objects.create(name='Anticipo', is_advance=True)
        self.today = timezone.localdate()

        # Una sola deuda pendiente: sin anticipo activo todavía, se guarda
        # justificada. Cada uno de los dos anticipos concurrentes, por sí
        # solo, tiene saldo de sobra para liquidarla — lo que se prueba es
        # que solo UNO de los dos efectivamente lo haga.
        api = APIClient()
        api.force_authenticate(user=self.superuser)
        trip_resp = api.post('/api/trips/', {
            'payment': self.payment_advance.id,
            'origin_site': self.origin.id,
            'material_type': self.material.id,
            'client': self.client_obj.id,
            'vehicle': self.vehicle.id,
            'value': '300000',
            'date': str(self.today),
            'justification': 'Sin anticipo activo todavía',
        }, format='json')
        connection.close()
        self.pending_trip_id = trip_resp.data['id']

    def _post_advance(self, transfer_num):
        api = APIClient()
        api.force_authenticate(user=self.superuser)
        try:
            return api.post('/api/advances/', {
                'client': self.client_obj.id,
                'value': '300000',
                'transfer_num': transfer_num,
                'date': str(self.today),
            }, format='json')
        finally:
            connection.close()

    def test_only_one_of_two_concurrent_advances_settles_the_same_pending_trip(self):
        results = []
        start_barrier = threading.Barrier(2)

        def worker(n):
            start_barrier.wait()
            results.append(self._post_advance(n))

        t1 = threading.Thread(target=worker, args=(1,))
        t2 = threading.Thread(target=worker, args=(2,))
        t1.start()
        t2.start()
        t1.join(timeout=15)
        t2.join(timeout=15)

        self.assertEqual(len(results), 2)
        for r in results:
            self.assertEqual(r.status_code, status.HTTP_201_CREATED, r.data)

        egresos = AdvanceMovement.objects.filter(
            trip_id=self.pending_trip_id, type_movement='egreso'
        )
        self.assertEqual(egresos.count(), 1, 'el viaje pendiente no debe liquidarse dos veces')

        trip = Trip.objects.get(pk=self.pending_trip_id)
        advance_ids = [r.data['id'] for r in results]
        self.assertIn(trip.advance_id, advance_ids)

        settled_id = trip.advance_id
        other_id = [i for i in advance_ids if i != settled_id][0]
        self.assertEqual(
            get_available_balance(Advance.objects.get(pk=settled_id)), Decimal('0')
        )
        self.assertEqual(
            get_available_balance(Advance.objects.get(pk=other_id)), Decimal('300000'),
            'el anticipo que perdió la carrera debe quedar con su saldo intacto',
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
        self._create_advance(200000)
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


class AdvanceCreationValidationAndRoleGateTests(PendingDebtFixturesMixin, TestCase):
    """FASE 6.4: cobertura que faltaba sobre el registro de anticipos en sí
    (más allá de la secuencia de liquidación, ya cubierta arriba): quién
    puede crearlos (can_manage_advances) y las validaciones de campo
    (RF-29: valor > 0, número de consignación válido)."""

    def test_cashier_cannot_create_advance(self):
        resp = self._create_advance(500000, api=self.cashier_api)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN, resp.data)
        self.assertTrue(
            AuditLog.objects.filter(action='access_denied', model_name='Advance').exists()
        )
        self.assertEqual(Advance.objects.count(), 0)

    def test_advance_with_zero_value_is_rejected(self):
        resp = self.api.post('/api/advances/', {
            'client': self.client_obj.id,
            'value': '0',
            'transfer_num': 1,
            'date': str(self.today),
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST, resp.data)

    def test_advance_with_invalid_transfer_num_is_rejected(self):
        resp = self.api.post('/api/advances/', {
            'client': self.client_obj.id,
            'value': '500000',
            'transfer_num': 0,
            'date': str(self.today),
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST, resp.data)


class AnnotatedBalanceMatchesPerObjectCalculationTests(PendingDebtFixturesMixin, TestCase):
    """
    FASE 6.2: annotate_available_balance() (una sola consulta agregada para
    varios anticipos) debe devolver exactamente el mismo número que
    get_available_balance() (una consulta por anticipo) para el mismo
    dataset — es una optimización de acceso a datos, no un cambio de
    fórmula.
    """

    def test_annotated_and_per_object_balance_match_for_mixed_movements(self):
        # A: solo ingreso, sin egresos.
        resp_a = self._create_advance(1000000)
        advance_a_id = resp_a.data['id']

        # B: ingreso + un viaje que lo descuenta parcialmente.
        self._create_advance(500000)
        self._create_trip(200000)  # se descuenta del anticipo activo (B)

        # C: un segundo cliente para que la agregación cruce varias filas.
        other_owner = User.objects.create_user(
            username='owner2', email='owner2@test.com', name='Owner 2',
            role='commercial_admin', password='x12345',
        )
        other_client = Client.objects.create(
            user=other_owner, nit='900987654', name='Cliente Test 2',
            abrev_name='CT2', address='Calle 2', phone=3000000001,
        )
        advance_c = Advance.objects.create(
            client=other_client, user=self.superuser, value=Decimal('300000'),
            transfer_num=999, date=self.today,
        )
        # C se queda sin ningún AdvanceMovement — caso borde (0 movimientos).

        annotated = {
            adv.id: (adv._annotated_ingresos or Decimal('0')) - (adv._annotated_egresos or Decimal('0'))  # type: ignore[attr-defined]
            for adv in annotate_available_balance(Advance.objects.all())
        }
        per_object = {
            adv.id: get_available_balance(adv)
            for adv in Advance.objects.all()
        }

        self.assertEqual(annotated, per_object)
        self.assertEqual(annotated[advance_a_id], Decimal('1000000'))
        self.assertEqual(per_object[advance_c.id], Decimal('0'))

    def test_advance_list_endpoint_returns_same_balance_as_before(self):
        resp_a = self._create_advance(1000000)
        advance_a_id = resp_a.data['id']
        self._create_trip(400000)

        expected_balance = get_available_balance(Advance.objects.get(pk=advance_a_id))

        resp = self.api.get('/api/advances/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        entry = next(a for a in resp.data if a['id'] == advance_a_id)
        self.assertEqual(Decimal(str(entry['available_balance'])), expected_balance)


class AdvanceClientValueLockedAfterMovementsTests(PendingDebtFixturesMixin, TestCase):
    """
    9.3 — Advance.client y Advance.value quedan bloqueados para edición una
    vez que el anticipo tiene al menos un AdvanceMovement asociado (ver
    AdvanceSerializer.validate). Cualquier anticipo creado por la API
    (AdvanceListCreateView.post) ya nace con su movimiento de ingreso
    inicial, así que en la práctica queda bloqueado desde el instante en
    que se crea — el caso "sin movimientos" solo es alcanzable creando el
    Advance directamente por ORM (fuera del flujo normal de la API), como
    hace el primer test de abajo.
    """

    def test_advance_without_movements_still_allows_editing_client_and_value(self):
        other_owner = User.objects.create_user(
            username='owner_93a', email='owner_93a@test.com', name='Owner93A',
            role='commercial_admin', password='x12345',
        )
        other_client = Client.objects.create(
            user=other_owner, nit='900930001', name='Cliente 9.3 A',
            abrev_name='C93A', address='Calle 1', phone=3000900001,
        )
        advance = Advance.objects.create(
            client=self.client_obj, user=self.superuser, value=Decimal('500000'),
            transfer_num=901, date=self.today,
        )
        self.assertFalse(AdvanceMovement.objects.filter(advance=advance).exists())

        resp = self.api.patch(f'/api/advances/{advance.id}/', {
            'client': other_client.id, 'value': '600000',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        advance.refresh_from_db()
        self.assertEqual(advance.client_id, other_client.id)
        self.assertEqual(advance.value, Decimal('600000'))

    def test_advance_with_movements_rejects_editing_client_and_value(self):
        resp_a = self._create_advance(500000)
        advance_id = resp_a.data['id']
        self.assertTrue(AdvanceMovement.objects.filter(advance_id=advance_id).exists())

        other_owner = User.objects.create_user(
            username='owner_93b', email='owner_93b@test.com', name='Owner93B',
            role='commercial_admin', password='x12345',
        )
        other_client = Client.objects.create(
            user=other_owner, nit='900930002', name='Cliente 9.3 B',
            abrev_name='C93B', address='Calle 1', phone=3000900002,
        )

        resp_client = self.api.patch(f'/api/advances/{advance_id}/', {
            'client': other_client.id,
        }, format='json')
        self.assertEqual(resp_client.status_code, status.HTTP_400_BAD_REQUEST, resp_client.data)
        self.assertIn('client', resp_client.data)

        resp_value = self.api.patch(f'/api/advances/{advance_id}/', {
            'value': '999999',
        }, format='json')
        self.assertEqual(resp_value.status_code, status.HTTP_400_BAD_REQUEST, resp_value.data)
        self.assertIn('value', resp_value.data)

        advance = Advance.objects.get(pk=advance_id)
        self.assertEqual(advance.client_id, self.client_obj.id)
        self.assertEqual(advance.value, Decimal('500000'))

    def test_advance_with_movements_still_allows_editing_other_fields(self):
        resp_a = self._create_advance(500000)
        advance_id = resp_a.data['id']

        resp = self.api.patch(f'/api/advances/{advance_id}/', {
            'observations': 'Nota actualizada',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        advance = Advance.objects.get(pk=advance_id)
        self.assertEqual(advance.observations, 'Nota actualizada')


class AdvanceValueCorrectionTests(PendingDebtFixturesMixin, TestCase):
    """
    9C — corrección del valor original de un anticipo ACTIVO mediante un
    movimiento de ajuste nuevo (correct_active_advance_value /
    AdvanceCorrectValueView), sin editar ni borrar ningún AdvanceMovement
    existente. No usa PendingDebtFixturesMixin._create_trip con
    justificación porque en estos tests siempre hay saldo de sobra para el
    viaje que se registra (no es deuda pendiente).
    """

    def _correct(self, advance_id, correct_value, justification='Corrección de error de digitación', api=None):
        api = api or self.api
        return api.post(f'/api/advances/{advance_id}/correct-value/', {
            'correct_value': str(correct_value),
            'justification': justification,
        }, format='json')

    def test_correcting_to_higher_value_increases_balance_and_audits(self):
        resp_a = self._create_advance(1000000)
        advance_id = resp_a.data['id']

        resp = self._correct(advance_id, 1500000, justification='El valor real consignado era 1.500.000')
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        self.assertEqual(resp.data['advance']['available_balance'], 1500000.0)
        self.assertEqual(resp.data['movement']['type_movement'], 'ingreso')
        self.assertEqual(Decimal(str(resp.data['movement']['amount'])), Decimal('500000'))

        advance = Advance.objects.get(pk=advance_id)
        self.assertEqual(advance.value, Decimal('1500000'))
        self.assertEqual(get_available_balance(advance), Decimal('1500000'))

        movement = AdvanceMovement.objects.get(advance=advance, type_movement='ingreso', amount=Decimal('500000'))
        self.assertIsNone(movement.trip, 'el movimiento de ajuste no está atado a ningún viaje')

        entry = AuditLog.objects.filter(
            action='update', model_name='Advance', object_id=advance_id
        ).latest('timestamp')
        self.assertEqual(entry.justification, 'El valor real consignado era 1.500.000')
        self.assertEqual(Decimal(entry.new_data['value']), Decimal('1500000'))
        self.assertEqual(Decimal(entry.new_data['difference']), Decimal('500000'))
        self.assertEqual(entry.new_data['role'], 'superuser')
        self.assertEqual(Decimal(entry.previous_data['value']), Decimal('1000000'))

    def test_correcting_to_higher_value_settles_existing_pending_debt(self):
        """DIAGNÓSTICO — reproduce el bug reportado: corregir el valor hacia
        arriba debería liquidar deuda pendiente ya existente del cliente,
        igual que ya hace crear un anticipo nuevo (PendingDebtSettlementOnNewAdvanceTests)."""
        resp_a = self._create_advance(100000)  # insuficiente
        advance_id = resp_a.data['id']

        trip_resp = self._create_trip(300000, justification='Sin saldo suficiente')
        trip_id = trip_resp.data['id']
        self.assertIsNone(trip_resp.data['advance'])

        resp = self._correct(advance_id, 500000, justification='El valor real consignado era 500.000')
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)

        trip = Trip.objects.get(pk=trip_id)
        self.assertEqual(
            trip.advance_id, advance_id,
            'la deuda pendiente debe liquidarse contra el mismo anticipo corregido',
        )
        self.assertEqual(
            get_available_balance(Advance.objects.get(pk=advance_id)),
            Decimal('200000'),  # 500000 - 300000
        )

    def test_correcting_to_higher_value_stops_at_first_uncovered_debt_fifo(self):
        """DIAGNÓSTICO — si hay VARIAS deudas pendientes, el FIFO estricto
        (igual que al crear un anticipo nuevo) se detiene en la primera que
        no alcanza a cubrirse, aunque una deuda MÁS NUEVA y más chica sí
        quepa en el saldo corregido."""
        resp_a = self._create_advance(100000)
        advance_id = resp_a.data['id']

        # Ambos viajes deben exceder el saldo ORIGINAL de la activa (100000)
        # para que los dos sean genuinamente deuda pendiente — el chequeo de
        # "insuficiente" en TripListCreateView.post compara contra el saldo
        # de movimientos real, que una deuda pendiente anterior NO toca.
        resp1 = self._create_trip(300000, justification='Deuda 1 (más antigua, grande)')
        trip1_id = resp1.data['id']
        resp2 = self._create_trip(150000, justification='Deuda 2 (más nueva, chica)')
        trip2_id = resp2.data['id']
        self.assertIsNone(resp1.data['advance'])
        self.assertIsNone(resp2.data['advance'])

        # Alcanza para la deuda 2 (150000) pero NO para la deuda 1 (300000).
        resp = self._correct(advance_id, 200000, justification='Corrección parcial')
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)

        trip1 = Trip.objects.get(pk=trip1_id)
        trip2 = Trip.objects.get(pk=trip2_id)
        self.assertIsNone(trip1.advance_id, 'la deuda más antigua sigue pendiente: no alcanzó el saldo')
        self.assertIsNone(
            trip2.advance_id,
            'FIFO estricto: no debe saltarse la deuda 1 para liquidar la 2 aunque quepa sola',
        )

    def test_correcting_to_lower_value_without_trips_decreases_balance(self):
        resp_a = self._create_advance(1000000)
        advance_id = resp_a.data['id']

        resp = self._correct(advance_id, 700000)
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)

        advance = Advance.objects.get(pk=advance_id)
        self.assertEqual(advance.value, Decimal('700000'))
        self.assertEqual(get_available_balance(advance), Decimal('700000'))

        self.assertTrue(
            AdvanceMovement.objects.filter(
                advance=advance, type_movement='egreso', amount=Decimal('300000')
            ).exists()
        )

    def test_correcting_to_lower_value_unlinks_most_recent_trip_as_pending_debt(self):
        """REQUISITO NUEVO (esta sesión): antes, una reducción que dejaba el
        saldo negativo simplemente se permitía tal cual. Ahora, si el saldo
        resultante quedaría negativo, el/los viaje(s) vinculados MÁS
        RECIENTES se sueltan como deuda pendiente (compute_unlink_impact)
        hasta cubrir el faltante, en vez de dejar un saldo negativo."""
        resp_a = self._create_advance(1000000)
        advance_id = resp_a.data['id']
        trip_resp = self._create_trip(800000)  # descuenta 800000 del anticipo activo: saldo queda en 200000
        trip_id = trip_resp.data['id']
        self.assertEqual(trip_resp.data['advance'], advance_id)

        resp = self._correct(advance_id, 500000, justification='El valor real era 500.000, no 1.000.000')
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        self.assertEqual(len(resp.data['unlinked_trips']), 1)
        self.assertEqual(resp.data['unlinked_trips'][0]['trip'], trip_id)

        advance = Advance.objects.get(pk=advance_id)
        trip = Trip.objects.get(pk=trip_id)
        self.assertEqual(advance.value, Decimal('500000'))
        self.assertIsNone(trip.advance_id, 'el viaje debe soltarse como deuda pendiente, no quedar con saldo negativo')
        self.assertEqual(
            get_available_balance(advance), Decimal('500000'),
            'al soltar el viaje (800000) se recupera más que el faltante (300000): el saldo queda positivo',
        )

        entry = AuditLog.objects.filter(
            action='update', model_name='Advance', object_id=advance_id
        ).latest('timestamp')
        self.assertEqual(Decimal(entry.new_data['difference']), Decimal('-500000'))
        self.assertEqual(len(entry.new_data['unlinked_trips']), 1)

    def test_correcting_to_lower_value_with_no_linked_trips_never_goes_negative(self):
        """Sin ningún viaje vinculado, reducir el valor (siempre a un
        correct_value > 0, exigido por el serializer) nunca puede dejar el
        saldo negativo: sin egresos por viajes que reclamar, el saldo
        resultante es exactamente correct_value."""
        resp_a = self._create_advance(1000000)
        advance_id = resp_a.data['id']

        resp = self._correct(advance_id, 100, justification='Corrección drástica, sin viajes vinculados')
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        self.assertEqual(resp.data['unlinked_trips'], [])

        advance = Advance.objects.get(pk=advance_id)
        self.assertEqual(get_available_balance(advance), Decimal('100'))

    def test_cannot_correct_advance_that_is_no_longer_active(self):
        resp_a = self._create_advance(1000000)
        advance_a_id = resp_a.data['id']
        self._create_advance(500000)  # B, más reciente: A queda congelado

        resp = self._correct(advance_a_id, 2000000)
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST, resp.data)

        advance_a = Advance.objects.get(pk=advance_a_id)
        self.assertEqual(
            advance_a.value, Decimal('1000000'),
            'no debe haberse tocado el valor de un anticipo ya congelado',
        )
        self.assertFalse(
            AdvanceMovement.objects.filter(advance=advance_a, description__icontains='Corrección').exists()
        )

    def test_correction_without_justification_is_rejected(self):
        resp_a = self._create_advance(1000000)
        advance_id = resp_a.data['id']

        resp = self.api.post(f'/api/advances/{advance_id}/correct-value/', {
            'correct_value': '1200000',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST, resp.data)

        advance = Advance.objects.get(pk=advance_id)
        self.assertEqual(advance.value, Decimal('1000000'))

    def test_unauthorized_role_cannot_correct_value(self):
        resp_a = self._create_advance(1000000)
        advance_id = resp_a.data['id']

        resp = self._correct(advance_id, 1200000, api=self.cashier_api)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN, resp.data)

        advance = Advance.objects.get(pk=advance_id)
        self.assertEqual(advance.value, Decimal('1000000'))

    def test_movement_history_shows_correction_without_altering_original(self):
        resp_a = self._create_advance(1000000)
        advance_id = resp_a.data['id']
        original_movement_id = AdvanceMovement.objects.get(
            advance_id=advance_id, type_movement='ingreso'
        ).id

        self._correct(advance_id, 1300000, justification='Ajuste de valor')

        resp = self.api.get(f'/api/advances/{advance_id}/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        movements = resp.data['movements']
        self.assertEqual(len(movements), 2, 'el movimiento original y el de ajuste deben coexistir')

        original = next(m for m in movements if m['id'] == original_movement_id)
        self.assertEqual(Decimal(str(original['amount'])), Decimal('1000000'))
        self.assertEqual(original['description'], 'Anticipo registrado. Ref: 1')

        adjustment = next(m for m in movements if m['id'] != original_movement_id)
        self.assertEqual(Decimal(str(adjustment['amount'])), Decimal('300000'))
        self.assertEqual(adjustment['type_movement'], 'ingreso')
