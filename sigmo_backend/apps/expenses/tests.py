from decimal import Decimal

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
