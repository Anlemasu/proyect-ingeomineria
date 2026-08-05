from django.db import IntegrityError, transaction
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from apps.users.models import User
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
