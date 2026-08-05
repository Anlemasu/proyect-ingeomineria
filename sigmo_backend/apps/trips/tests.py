from decimal import Decimal

from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.users.models import User
from apps.clients.models import Client
from apps.masters.models import VehicleType, Vehicle, MaterialType, PaymentMethod, OriginSite
from apps.advances.models import Advance, AdvanceMovement
from apps.advances.services import get_available_balance
from apps.audit.models import AuditLog
from apps.cash_closing.services import execute_close
from apps.cash_closing.models import DailySummary
from apps.trips.models import Trip


class TripAdvanceFixturesMixin:
    """Fixtures comunes: un cliente con un anticipo de 1'000.000 y un medio
    de pago 'anticipo'. Se usan en los tests del BUG 2 (reversión de saldo)
    y del REQUISITO NUEVO 3.4 (resync de un cierre tras un ajuste)."""

    def setUp(self):
        self.superuser = User.objects.create_user(
            username='super1', email='super1@test.com', name='Super',
            role='superuser', password='x12345',
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

        self.advance = Advance.objects.create(
            client=self.client_obj, user=self.superuser, value=Decimal('1000000'),
            transfer_num=1, date=timezone.localdate(),
        )
        AdvanceMovement.objects.create(
            advance=self.advance, type_movement='ingreso', amount=Decimal('1000000'),
            trips_quantity=0, date=timezone.localdate(), description='Anticipo inicial',
        )

        self.today = timezone.localdate()
        self.api = APIClient()
        self.api.force_authenticate(user=self.superuser)

    def _create_trip(self, *, value='300000', payment=None, advance=None, date=None):
        payment = payment or self.payment_advance
        if advance is None and payment.is_advance:
            advance = self.advance
        return self.api.post('/api/trips/', {
            'payment': payment.id,
            'origin_site': self.origin.id,
            'material_type': self.material.id,
            'client': self.client_obj.id,
            'vehicle': self.vehicle.id,
            'advance': advance.id if advance else None,
            'value': value,
            'date': str(date or self.today),
        }, format='json')


class AdvanceReversalOnTripChangeTests(TripAdvanceFixturesMixin, TestCase):
    """BUG 2: anular o editar el valor de un viaje pagado con anticipo debe
    revertir/ajustar el saldo, dejando el movimiento original intacto."""

    def test_annul_advance_funded_trip_restores_balance(self):
        resp = self._create_trip(value='300000')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        trip_id = resp.data['id']

        self.assertEqual(get_available_balance(self.advance), Decimal('700000'))

        resp2 = self.api.patch(
            f'/api/trips/{trip_id}/',
            {'state': False, 'justification': 'Anulación de prueba'},
            format='json',
        )
        self.assertEqual(resp2.status_code, status.HTTP_200_OK, resp2.data)

        # El saldo vuelve a estar completo: la anulación no debe "perder"
        # el dinero descontado originalmente (el bug que se corrige aquí).
        self.assertEqual(get_available_balance(self.advance), Decimal('1000000'))

        movs = AdvanceMovement.objects.filter(advance=self.advance, trip_id=trip_id)
        self.assertEqual(movs.count(), 2, 'debe existir el egreso original Y el ingreso de reversión')
        self.assertTrue(movs.filter(type_movement='egreso', amount=Decimal('300000')).exists())
        self.assertTrue(movs.filter(type_movement='ingreso', amount=Decimal('300000')).exists())

        # Auditoría: la reversión del anticipo queda registrada aparte del
        # 'annul' del viaje.
        self.assertTrue(AuditLog.objects.filter(action='annul', model_name='Trip', object_id=trip_id).exists())
        self.assertTrue(AuditLog.objects.filter(action='update', model_name='Advance', object_id=self.advance.id).exists())

    def test_edit_value_of_advance_funded_trip_adjusts_balance(self):
        resp = self._create_trip(value='300000')
        trip_id = resp.data['id']

        resp2 = self.api.patch(f'/api/trips/{trip_id}/', {'value': '500000'}, format='json')
        self.assertEqual(resp2.status_code, status.HTTP_200_OK, resp2.data)

        # 1.000.000 - 500.000 (nuevo valor neto del viaje), no 1.000.000 - 300.000 - 200.000 "sueltos"
        self.assertEqual(get_available_balance(self.advance), Decimal('500000'))

        resp3 = self.api.patch(f'/api/trips/{trip_id}/', {'value': '100000'}, format='json')
        self.assertEqual(resp3.status_code, status.HTTP_200_OK, resp3.data)
        self.assertEqual(get_available_balance(self.advance), Decimal('900000'))

    def test_edit_exceeding_balance_is_rejected_unless_superuser_forces(self):
        resp = self._create_trip(value='300000')
        trip_id = resp.data['id']

        # Saldo disponible tras crear: 700.000. Subir a 2'000.000 no cabe.
        resp2 = self.api.patch(f'/api/trips/{trip_id}/', {'value': '2000000'}, format='json')
        self.assertEqual(resp2.status_code, status.HTTP_400_BAD_REQUEST, resp2.data)
        self.assertEqual(get_available_balance(self.advance), Decimal('700000'), 'el saldo no debe cambiar si se rechaza')

        resp3 = self.api.patch(
            f'/api/trips/{trip_id}/', {'value': '2000000', 'force': 'true'}, format='json'
        )
        self.assertEqual(resp3.status_code, status.HTTP_200_OK, resp3.data)
        self.assertEqual(get_available_balance(self.advance), Decimal('-1000000'))

    def test_annul_non_advance_trip_does_not_touch_advance_balance(self):
        """No debe alterarse la lógica existente para viajes que no usan anticipo."""
        resp = self._create_trip(value='150000', payment=self.payment_cash)
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        trip_id = resp.data['id']

        balance_before = get_available_balance(self.advance)
        resp2 = self.api.patch(
            f'/api/trips/{trip_id}/',
            {'state': False, 'justification': 'Anulación de prueba'},
            format='json',
        )
        self.assertEqual(resp2.status_code, status.HTTP_200_OK, resp2.data)
        self.assertEqual(get_available_balance(self.advance), balance_before)
        self.assertFalse(AdvanceMovement.objects.filter(trip_id=trip_id).exists())


class HistoricalAdjustmentResyncTests(TripAdvanceFixturesMixin, TestCase):
    """REQUISITO NUEVO 3.4: ajustar un viaje de un día ya cerrado debe
    recalcular el DailySummary correspondiente y dejarlo auditado."""

    def test_edit_trip_on_closed_day_resyncs_summary_and_audit_trail(self):
        resp = self._create_trip(value='200000', payment=self.payment_cash)
        trip_id = resp.data['id']

        summary = execute_close(self.today, source='manual')
        self.assertEqual(summary.total_trips, 1)
        self.assertEqual(summary.avg_trip_value, Decimal('200000'))

        # El superuser puede ajustar un viaje de un día cerrado sin
        # justificar (decisión posterior a la Fase 2: la justificación
        # quedó concentrada solo en la anulación de viajes).
        resp2 = self.api.patch(f'/api/trips/{trip_id}/', {'value': '350000'}, format='json')
        self.assertEqual(resp2.status_code, status.HTTP_200_OK, resp2.data)

        summary.refresh_from_db()
        self.assertEqual(summary.avg_trip_value, Decimal('350000'))
        payment_total = summary.payment_details.get(payment_method=self.payment_cash).total
        self.assertEqual(payment_total, Decimal('350000'))

        self.assertTrue(AuditLog.objects.filter(action='update', model_name='Trip', object_id=trip_id).exists())
        self.assertTrue(
            AuditLog.objects.filter(action='recalculo_cierre', model_name='DailySummary', object_id=summary.id).exists()
        )

    def test_invoice_only_patch_does_not_trigger_resync(self):
        """Un PATCH que solo toca invoice/invoice_pos no cambia totales: no
        debe generar un recálculo/evento de auditoría innecesario."""
        resp = self._create_trip(value='200000', payment=self.payment_cash)
        trip_id = resp.data['id']
        summary = execute_close(self.today, source='manual')

        events_before = AuditLog.objects.filter(action='recalculo_cierre').count()
        resp2 = self.api.patch(f'/api/trips/{trip_id}/', {'invoice_pos': 1}, format='json')
        self.assertEqual(resp2.status_code, status.HTTP_200_OK, resp2.data)
        events_after = AuditLog.objects.filter(action='recalculo_cierre').count()
        self.assertEqual(events_before, events_after)


class ClosedDayBlocksTripCreationTests(TripAdvanceFixturesMixin, TestCase):
    """REQUISITO NUEVO 3.1/3.3: un día con cierre vigente no admite viajes
    nuevos; revertir el cierre debe permitirlo de nuevo."""

    def test_create_blocked_on_closed_day_then_allowed_after_revert(self):
        summary = execute_close(self.today, source='manual')
        self.assertEqual(summary.state, DailySummary.STATE_CLOSED)

        resp = self._create_trip(value='150000', payment=self.payment_cash)
        self.assertEqual(resp.status_code, status.HTTP_409_CONFLICT, resp.data)

        revert_resp = self.api.post(
            f'/api/cash-closing/{summary.id}/revert/',
            {'justification': 'Prueba automatizada de reversión'},
            format='json',
        )
        self.assertEqual(revert_resp.status_code, status.HTTP_200_OK, revert_resp.data)
        summary.refresh_from_db()
        self.assertEqual(summary.state, DailySummary.STATE_REVERTED)

        resp2 = self._create_trip(value='150000', payment=self.payment_cash)
        self.assertEqual(resp2.status_code, status.HTTP_201_CREATED, resp2.data)

    def test_revert_requires_superuser_but_not_justification(self):
        summary = execute_close(self.today, source='manual')

        cashier = User.objects.create_user(
            username='cash1', email='cash1@test.com', name='Cajero',
            role='cashier', password='x12345',
        )
        cashier_api = APIClient()
        cashier_api.force_authenticate(user=cashier)
        resp = cashier_api.post(
            f'/api/cash-closing/{summary.id}/revert/', {'justification': 'x'}, format='json'
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

        # Decisión: revertir un cierre ya no exige justificación al superuser.
        resp2 = self.api.post(f'/api/cash-closing/{summary.id}/revert/', {}, format='json')
        self.assertEqual(resp2.status_code, status.HTTP_200_OK, resp2.data)
        summary.refresh_from_db()
        self.assertEqual(summary.state, DailySummary.STATE_REVERTED)


class DateRegisterLocalTimezoneComparisonTests(TripAdvanceFixturesMixin, TestCase):
    """
    Regresión de un bug encontrado durante la Fase 1 (no formaba parte de
    los dos bugs originales, pero se corrigió a pedido): RF-36 (el cajero
    solo edita registros del día en curso) y RF-37 (justificación para
    ajustes históricos) comparaban `obj.date_register.date()` — la fecha en
    UTC, tal como Postgres/Django devuelven un datetime-aware — contra
    `timezone.localdate()` — la fecha en la zona horaria del proyecto
    (America/Bogota, UTC-5). Un viaje registrado después de las 19:00 hora
    de Bogotá (cuando UTC ya cambió de calendario pero Bogotá todavía no) se
    trataba como si fuera de un día anterior. Se corrigió comparando
    `timezone.localtime(obj.date_register).date()`.
    """

    def _create_trip_late_local_tonight(self):
        from datetime import datetime, time as dt_time

        today = timezone.localdate()
        # 23:30 hora de Bogotá de "hoy": en UTC cae en la madrugada de "mañana".
        late_local_tonight = timezone.make_aware(datetime.combine(today, dt_time(23, 30)))
        trip = Trip.objects.create(
            payment=self.payment_cash, origin_site=self.origin, material_type=self.material,
            client=self.client_obj, vehicle=self.vehicle, voucher_num=9001,
            value=Decimal('180000'), date_register=late_local_tonight, date=today, state=True,
        )
        # Al volver a leerlo de la base de datos, date_register llega como
        # datetime-aware en UTC (así lo entrega Postgres/psycopg2 con
        # USE_TZ=True) — así es exactamente como lo ve la vista en un PATCH
        # real, y así se reproduce la condición del bug.
        trip.refresh_from_db()
        return trip, today

    def test_cashier_can_edit_trip_registered_late_tonight_local_time(self):
        trip, today = self._create_trip_late_local_tonight()
        # Confirma la premisa del test: la fecha "cruda" en UTC ya no
        # coincide con la fecha local, que es justo el caso que rompía la
        # comparación vieja.
        self.assertNotEqual(trip.date_register.date(), today)

        cashier = User.objects.create_user(
            username='cash1', email='cash1@test.com', name='Cajero',
            role='cashier', password='x12345',
        )
        cashier_api = APIClient()
        cashier_api.force_authenticate(user=cashier)

        resp = cashier_api.patch(f'/api/trips/{trip.id}/', {'value': '190000'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)

    def test_superuser_editing_it_does_not_require_justification(self):
        trip, _today = self._create_trip_late_local_tonight()
        resp = self.api.patch(f'/api/trips/{trip.id}/', {'value': '190000'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)


class TripPatchRoleGateTests(TripAdvanceFixturesMixin, TestCase):
    """
    FASE 2 — BUG 1/2: antes de este fix, TripDetailView.patch no chequeaba
    el rol en absoluto (cualquier autenticado podía modificar cualquier
    viaje). Estos tests cubren: quién puede entrar al PATCH, quién puede
    anular y bajo qué condición, y el bloqueo de un día con cierre vigente.
    """

    def setUp(self):
        super().setUp()
        self.cashier = User.objects.create_user(
            username='cash1', email='cash1@test.com', name='Cajero',
            role='cashier', password='x12345',
        )
        self.commercial_admin = User.objects.create_user(
            username='comm1', email='comm1@test.com', name='Comercial',
            role='commercial_admin', password='x12345',
        )
        self.auditor = User.objects.create_user(
            username='audit1', email='audit1@test.com', name='Auditor',
            role='auditor', password='x12345',
        )
        self.accountant = User.objects.create_user(
            username='acct1', email='acct1@test.com', name='Contador',
            role='accountant', password='x12345',
        )

    def _api_as(self, user):
        api = APIClient()
        api.force_authenticate(user=user)
        return api

    def test_auditor_cannot_patch_trip(self):
        resp = self._create_trip(value='150000', payment=self.payment_cash)
        trip_id = resp.data['id']

        result = self._api_as(self.auditor).patch(
            f'/api/trips/{trip_id}/', {'value': '160000'}, format='json'
        )
        self.assertEqual(result.status_code, status.HTTP_403_FORBIDDEN, result.data)
        self.assertTrue(
            AuditLog.objects.filter(action='access_denied', model_name='Trip', object_id=trip_id).exists()
        )

    def test_accountant_cannot_patch_trip(self):
        resp = self._create_trip(value='150000', payment=self.payment_cash)
        trip_id = resp.data['id']

        result = self._api_as(self.accountant).patch(
            f'/api/trips/{trip_id}/', {'value': '160000'}, format='json'
        )
        self.assertEqual(result.status_code, status.HTTP_403_FORBIDDEN, result.data)

    def test_commercial_admin_can_edit_trip_of_current_day(self):
        resp = self._create_trip(value='150000', payment=self.payment_cash)
        trip_id = resp.data['id']

        result = self._api_as(self.commercial_admin).patch(
            f'/api/trips/{trip_id}/', {'value': '160000'}, format='json'
        )
        self.assertEqual(result.status_code, status.HTTP_200_OK, result.data)

    def test_cashier_cannot_annul_without_justification(self):
        resp = self._create_trip(value='150000', payment=self.payment_cash)
        trip_id = resp.data['id']

        result = self._api_as(self.cashier).patch(
            f'/api/trips/{trip_id}/', {'state': False}, format='json'
        )
        self.assertEqual(result.status_code, status.HTTP_400_BAD_REQUEST, result.data)
        trip = Trip.objects.get(pk=trip_id)
        self.assertTrue(trip.state, 'el viaje no debe quedar anulado si falta la justificación')

    def test_cashier_can_annul_with_justification(self):
        resp = self._create_trip(value='150000', payment=self.payment_cash)
        trip_id = resp.data['id']

        result = self._api_as(self.cashier).patch(
            f'/api/trips/{trip_id}/',
            {'state': False, 'justification': 'Viaje registrado por error, cliente incorrecto'},
            format='json',
        )
        self.assertEqual(result.status_code, status.HTTP_200_OK, result.data)
        trip = Trip.objects.get(pk=trip_id)
        self.assertFalse(trip.state)

    def test_superuser_can_annul_with_justification(self):
        resp = self._create_trip(value='150000', payment=self.payment_cash)
        trip_id = resp.data['id']

        result = self.api.patch(
            f'/api/trips/{trip_id}/',
            {'state': False, 'justification': 'Anulación de prueba'},
            format='json',
        )
        self.assertEqual(result.status_code, status.HTTP_200_OK, result.data)

    def test_superuser_cannot_annul_without_justification(self):
        """Decisión: la justificación quedó concentrada solo en anular —
        aplica también a superuser, que antes no la necesitaba para esto."""
        resp = self._create_trip(value='150000', payment=self.payment_cash)
        trip_id = resp.data['id']

        result = self.api.patch(f'/api/trips/{trip_id}/', {'state': False}, format='json')
        self.assertEqual(result.status_code, status.HTTP_400_BAD_REQUEST, result.data)
        trip = Trip.objects.get(pk=trip_id)
        self.assertTrue(trip.state)

    def test_closed_day_blocks_normal_patch_for_non_superuser(self):
        resp = self._create_trip(value='150000', payment=self.payment_cash)
        trip_id = resp.data['id']
        execute_close(self.today, source='manual')

        result = self._api_as(self.commercial_admin).patch(
            f'/api/trips/{trip_id}/', {'value': '160000'}, format='json'
        )
        self.assertEqual(result.status_code, status.HTTP_409_CONFLICT, result.data)

    def test_closed_day_allows_superuser_without_justification(self):
        """Decisión: el ajuste histórico de superuser ya no exige
        justificación (quedó reservada solo para anular, ver arriba)."""
        resp = self._create_trip(value='150000', payment=self.payment_cash)
        trip_id = resp.data['id']
        execute_close(self.today, source='manual')

        result = self.api.patch(f'/api/trips/{trip_id}/', {'value': '160000'}, format='json')
        self.assertEqual(result.status_code, status.HTTP_200_OK, result.data)
