from decimal import Decimal
from datetime import timedelta
from unittest import mock

from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.users.models import User
from apps.audit.models import AuditLog
from apps.cash_closing.models import DailySummary
from apps.cash_closing.services import execute_close
from .models import Expense


class ExpenseFixturesMixin:
    def setUp(self):
        self.superuser = User.objects.create_user(
            username='super1', email='super1@test.com', name='Super',
            role='superuser', password='x12345',
        )
        self.cashier = User.objects.create_user(
            username='cash1', email='cash1@test.com', name='Cajero',
            role='cashier', password='x12345',
        )
        self.today = timezone.localdate()
        self.super_api = APIClient()
        self.super_api.force_authenticate(user=self.superuser)
        self.cashier_api = APIClient()
        self.cashier_api.force_authenticate(user=self.cashier)


class ExpenseAnnulmentTests(ExpenseFixturesMixin, TestCase):
    """FASE 5.3: Expense gana un campo `state` para poder anularse con
    trazabilidad, con las mismas reglas de día cerrado que ya existen para
    Trip (RF-37)."""

    def setUp(self):
        super().setUp()
        self.expense = Expense.objects.create(
            user=self.cashier, value=Decimal('50000'),
            description='Combustible', date=self.today,
        )

    def test_cashier_can_annul_expense_with_justification(self):
        resp = self.cashier_api.patch(
            f'/api/expenses/{self.expense.id}/',
            {'state': False, 'justification': 'Registrado por error'},
            format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        self.expense.refresh_from_db()
        self.assertFalse(self.expense.state)

        log = AuditLog.objects.filter(model_name='Expense', object_id=self.expense.id, action='annul').first()
        self.assertIsNotNone(log)
        self.assertEqual(log.justification, 'Registrado por error')

    def test_annul_without_justification_is_rejected(self):
        resp = self.cashier_api.patch(
            f'/api/expenses/{self.expense.id}/', {'state': False}, format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.expense.refresh_from_db()
        self.assertTrue(self.expense.state)

    def test_cannot_modify_an_already_annulled_expense(self):
        self.expense.state = False
        self.expense.save(update_fields=['state'])

        resp = self.cashier_api.patch(
            f'/api/expenses/{self.expense.id}/', {'value': '60000'}, format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_non_superuser_cannot_touch_expense_of_closed_day(self):
        execute_close(self.today, user=self.superuser)

        resp = self.cashier_api.patch(
            f'/api/expenses/{self.expense.id}/',
            {'state': False, 'justification': 'x'},
            format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_409_CONFLICT)
        self.expense.refresh_from_db()
        self.assertTrue(self.expense.state)

    def test_superuser_can_annul_expense_of_closed_day_and_summary_resyncs(self):
        summary = execute_close(self.today, user=self.superuser)
        self.assertEqual(summary.total_expenses, Decimal('50000'))

        resp = self.super_api.patch(
            f'/api/expenses/{self.expense.id}/',
            {'state': False, 'justification': 'Ajuste histórico'},
            format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)

        summary.refresh_from_db()
        self.assertEqual(summary.total_expenses, Decimal('0'))


class ExpenseAnnulmentAtomicWithResyncTests(ExpenseFixturesMixin, TestCase):
    """8B.1 (diagnóstico de solo lectura): la anulación/edición del gasto y
    el recálculo del DailySummary corrían como dos pasos independientes,
    sin transaction.atomic() — si el recálculo fallaba a mitad de camino,
    el gasto podía quedar anulado/editado sin que el cierre se hubiera
    actualizado. Se simula esa falla mockeando resync_if_closed."""

    def setUp(self):
        super().setUp()
        self.expense = Expense.objects.create(
            user=self.cashier, value=Decimal('50000'),
            description='Combustible', date=self.today,
        )

    def test_failure_during_resync_rolls_back_the_expense_change_too(self):
        execute_close(self.today, user=self.superuser)

        with mock.patch(
            'apps.expenses.views.resync_if_closed',
            side_effect=Exception('fallo simulado a mitad del recálculo'),
        ):
            with self.assertRaises(Exception):
                self.super_api.patch(
                    f'/api/expenses/{self.expense.id}/',
                    {'state': False, 'justification': 'Ajuste histórico'},
                    format='json',
                )

        # El rollback del atomic() debe deshacer también la anulación del
        # gasto, no solo el recálculo que falló.
        self.expense.refresh_from_db()
        self.assertTrue(self.expense.state, 'el gasto no debe quedar anulado si el recálculo falló')


class ExpenseDateEditClosedDayValidationTests(ExpenseFixturesMixin, TestCase):
    """8B.2 (diagnóstico de solo lectura): la validación de "día cerrado"
    solo miraba la fecha ACTUAL del gasto, nunca la fecha NUEVA propuesta
    en el mismo PATCH — cambiar `date` hacia o desde un día cerrado evadía
    el bloqueo por completo."""

    def setUp(self):
        super().setUp()
        self.expense = Expense.objects.create(
            user=self.cashier, value=Decimal('50000'),
            description='Combustible', date=self.today,
        )

    def test_moving_expense_from_closed_day_to_open_day_is_rejected(self):
        execute_close(self.today, user=self.superuser)
        open_day = self.today + timedelta(days=1)

        resp = self.cashier_api.patch(
            f'/api/expenses/{self.expense.id}/',
            {'date': str(open_day), 'value': '99999'},
            format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_409_CONFLICT, resp.data)

        self.expense.refresh_from_db()
        self.assertEqual(self.expense.date, self.today)
        self.assertEqual(self.expense.value, Decimal('50000'))

    def test_moving_expense_from_open_day_into_closed_day_is_rejected(self):
        closed_day = self.today + timedelta(days=1)
        execute_close(closed_day, user=self.superuser)

        resp = self.cashier_api.patch(
            f'/api/expenses/{self.expense.id}/',
            {'date': str(closed_day)},
            format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_409_CONFLICT, resp.data)

        self.expense.refresh_from_db()
        self.assertEqual(self.expense.date, self.today)


class ExpenseTotalsExcludeAnnulledTests(ExpenseFixturesMixin, TestCase):
    """recalculate_daily_summary (vía execute_close) no debe sumar gastos
    anulados en los totales del cierre."""

    def test_annulled_expense_excluded_from_daily_summary_total(self):
        Expense.objects.create(
            user=self.cashier, value=Decimal('30000'),
            description='Activo', date=self.today, state=True,
        )
        Expense.objects.create(
            user=self.cashier, value=Decimal('99999'),
            description='Anulado antes de cerrar', date=self.today, state=False,
        )

        summary = execute_close(self.today, user=self.superuser)
        self.assertEqual(summary.total_expenses, Decimal('30000'))


class ExpenseCreationTests(ExpenseFixturesMixin, TestCase):
    """
    FASE 6.4: cobertura que faltaba sobre la creación de gastos en sí (las
    pruebas de Fase 5 partían de gastos ya creados por ORM directamente
    para probar la anulación) — camino feliz, validación de valor,
    control de rol y el bloqueo por día cerrado que ya existía en
    ExpenseListCreateView.post pero no tenía ningún test.
    """

    def test_cashier_can_create_expense(self):
        resp = self.cashier_api.post('/api/expenses/', {
            'description': 'Peaje', 'value': '25000', 'date': str(self.today),
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        self.assertTrue(resp.data['state'])
        self.assertEqual(resp.data['user'], self.cashier.id)
        self.assertTrue(
            AuditLog.objects.filter(action='create', model_name='Expense', object_id=resp.data['id']).exists()
        )

    def test_expense_with_zero_value_is_rejected(self):
        resp = self.cashier_api.post('/api/expenses/', {
            'description': 'Peaje', 'value': '0', 'date': str(self.today),
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST, resp.data)

    def test_auditor_cannot_create_expense(self):
        auditor = User.objects.create_user(
            username='audit1', email='audit1@test.com', name='Auditor',
            role='auditor', password='x12345',
        )
        api = APIClient()
        api.force_authenticate(user=auditor)
        resp = api.post('/api/expenses/', {
            'description': 'Peaje', 'value': '25000', 'date': str(self.today),
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN, resp.data)
        self.assertEqual(Expense.objects.count(), 0)

    def test_new_expense_blocked_on_closed_day(self):
        execute_close(self.today, user=self.superuser)

        resp = self.cashier_api.post('/api/expenses/', {
            'description': 'Peaje', 'value': '25000', 'date': str(self.today),
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_409_CONFLICT, resp.data)
        self.assertEqual(Expense.objects.count(), 0)
