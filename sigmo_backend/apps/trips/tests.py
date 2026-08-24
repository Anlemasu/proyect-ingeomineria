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


class TripCreationTests(TripAdvanceFixturesMixin, TestCase):
    """
    FASE 6.4: cobertura básica de creación de viajes que no estaba cubierta
    todavía — el camino feliz sin anticipo (voucher_num, campos por
    defecto) y el control de rol sobre quién puede registrar viajes
    (can_register_trips). El caso "con anticipo, alcanza/no alcanza" ya
    tiene cobertura extensa en advances/tests.py, no se duplica aquí.
    """

    def test_cash_trip_created_with_sequential_voucher_and_active_state(self):
        resp1 = self._create_trip(value='150000', payment=self.payment_cash)
        self.assertEqual(resp1.status_code, status.HTTP_201_CREATED, resp1.data)
        resp2 = self._create_trip(value='180000', payment=self.payment_cash)
        self.assertEqual(resp2.status_code, status.HTTP_201_CREATED, resp2.data)

        self.assertEqual(resp2.data['voucher_num'], resp1.data['voucher_num'] + 1)
        self.assertTrue(resp2.data['state'])
        self.assertIsNone(resp2.data['advance'])
        self.assertFalse(resp2.data['is_pending_debt'])

        self.assertTrue(
            AuditLog.objects.filter(action='create', model_name='Trip', object_id=resp1.data['id']).exists()
        )

    def test_auditor_cannot_register_trip(self):
        auditor = User.objects.create_user(
            username='audit1', email='audit1@test.com', name='Auditor',
            role='auditor', password='x12345',
        )
        api = APIClient()
        api.force_authenticate(user=auditor)
        resp = api.post('/api/trips/', {
            'payment': self.payment_cash.id,
            'origin_site': self.origin.id,
            'material_type': self.material.id,
            'client': self.client_obj.id,
            'vehicle': self.vehicle.id,
            'value': '150000',
            'date': str(self.today),
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN, resp.data)
        self.assertEqual(Trip.objects.count(), 0)


class TripInvoiceAssociationTests(TripAdvanceFixturesMixin, TestCase):
    """FASE 6.4: RF-39 — asociar una factura ya creada a un viaje vía PATCH
    (invoice/invoice_pos). El rechazo por número duplicado ya se prueba en
    invoices/tests.py; acá se prueba la asociación en sí."""

    def test_patch_associates_invoice_to_trip(self):
        trip_resp = self._create_trip(value='200000', payment=self.payment_cash)
        trip_id = trip_resp.data['id']

        invoice_resp = self.api.post('/api/invoices/', {'number': 'FAC-6001'}, format='json')
        self.assertEqual(invoice_resp.status_code, status.HTTP_201_CREATED, invoice_resp.data)
        invoice_id = invoice_resp.data['id']

        patch_resp = self.api.patch(
            f'/api/trips/{trip_id}/', {'invoice': invoice_id, 'invoice_pos': 3}, format='json'
        )
        self.assertEqual(patch_resp.status_code, status.HTTP_200_OK, patch_resp.data)

        trip = Trip.objects.get(pk=trip_id)
        self.assertEqual(trip.invoice_id, invoice_id)
        self.assertEqual(trip.invoice_pos, 3)

        get_resp = self.api.get(f'/api/trips/{trip_id}/')
        self.assertEqual(get_resp.data['invoice'], invoice_id)


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

        # 8B.3: decisión de negocio confirmada — se mantiene el mecanismo
        # (el anticipo queda en negativo, no se convierte en deuda
        # pendiente), pero ahora forzar el exceso también exige
        # justificación, no solo force=true + superuser.
        resp3 = self.api.patch(
            f'/api/trips/{trip_id}/',
            {'value': '2000000', 'force': 'true', 'justification': 'Autorizado por gerencia'},
            format='json',
        )
        self.assertEqual(resp3.status_code, status.HTTP_200_OK, resp3.data)
        self.assertEqual(get_available_balance(self.advance), Decimal('-1000000'))

        self.assertTrue(
            AuditLog.objects.filter(
                action='update', model_name='Advance', object_id=self.advance.id,
                justification='Autorizado por gerencia',
            ).exists()
        )

    def test_forcing_excess_without_justification_is_rejected(self):
        """8B.3 (diagnóstico de solo lectura): antes bastaba force=true +
        superuser para dejar un anticipo en negativo sin ningún rastro de
        por qué se autorizó."""
        resp = self._create_trip(value='300000')
        trip_id = resp.data['id']

        resp2 = self.api.patch(
            f'/api/trips/{trip_id}/', {'value': '2000000', 'force': 'true'}, format='json'
        )
        self.assertEqual(resp2.status_code, status.HTTP_400_BAD_REQUEST, resp2.data)
        self.assertEqual(get_available_balance(self.advance), Decimal('700000'))

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

    def test_changing_payment_away_from_advance_on_funded_trip_reverses_balance(self):
        """BUG 1 (diagnóstico de solo lectura): cambiar el medio de pago de un
        viaje financiado, dejando el mismo cliente, debe revertir el saldo
        igual que anular — antes se descontaba y quedaba huérfano."""
        resp = self._create_trip(value='300000')
        trip_id = resp.data['id']
        self.assertEqual(get_available_balance(self.advance), Decimal('700000'))

        resp2 = self.api.patch(f'/api/trips/{trip_id}/', {'payment': self.payment_cash.id}, format='json')
        self.assertEqual(resp2.status_code, status.HTTP_200_OK, resp2.data)

        self.assertEqual(get_available_balance(self.advance), Decimal('1000000'))
        trip = Trip.objects.get(pk=trip_id)
        self.assertIsNone(trip.advance_id)
        self.assertIsNone(trip.pending_debt_justification)

        movs = AdvanceMovement.objects.filter(advance=self.advance, trip_id=trip_id)
        self.assertEqual(movs.count(), 2, 'debe existir el egreso original Y el ingreso de reversión')
        self.assertTrue(movs.filter(type_movement='egreso', amount=Decimal('300000')).exists())
        self.assertTrue(movs.filter(type_movement='ingreso', amount=Decimal('300000')).exists())
        self.assertTrue(
            AuditLog.objects.filter(action='update', model_name='Advance', object_id=self.advance.id).exists()
        )

    def test_explicit_null_advance_on_funded_trip_is_rejected(self):
        """BUG 1: poner `advance` en null a mano en un viaje financiado
        (mismo cliente, payment sigue siendo de tipo anticipo) debe
        rechazarse — dejarlo pasar corrompería el saldo silenciosamente."""
        resp = self._create_trip(value='300000')
        trip_id = resp.data['id']

        resp2 = self.api.patch(f'/api/trips/{trip_id}/', {'advance': None}, format='json')
        self.assertEqual(resp2.status_code, status.HTTP_400_BAD_REQUEST, resp2.data)

        trip = Trip.objects.get(pk=trip_id)
        self.assertEqual(trip.advance_id, self.advance.id)
        self.assertEqual(get_available_balance(self.advance), Decimal('700000'))
        self.assertEqual(AdvanceMovement.objects.filter(trip_id=trip_id).count(), 1)


class TripClientChangeReversalTests(TripAdvanceFixturesMixin, TestCase):
    """Caracterización de reallocate_advance_on_client_change (Fase 1): no
    tenía cobertura propia antes de este cambio (BUG 1 la refactorizó para
    reutilizar reverse_advance_discount) — este test protege que la
    reversión completa al anticipo del cliente anterior, y el nuevo
    descuento contra el anticipo del cliente nuevo, sigan funcionando
    exactamente igual tras la extracción del helper."""

    def test_changing_client_reverses_old_advance_and_funds_new_client_advance(self):
        resp = self._create_trip(value='300000')
        trip_id = resp.data['id']
        self.assertEqual(get_available_balance(self.advance), Decimal('700000'))

        other_owner = User.objects.create_user(
            username='owner2', email='owner2@test.com', name='Owner2',
            role='commercial_admin', password='x12345',
        )
        other_client = Client.objects.create(
            user=other_owner, nit='900999999', name='Otro Cliente',
            abrev_name='OC', address='Calle 2', phone=3000000001,
        )
        other_advance = Advance.objects.create(
            client=other_client, user=self.superuser, value=Decimal('500000'),
            transfer_num=2, date=self.today,
        )
        AdvanceMovement.objects.create(
            advance=other_advance, type_movement='ingreso', amount=Decimal('500000'),
            trips_quantity=0, date=self.today, description='Anticipo inicial otro cliente',
        )

        resp2 = self.api.patch(f'/api/trips/{trip_id}/', {'client': other_client.id}, format='json')
        self.assertEqual(resp2.status_code, status.HTTP_200_OK, resp2.data)

        # El anticipo original queda completamente restaurado.
        self.assertEqual(get_available_balance(self.advance), Decimal('1000000'))
        # El anticipo del cliente nuevo queda descontado por el mismo valor.
        self.assertEqual(get_available_balance(other_advance), Decimal('200000'))

        trip = Trip.objects.get(pk=trip_id)
        self.assertEqual(trip.advance_id, other_advance.id)
        self.assertEqual(trip.client_id, other_client.id)

        self.assertTrue(AuditLog.objects.filter(action='update', model_name='Advance', object_id=self.advance.id).exists())
        self.assertTrue(AuditLog.objects.filter(action='update', model_name='Advance', object_id=other_advance.id).exists())


class InvoicedTripLockAndUnlinkTests(TripAdvanceFixturesMixin, TestCase):
    """8B.4 (diagnóstico de solo lectura): un viaje ya facturado se podía
    seguir editando (valor, cliente, medio de pago) sin ninguna
    restricción, desalineando lo facturado del registro operativo. Ahora
    esos 3 campos quedan bloqueados hasta desvincular la factura
    (superuser o contabilidad, únicos con permiso)."""

    def setUp(self):
        super().setUp()
        self.accountant = User.objects.create_user(
            username='acc_lock1', email='acc_lock1@test.com', name='Contador',
            role='accountant', password='x12345',
        )
        self.accountant_api = APIClient()
        self.accountant_api.force_authenticate(user=self.accountant)

        trip_resp = self._create_trip(value='200000', payment=self.payment_cash)
        self.trip_id = trip_resp.data['id']
        invoice_resp = self.api.post('/api/invoices/', {'number': 'FAC-LOCK-1'}, format='json')
        self.invoice_id = invoice_resp.data['id']
        patch_resp = self.api.patch(
            f'/api/trips/{self.trip_id}/',
            {'invoice': self.invoice_id, 'invoice_pos': 1},
            format='json',
        )
        assert patch_resp.status_code == status.HTTP_200_OK, patch_resp.data

    def test_editing_value_of_invoiced_trip_is_rejected(self):
        resp = self.api.patch(f'/api/trips/{self.trip_id}/', {'value': '999999'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_409_CONFLICT, resp.data)
        trip = Trip.objects.get(pk=self.trip_id)
        self.assertEqual(trip.value, Decimal('200000'))

    def test_editing_client_of_invoiced_trip_is_rejected(self):
        other_client = Client.objects.create(
            user=self.owner_user, nit='900777777', name='Otro Cliente Facturado',
            abrev_name='OCF', address='Calle 2', phone=3000000005,
        )
        resp = self.api.patch(f'/api/trips/{self.trip_id}/', {'client': other_client.id}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_409_CONFLICT, resp.data)

    def test_editing_payment_of_invoiced_trip_is_rejected(self):
        resp = self.api.patch(
            f'/api/trips/{self.trip_id}/', {'payment': self.payment_advance.id}, format='json'
        )
        self.assertEqual(resp.status_code, status.HTTP_409_CONFLICT, resp.data)

    def test_editing_non_financial_field_of_invoiced_trip_still_works(self):
        resp = self.api.patch(
            f'/api/trips/{self.trip_id}/', {'extern_voucher_num': 'EXT-999'}, format='json'
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        trip = Trip.objects.get(pk=self.trip_id)
        self.assertEqual(trip.extern_voucher_num, 'EXT-999')

    def test_editing_value_of_non_invoiced_trip_still_works_normally(self):
        other_resp = self._create_trip(value='100000', payment=self.payment_cash)
        other_id = other_resp.data['id']
        resp = self.api.patch(f'/api/trips/{other_id}/', {'value': '150000'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)

    def test_cashier_and_commercial_admin_cannot_unlink_invoice(self):
        cashier = User.objects.create_user(
            username='cash_lock1', email='cash_lock1@test.com', name='Cajero',
            role='cashier', password='x12345',
        )
        cashier_api = APIClient()
        cashier_api.force_authenticate(user=cashier)

        resp = cashier_api.patch(f'/api/trips/{self.trip_id}/', {'invoice': None}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN, resp.data)

        commercial_api = APIClient()
        commercial_api.force_authenticate(user=self.owner_user)  # commercial_admin
        resp3 = commercial_api.patch(f'/api/trips/{self.trip_id}/', {'invoice': None}, format='json')
        self.assertEqual(resp3.status_code, status.HTTP_403_FORBIDDEN, resp3.data)

        trip = Trip.objects.get(pk=self.trip_id)
        self.assertEqual(trip.invoice_id, self.invoice_id)

    def test_superuser_can_unlink_invoice_and_then_edit_normally(self):
        resp = self.api.patch(f'/api/trips/{self.trip_id}/', {'invoice': None}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)

        trip = Trip.objects.get(pk=self.trip_id)
        self.assertIsNone(trip.invoice_id)
        self.assertIsNone(trip.invoice_pos, 'invoice_pos debe limpiarse junto con invoice')

        # Ya desvinculado, edición normal vuelve a funcionar.
        resp2 = self.api.patch(f'/api/trips/{self.trip_id}/', {'value': '999999'}, format='json')
        self.assertEqual(resp2.status_code, status.HTTP_200_OK, resp2.data)

    def test_accountant_can_unlink_invoice(self):
        resp = self.accountant_api.patch(f'/api/trips/{self.trip_id}/', {'invoice': None}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        trip = Trip.objects.get(pk=self.trip_id)
        self.assertIsNone(trip.invoice_id)

    def test_accountant_cannot_edit_trip_fields_outside_unlink(self):
        """accountant solo tiene permiso para la operación de
        desvincular — sigue sin poder editar viajes normalmente."""
        resp = self.accountant_api.patch(
            f'/api/trips/{self.trip_id}/', {'extern_voucher_num': 'X'}, format='json'
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN, resp.data)

    def test_combining_unlink_with_value_change_in_same_request_is_rejected(self):
        """El flujo es en dos pasos: desvincular, y LUEGO editar — no
        combinado en el mismo PATCH."""
        resp = self.api.patch(
            f'/api/trips/{self.trip_id}/', {'invoice': None, 'value': '999999'}, format='json'
        )
        self.assertEqual(resp.status_code, status.HTTP_409_CONFLICT, resp.data)
        trip = Trip.objects.get(pk=self.trip_id)
        self.assertEqual(trip.invoice_id, self.invoice_id)
        self.assertEqual(trip.value, Decimal('200000'))


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
        execute_close(self.today, source='manual')

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


class ConcurrentTripAdvanceBalanceCheckTests(TransactionTestCase):
    """
    FASE 6.1: dos registros de viaje casi simultáneos contra el mismo
    cliente, con saldo que solo alcanza para uno, no deben poder leer el
    mismo saldo "viejo" y decidir ambos que alcanza (doble descuento) ni
    ambos que no alcanza (ambos como deuda pendiente por error). Antes del
    fix, active_advance/active_balance se leían sin ningún lock, fuera del
    atomic — dos requests concurrentes podían leer el mismo saldo antes de
    que cualquiera de los dos terminara de escribir su AdvanceMovement.

    TransactionTestCase (no TestCase), mismo motivo que
    ConcurrentDoubleCloseRaceTests en cash_closing: los hilos necesitan
    conexiones de BD independientes con commits reales para reproducir la
    carrera; TestCase envuelve todo en una única transacción no confirmada.
    """

    def setUp(self):
        # Nombres de usuario/email deliberadamente distintos a los que usan
        # otros fixtures de este archivo (p. ej. 'super1'): al ser
        # TransactionTestCase (igual que ConcurrentDoubleCloseRaceTests en
        # cash_closing), si el flush de la BD de test entre clases queda
        # pendiente por una fracción de segundo, dos TransactionTestCase
        # con el mismo username/email consecutivos pueden chocar por clave
        # duplicada — con nombres únicos ese choque no puede ocurrir.
        self.superuser = User.objects.create_user(
            username='super_race601', email='super_race601@test.com', name='Super',
            role='superuser', password='x12345',
        )
        self.owner_user = User.objects.create_user(
            username='owner_race601', email='owner_race601@test.com', name='Owner',
            role='commercial_admin', password='x12345',
        )
        self.client_obj = Client.objects.create(
            user=self.owner_user, nit='900123457', name='Cliente Test Concurrencia',
            abrev_name='CTC', address='Calle 1', phone=3000000002,
        )
        vehicle_type = VehicleType.objects.create(name='Volqueta', capacity=Decimal('10.00'))
        self.vehicle = Vehicle.objects.create(vehicle_type=vehicle_type, plaque='XYZ601')
        self.material = MaterialType.objects.create(name='Material Test')
        self.origin = OriginSite.objects.create(name='Origen Test')
        self.payment_advance = PaymentMethod.objects.create(name='Anticipo', is_advance=True)
        self.today = timezone.localdate()

        # Saldo que alcanza para exactamente UNO de los dos viajes de 200000.
        self.advance = Advance.objects.create(
            client=self.client_obj, user=self.superuser, value=Decimal('300000'),
            transfer_num=1, date=self.today,
        )
        AdvanceMovement.objects.create(
            advance=self.advance, type_movement='ingreso', amount=Decimal('300000'),
            trips_quantity=0, date=self.today, description='Anticipo inicial',
        )

    def _post_trip(self):
        api = APIClient()
        api.force_authenticate(user=self.superuser)
        try:
            return api.post('/api/trips/', {
                'payment': self.payment_advance.id,
                'origin_site': self.origin.id,
                'material_type': self.material.id,
                'client': self.client_obj.id,
                'vehicle': self.vehicle.id,
                'value': '200000',
                'date': str(self.today),
                # Por si a este hilo le toca perder la carrera y queda
                # sin saldo suficiente: sin esto el registro se rechazaría
                # con 400 en vez de quedar como deuda pendiente.
                'justification': 'Posible saldo insuficiente bajo concurrencia',
            }, format='json')
        finally:
            connection.close()

    def test_only_one_of_two_concurrent_trips_discounts_the_advance(self):
        results = []
        start_barrier = threading.Barrier(2)

        def worker():
            start_barrier.wait()
            results.append(self._post_trip())

        t1 = threading.Thread(target=worker)
        t2 = threading.Thread(target=worker)
        t1.start()
        t2.start()
        t1.join(timeout=15)
        t2.join(timeout=15)

        self.assertEqual(len(results), 2)
        for r in results:
            self.assertEqual(r.status_code, status.HTTP_201_CREATED, r.data)

        settled = [r for r in results if r.data.get('advance') == self.advance.id]
        pending = [r for r in results if r.data.get('is_pending_debt')]
        self.assertEqual(len(settled), 1, [r.data for r in results])
        self.assertEqual(len(pending), 1, [r.data for r in results])

        # Un solo egreso de 200000 debió aplicarse — no dos.
        self.assertEqual(
            get_available_balance(Advance.objects.get(pk=self.advance.id)),
            Decimal('100000'),
        )
        self.assertEqual(
            AdvanceMovement.objects.filter(advance=self.advance, type_movement='egreso').count(),
            1,
        )


class ConcurrentClientChangeReallocationRaceTests(TransactionTestCase):
    """
    9.1 — reallocate_advance_on_client_change (trips/services.py) no
    bloqueaba la fila del Client destino antes de leer el saldo de su
    anticipo activo. Dos viajes de DOS clientes distintos cambiando su
    cliente al MISMO cliente destino, casi al mismo tiempo, podían leer el
    mismo saldo "viejo" antes de que cualquiera de los dos escribiera su
    AdvanceMovement, y ambos aprobar un descuento que juntos ya no caben
    (doble descuento contra el mismo anticipo). El fix bloquea la fila del
    Client destino (mismo patrón que settle_pending_debts en
    advances/services.py) dentro del mismo transaction.atomic() que ya
    abre TripDetailView.patch.

    TransactionTestCase, mismo motivo que ConcurrentTripAdvanceBalanceCheckTests
    arriba: los hilos necesitan conexiones de BD independientes con commits
    reales para reproducir la carrera; TestCase envuelve todo en una única
    transacción no confirmada.
    """

    def setUp(self):
        self.superuser = User.objects.create_user(
            username='super_race801', email='super_race801@test.com', name='Super',
            role='superuser', password='x12345',
        )
        owner = User.objects.create_user(
            username='owner_race801', email='owner_race801@test.com', name='Owner',
            role='commercial_admin', password='x12345',
        )
        vehicle_type = VehicleType.objects.create(name='Volqueta', capacity=Decimal('10.00'))
        self.vehicle_a = Vehicle.objects.create(vehicle_type=vehicle_type, plaque='XYZ801')
        self.vehicle_b = Vehicle.objects.create(vehicle_type=vehicle_type, plaque='XYZ802')
        self.material = MaterialType.objects.create(name='Material Test')
        self.origin = OriginSite.objects.create(name='Origen Test')
        self.payment_advance = PaymentMethod.objects.create(name='Anticipo', is_advance=True)
        self.today = timezone.localdate()

        # Cliente destino: saldo que alcanza para exactamente UNO de los
        # dos viajes que van a cambiarse hacia él (200000 cada uno).
        self.target_client = Client.objects.create(
            user=owner, nit='900800001', name='Cliente Destino',
            abrev_name='CD', address='Calle 1', phone=3000000010,
        )
        self.target_advance = Advance.objects.create(
            client=self.target_client, user=self.superuser, value=Decimal('300000'),
            transfer_num=1, date=self.today,
        )
        AdvanceMovement.objects.create(
            advance=self.target_advance, type_movement='ingreso', amount=Decimal('300000'),
            trips_quantity=0, date=self.today, description='Anticipo inicial destino',
        )

        # Dos clientes de origen, cada uno con saldo de sobra para financiar
        # su propio viaje — la reversión de su anticipo propio (al cambiar
        # de cliente) no es lo que se está probando, solo el descuento
        # contra el cliente destino compartido.
        source_client_a = Client.objects.create(
            user=owner, nit='900800002', name='Cliente Origen A',
            abrev_name='COA', address='Calle 2', phone=3000000011,
        )
        source_client_b = Client.objects.create(
            user=owner, nit='900800003', name='Cliente Origen B',
            abrev_name='COB', address='Calle 3', phone=3000000012,
        )
        source_advance_a = Advance.objects.create(
            client=source_client_a, user=self.superuser, value=Decimal('1000000'),
            transfer_num=2, date=self.today,
        )
        AdvanceMovement.objects.create(
            advance=source_advance_a, type_movement='ingreso', amount=Decimal('1000000'),
            trips_quantity=0, date=self.today, description='Anticipo inicial A',
        )
        source_advance_b = Advance.objects.create(
            client=source_client_b, user=self.superuser, value=Decimal('1000000'),
            transfer_num=3, date=self.today,
        )
        AdvanceMovement.objects.create(
            advance=source_advance_b, type_movement='ingreso', amount=Decimal('1000000'),
            trips_quantity=0, date=self.today, description='Anticipo inicial B',
        )

        api = APIClient()
        api.force_authenticate(user=self.superuser)
        trip_a_resp = api.post('/api/trips/', {
            'payment': self.payment_advance.id,
            'origin_site': self.origin.id,
            'material_type': self.material.id,
            'client': source_client_a.id,
            'vehicle': self.vehicle_a.id,
            'value': '200000',
            'date': str(self.today),
        }, format='json')
        trip_b_resp = api.post('/api/trips/', {
            'payment': self.payment_advance.id,
            'origin_site': self.origin.id,
            'material_type': self.material.id,
            'client': source_client_b.id,
            'vehicle': self.vehicle_b.id,
            'value': '200000',
            'date': str(self.today),
        }, format='json')
        connection.close()
        assert trip_a_resp.status_code == status.HTTP_201_CREATED, trip_a_resp.data
        assert trip_b_resp.status_code == status.HTTP_201_CREATED, trip_b_resp.data
        self.trip_a_id = trip_a_resp.data['id']
        self.trip_b_id = trip_b_resp.data['id']

    def _patch_client(self, trip_id):
        api = APIClient()
        api.force_authenticate(user=self.superuser)
        try:
            return api.patch(f'/api/trips/{trip_id}/', {
                'client': self.target_client.id,
            }, format='json')
        finally:
            connection.close()

    def test_only_one_of_two_concurrent_client_changes_discounts_target_advance(self):
        results = []
        start_barrier = threading.Barrier(2)

        def worker(trip_id):
            start_barrier.wait()
            results.append(self._patch_client(trip_id))

        t1 = threading.Thread(target=worker, args=(self.trip_a_id,))
        t2 = threading.Thread(target=worker, args=(self.trip_b_id,))
        t1.start()
        t2.start()
        t1.join(timeout=15)
        t2.join(timeout=15)

        self.assertEqual(len(results), 2)
        for r in results:
            self.assertEqual(r.status_code, status.HTTP_200_OK, r.data)

        # Un solo egreso de 200000 debió aplicarse contra el destino — no dos.
        egresos = AdvanceMovement.objects.filter(
            advance=self.target_advance, type_movement='egreso'
        )
        self.assertEqual(
            egresos.count(), 1,
            'solo uno de los dos cambios de cliente debe descontar el anticipo destino',
        )
        self.assertEqual(
            get_available_balance(Advance.objects.get(pk=self.target_advance.id)),
            Decimal('100000'),
        )

        trips = list(Trip.objects.filter(id__in=[self.trip_a_id, self.trip_b_id]))
        settled = [t for t in trips if t.advance_id == self.target_advance.id]
        pending = [t for t in trips if t.advance_id is None]
        self.assertEqual(len(settled), 1, [t.id for t in trips])
        self.assertEqual(
            len(pending), 1,
            'el que pierde la carrera debe quedar como deuda pendiente del cliente destino, no descontado igual',
        )


class FormEncodedAnnulmentDetectionTests(TripAdvanceFixturesMixin, TestCase):
    """
    9.2 — antes de este fix, `request.data.get('state') is False` en
    TripDetailView.patch solo detectaba una anulación cuando 'state' llegaba
    como bool nativo de JSON. Un PATCH form-encoded (`state=false` como
    string) igual anulaba el viaje — el serializer sí normaliza el string a
    False y lo guarda — pero esa comparación cruda nunca lo detectaba, así
    que se saltaba la justificación obligatoria, el AuditLog de tipo
    'annul' (quedaba registrado como 'update' genérico) y la reversión del
    saldo del anticipo. Cubre el mismo camino que los tests de anulación
    JSON ya existentes, pero con format='multipart'.
    """

    def test_form_data_annulment_without_justification_is_rejected(self):
        resp = self._create_trip(value='150000', payment=self.payment_cash)
        trip_id = resp.data['id']

        result = self.api.patch(
            f'/api/trips/{trip_id}/', {'state': False}, format='multipart'
        )
        self.assertEqual(result.status_code, status.HTTP_400_BAD_REQUEST, result.data)
        trip = Trip.objects.get(pk=trip_id)
        self.assertTrue(
            trip.state,
            'el viaje no debe quedar anulado si falta la justificación, ni siquiera vía form-data',
        )

    def test_form_data_annulment_with_justification_is_audited_and_reverts_balance(self):
        resp = self._create_trip(value='300000')  # medio de pago anticipo, descontado de self.advance
        trip_id = resp.data['id']
        self.assertEqual(get_available_balance(self.advance), Decimal('700000'))

        result = self.api.patch(
            f'/api/trips/{trip_id}/',
            {'state': False, 'justification': 'Anulación vía form-data'},
            format='multipart',
        )
        self.assertEqual(result.status_code, status.HTTP_200_OK, result.data)

        trip = Trip.objects.get(pk=trip_id)
        self.assertFalse(trip.state)

        self.assertTrue(
            AuditLog.objects.filter(action='annul', model_name='Trip', object_id=trip_id).exists(),
            'debe quedar auditada específicamente como anulación, igual que la anulación vía JSON',
        )
        self.assertEqual(
            get_available_balance(self.advance), Decimal('1000000'),
            'el saldo del anticipo debe revertirse igual que en la anulación vía JSON',
        )
