import io
from datetime import date, datetime, timezone as dt_timezone
from decimal import Decimal
from unittest.mock import patch

import openpyxl
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.users.models import User
from apps.clients.models import Client
from apps.audit.models import AuditLog
from .models import VehicleType, Tariff, PinsDumper, Vehicle
from .services import parse_pins_from_excel, parse_pins_from_pdf


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


class TariffEndDateUsesBogotaTimezoneTests(TariffFixturesMixin, TestCase):
    """
    9E — TariffDetailView.patch (RF-21, cierra y reemplaza) y
    TariffDetailView.delete (8B.5, cierra sin reemplazo) usaban
    `timezone.now().date()` para fijar `end_date`: eso extrae el día
    calendario en UTC, no en `TIME_ZONE='America/Bogota'` (USE_TZ=True).
    Entre las 19:00 y las 23:59 hora Bogotá (=00:00-04:59 UTC del día
    siguiente), UTC ya cruzó la medianoche pero Bogotá no — `end_date`
    quedaba adelantado un día. El fix usa `timezone.localdate()`, mismo
    mecanismo que ya usa el resto del proyecto (cierre de caja, deuda
    pendiente).

    El proyecto no tiene freezegun ni un mecanismo equivalente instalado
    (no está en requirements.txt) — se usa unittest.mock.patch sobre
    `django.utils.timezone.now`, que es la única función que
    `timezone.localdate()`/`timezone.localtime()` consultan internamente
    cuando no reciben un valor explícito (ver
    django.utils.timezone.localtime: `if value is None: value = now()`),
    así que fijarla también controla de forma determinista cualquier
    `timezone.now()` que llame el código bajo prueba — sin depender de la
    hora real a la que corra la suite (que es justamente lo que hizo que
    el bug se detectara solo algunas veces).
    """

    # 02:00 UTC del 15 de enero de 2026 = 21:00 hora Bogotá del 14 de enero
    # (UTC-5) — dentro de la ventana crítica en la que UTC ya cambió de día
    # calendario pero Bogotá todavía no.
    CRITICAL_UTC_NOW = datetime(2026, 1, 15, 2, 0, 0, tzinfo=dt_timezone.utc)
    EXPECTED_BOGOTA_DATE = date(2026, 1, 14)

    def setUp(self):
        super().setUp()
        create_resp = self.api.post('/api/masters/tariffs/', {
            'client': self.client_obj.id, 'vehicle_type': self.vehicle_type.id,
            'value': '80000', 'start_date': str(self.today),
        }, format='json')
        assert create_resp.status_code == status.HTTP_201_CREATED, create_resp.data
        self.tariff_id = create_resp.data['id']

    def test_delete_sets_end_date_to_bogota_date_in_critical_utc_window(self):
        with patch('django.utils.timezone.now', return_value=self.CRITICAL_UTC_NOW):
            resp = self.api.delete(f'/api/masters/tariffs/{self.tariff_id}/')
        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT, resp.data)

        tariff = Tariff.objects.get(pk=self.tariff_id)
        self.assertEqual(
            tariff.end_date, self.EXPECTED_BOGOTA_DATE,
            'end_date debe quedar en la fecha Bogotá, no un día adelantado por tomar la fecha UTC cruda',
        )

    def test_patch_replacement_closes_old_tariff_with_bogota_date_in_critical_utc_window(self):
        with patch('django.utils.timezone.now', return_value=self.CRITICAL_UTC_NOW):
            resp = self.api.patch(f'/api/masters/tariffs/{self.tariff_id}/', {
                'value': '90000',
            }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)

        old_tariff = Tariff.objects.get(pk=self.tariff_id)
        self.assertFalse(old_tariff.state)
        self.assertEqual(
            old_tariff.end_date, self.EXPECTED_BOGOTA_DATE,
            'la tarifa cerrada por reemplazo (RF-21) debe quedar con la fecha Bogotá, no la fecha UTC',
        )

        new_tariff = Tariff.objects.get(pk=resp.data['id'])
        self.assertTrue(new_tariff.state)
        self.assertEqual(new_tariff.value, Decimal('90000'))


# ── Importador de pines (RF-23) ─────────────────────────────────────────────
class FakePdfPage:
    def __init__(self, table):
        self._table = table

    def extract_table(self):
        return self._table


class FakePdf:
    """Reemplazo mínimo de pdfplumber.PDF para simular páginas del listado
    oficial sin depender de un PDF real en los tests."""

    def __init__(self, pages):
        self.pages = pages

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def make_pdf_row(pin, nombre='NOMBRE X', direccion='DIRECCION X', telefono='3001234567',
                  email='x@test.com', placa='ABC123', lugar='BOGOTA', modelo='2020',
                  capacidad='10', conductor='CONDUCTOR X', fecha='01/11/2012', estado='ACTIVO'):
    return [pin, nombre, direccion, telefono, email, placa, lugar, modelo,
            capacidad, conductor, fecha, estado]


PDF_HEADER = ['PIN', 'NOMBRE', 'DIRECCION', 'TELEFONO', 'E_MAIL', 'PLACA',
              'LUGAR EXPEDICIÓN', 'MODELO', 'CAPACIDAD', 'CONDUCTOR',
              'FECHA REGISTRO', 'ESTADO']


class PinsDumperExcelImportTests(TestCase):
    def _build_workbook(self, rows, headers=None):
        headers = headers or EXCEL_HEADERS
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(headers)
        for row in rows:
            ws.append(row)
        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)
        return buf

    def test_creates_new_pins(self):
        f = self._build_workbook([
            ['P1', 'JUAN PEREZ', 'CL 1', '3001112233', 'juan@test.com',
             'ABC123', 'BOGOTA', '2020', '10', 'PEDRO GOMEZ', '01/11/2012', 'ACTIVO'],
        ])
        result = parse_pins_from_excel(f)
        self.assertTrue(result['success'], result)
        self.assertEqual(result['created'], 1)
        self.assertEqual(result['updated'], 0)
        pin = PinsDumper.objects.get(ambiental_pin='P1')
        self.assertEqual(pin.plaque, 'ABC123')
        self.assertTrue(pin.state)
        self.assertEqual(pin.date_register, date(2012, 11, 1))

    def test_reimport_same_pin_updates_instead_of_duplicating(self):
        f1 = self._build_workbook([
            ['P1', 'JUAN PEREZ', 'CL 1', '3001112233', 'juan@test.com',
             'ABC123', 'BOGOTA', '2020', '10', 'PEDRO GOMEZ', '01/11/2012', 'ACTIVO'],
        ])
        parse_pins_from_excel(f1)

        f2 = self._build_workbook([
            ['P1', 'JUAN PEREZ', 'CL 1', '3001112233', 'juan@test.com',
             'ABC123', 'BOGOTA', '2020', '10', 'PEDRO GOMEZ', '01/11/2012', 'FINALIZADO'],
        ])
        result = parse_pins_from_excel(f2)

        self.assertEqual(result['created'], 0)
        self.assertEqual(result['updated'], 1)
        self.assertEqual(PinsDumper.objects.filter(ambiental_pin='P1').count(), 1)
        self.assertFalse(PinsDumper.objects.get(ambiental_pin='P1').state)

    def test_missing_plaque_is_rejected(self):
        """Un PIN sin placa no sirve para nada de lo que usa el sistema
        (vale, Vehicle.dumper) — se descarta, incluso si el resto de la
        fila es válido."""
        f = self._build_workbook([
            ['P2', 'MARIA LOPEZ', 'CL 2', '', 'maria@test.com',
             '', '', '', '', '', '01/11/2012', 'FINALIZADO'],
        ])
        result = parse_pins_from_excel(f)
        self.assertEqual(result['created'], 0)
        self.assertEqual(result['rejected_count'], 1)
        self.assertFalse(PinsDumper.objects.filter(ambiental_pin='P2').exists())

    def test_missing_pin_is_rejected(self):
        f = self._build_workbook([
            ['', 'MARIA LOPEZ', 'CL 2', '', 'maria@test.com',
             'ABC123', 'BOGOTA', '2020', '10', 'COND', '01/11/2012', 'ACTIVO'],
        ])
        result = parse_pins_from_excel(f)
        self.assertEqual(result['created'], 0)
        self.assertEqual(result['rejected_count'], 1)

    def test_invalid_date_is_rejected_without_aborting_import(self):
        f = self._build_workbook([
            ['P3', 'A', 'CL 1', '', 'a@test.com', 'ABC123', 'BOGOTA', '2020', '10', 'C', 'fecha-mala', 'ACTIVO'],
            ['P4', 'B', 'CL 1', '', 'b@test.com', 'XYZ987', 'BOGOTA', '2020', '10', 'C', '02/11/2012', 'ACTIVO'],
        ])
        result = parse_pins_from_excel(f)
        self.assertEqual(result['created'], 1)
        self.assertEqual(result['rejected_count'], 1)
        self.assertTrue(PinsDumper.objects.filter(ambiental_pin='P4').exists())
        self.assertFalse(PinsDumper.objects.filter(ambiental_pin='P3').exists())

    def test_capacity_thousands_separator_is_normalized(self):
        f = self._build_workbook([
            ['P5', 'A', 'CL 1', '', 'a@test.com', 'ABC123', 'BOGOTA', '2020', '15,750', 'C', '01/11/2012', 'ACTIVO'],
        ])
        parse_pins_from_excel(f)
        self.assertEqual(PinsDumper.objects.get(ambiental_pin='P5').capacity, Decimal('15750'))

    def test_capacity_decimal_comma_is_normalized(self):
        f = self._build_workbook([
            ['P6', 'A', 'CL 1', '', 'a@test.com', 'ABC123', 'BOGOTA', '2020', '4,8', 'C', '01/11/2012', 'ACTIVO'],
        ])
        parse_pins_from_excel(f)
        self.assertEqual(PinsDumper.objects.get(ambiental_pin='P6').capacity, Decimal('4.8'))

    def test_vehicle_dumper_is_synced_for_existing_plaque(self):
        Vehicle.objects.create(
            vehicle_type=VehicleType.objects.create(name='Volqueta', capacity=Decimal('10')),
            plaque='ABC123',
        )
        f = self._build_workbook([
            ['P7', 'A', 'CL 1', '', 'a@test.com', 'ABC123', 'BOGOTA', '2020', '10', 'C', '01/11/2012', 'ACTIVO'],
        ])
        result = parse_pins_from_excel(f)
        self.assertEqual(result['vehicles_synced'], 1)
        vehicle = Vehicle.objects.get(plaque='ABC123')
        self.assertEqual(vehicle.dumper.ambiental_pin, 'P7')


EXCEL_HEADERS = ['PIN', 'NOMBRE', 'DIRECCION', 'TELEFONO', 'E_MAIL', 'PLACA',
                  'LUGAR_EXPEDICION', 'MODELO', 'CAPACIDAD', 'CONDUCTOR',
                  'FECHA_REGISTRO', 'ESTADO']


class PinsDumperPdfImportTests(TestCase):
    def test_only_first_page_header_is_skipped(self):
        pages = [
            FakePdfPage([PDF_HEADER, make_pdf_row('P1', placa='AAA111'), make_pdf_row('P2', placa='BBB222')]),
            FakePdfPage([make_pdf_row('P3', placa='CCC333'), make_pdf_row('P4', placa='DDD444')]),
        ]
        with patch('pdfplumber.open', return_value=FakePdf(pages)):
            result = parse_pins_from_pdf(io.BytesIO(b'%PDF-fake'))

        self.assertTrue(result['success'], result)
        self.assertEqual(result['created'], 4)
        self.assertEqual(
            set(PinsDumper.objects.values_list('ambiental_pin', flat=True)),
            {'P1', 'P2', 'P3', 'P4'},
        )

    def test_finalizado_row_without_plaque_is_rejected(self):
        row = ['P5', 'MANUEL SANCHEZ', 'CR 85 A 77 A 46', '', 'manuel@test.com',
               '', '', '', '', 'MANUEL SANCHEZ', '01/11/2012', 'FINALIZADO']
        pages = [FakePdfPage([PDF_HEADER, row])]
        with patch('pdfplumber.open', return_value=FakePdf(pages)):
            result = parse_pins_from_pdf(io.BytesIO(b'%PDF-fake'))

        self.assertEqual(result['created'], 0)
        self.assertEqual(result['rejected_count'], 1)
        self.assertFalse(PinsDumper.objects.filter(ambiental_pin='P5').exists())

    def test_missing_capacity_is_still_tolerated(self):
        """La placa es obligatoria, pero capacidad/modelo/conductor/
        teléfono siguen siendo opcionales (RF-23) — el listado real trae
        filas ACTIVO con placa pero sin esos otros datos."""
        row = ['P5B', 'MANUEL SANCHEZ', 'CR 85 A 77 A 46', '', 'manuel@test.com',
               'ABC123', '', '', '', '', '01/11/2012', 'ACTIVO']
        pages = [FakePdfPage([PDF_HEADER, row])]
        with patch('pdfplumber.open', return_value=FakePdf(pages)):
            result = parse_pins_from_pdf(io.BytesIO(b'%PDF-fake'))

        self.assertEqual(result['created'], 1)
        self.assertEqual(result['rejected_count'], 0)
        pin = PinsDumper.objects.get(ambiental_pin='P5B')
        self.assertIsNone(pin.capacity)
        self.assertIsNone(pin.phone)

    def test_estado_other_than_activo_maps_to_inactive(self):
        pages = [FakePdfPage([
            PDF_HEADER,
            make_pdf_row('P6', placa='AAA666', estado='ACTIVO'),
            make_pdf_row('P7', placa='BBB777', estado='AHCETZIVO'),
            make_pdf_row('P8', placa='CCC888', estado=''),
        ])]
        with patch('pdfplumber.open', return_value=FakePdf(pages)):
            parse_pins_from_pdf(io.BytesIO(b'%PDF-fake'))

        self.assertTrue(PinsDumper.objects.get(ambiental_pin='P6').state)
        self.assertFalse(PinsDumper.objects.get(ambiental_pin='P7').state)
        self.assertFalse(PinsDumper.objects.get(ambiental_pin='P8').state)

    def test_reimport_is_idempotent_by_pin(self):
        pages = [FakePdfPage([PDF_HEADER, make_pdf_row('P9', estado='ACTIVO')])]
        with patch('pdfplumber.open', return_value=FakePdf(pages)):
            parse_pins_from_pdf(io.BytesIO(b'%PDF-fake'))

        pages2 = [FakePdfPage([PDF_HEADER, make_pdf_row('P9', estado='FINALIZADO')])]
        with patch('pdfplumber.open', return_value=FakePdf(pages2)):
            result = parse_pins_from_pdf(io.BytesIO(b'%PDF-fake'))

        self.assertEqual(result['created'], 0)
        self.assertEqual(result['updated'], 1)
        self.assertEqual(PinsDumper.objects.filter(ambiental_pin='P9').count(), 1)
        self.assertFalse(PinsDumper.objects.get(ambiental_pin='P9').state)

    def test_capacity_thousands_separator_is_normalized(self):
        pages = [FakePdfPage([PDF_HEADER, make_pdf_row('P10', capacidad='15,750')])]
        with patch('pdfplumber.open', return_value=FakePdf(pages)):
            parse_pins_from_pdf(io.BytesIO(b'%PDF-fake'))

        self.assertEqual(PinsDumper.objects.get(ambiental_pin='P10').capacity, Decimal('15750'))

    def test_row_without_pin_is_rejected_without_aborting(self):
        pages = [FakePdfPage([
            PDF_HEADER,
            make_pdf_row(''),
            make_pdf_row('P11'),
        ])]
        with patch('pdfplumber.open', return_value=FakePdf(pages)):
            result = parse_pins_from_pdf(io.BytesIO(b'%PDF-fake'))

        self.assertEqual(result['created'], 1)
        self.assertEqual(result['rejected_count'], 1)

    def test_bulk_path_still_uppercases_text_fields(self):
        """bulk_create()/bulk_update() no pasan por PinsDumper.save() (que
        normalmente uppercasea vía uppercase_fields()) — el importador debe
        replicar esa normalización a mano para no romper la convención del
        resto del sistema."""
        row = make_pdf_row('P13', nombre='juan perez', direccion='calle falsa 123',
                            lugar='bogota', modelo='volqueta doble', conductor='pedro gomez')
        pages = [FakePdfPage([PDF_HEADER, row])]
        with patch('pdfplumber.open', return_value=FakePdf(pages)):
            parse_pins_from_pdf(io.BytesIO(b'%PDF-fake'))

        pin = PinsDumper.objects.get(ambiental_pin='P13')
        self.assertEqual(pin.propietary, 'JUAN PEREZ')
        self.assertEqual(pin.address, 'CALLE FALSA 123')
        self.assertEqual(pin.expedition_site, 'BOGOTA')
        self.assertEqual(pin.model, 'VOLQUETA DOBLE')
        self.assertEqual(pin.driver, 'PEDRO GOMEZ')

    def test_within_file_duplicate_pin_collapses_to_last_occurrence(self):
        """El PDF oficial trae PINs genuinamente repetidos dentro del mismo
        archivo (varias filas para el mismo PIN, con datos distintos). El
        importador por lotes deduplica en memoria antes de tocar la BD:
        debe quedar un solo registro, con los datos de la última
        ocurrencia — el mismo resultado que un upsert fila-por-fila en
        orden, pero sin contarlo como 'created' + 'updated' extra."""
        pages = [FakePdfPage([
            PDF_HEADER,
            make_pdf_row('P12', placa='AAA111', conductor='PRIMERO'),
            make_pdf_row('P12', placa='BBB222', conductor='SEGUNDO'),
            make_pdf_row('P12', placa='CCC333', conductor='ULTIMO'),
        ])]
        with patch('pdfplumber.open', return_value=FakePdf(pages)):
            result = parse_pins_from_pdf(io.BytesIO(b'%PDF-fake'))

        self.assertEqual(result['read'], 3)
        self.assertEqual(result['created'], 1)
        self.assertEqual(result['updated'], 0)
        self.assertEqual(PinsDumper.objects.filter(ambiental_pin='P12').count(), 1)
        pin = PinsDumper.objects.get(ambiental_pin='P12')
        self.assertEqual(pin.plaque, 'CCC333')
        self.assertEqual(pin.driver, 'ULTIMO')

    def test_only_the_most_recent_pin_per_plaque_is_kept(self):
        """El listado oficial es histórico: una misma placa acumula un PIN
        distinto por cada re-registro a través de los años. Solo debe
        quedar el más reciente por fecha — los PIN anteriores para esa
        misma placa se rechazan en vez de acumularse como registros
        muertos."""
        pages = [FakePdfPage([
            PDF_HEADER,
            make_pdf_row('P30', placa='XYZ111', fecha='01/11/2012'),
            make_pdf_row('P31', placa='XYZ111', fecha='21/08/2018'),
            make_pdf_row('P32', placa='XYZ111', fecha='22/08/2018'),
        ])]
        with patch('pdfplumber.open', return_value=FakePdf(pages)):
            result = parse_pins_from_pdf(io.BytesIO(b'%PDF-fake'))

        self.assertEqual(result['read'], 3)
        self.assertEqual(result['created'], 1)
        self.assertEqual(result['rejected_count'], 2)
        self.assertEqual(PinsDumper.objects.filter(plaque='XYZ111').count(), 1)
        self.assertTrue(PinsDumper.objects.filter(ambiental_pin='P32').exists())
        self.assertFalse(PinsDumper.objects.filter(ambiental_pin='P30').exists())
        self.assertFalse(PinsDumper.objects.filter(ambiental_pin='P31').exists())

    def test_most_recent_per_plaque_tie_breaks_by_file_order(self):
        pages = [FakePdfPage([
            PDF_HEADER,
            make_pdf_row('P33', placa='XYZ222', fecha='22/08/2018', conductor='PRIMERO'),
            make_pdf_row('P34', placa='XYZ222', fecha='22/08/2018', conductor='ULTIMO'),
        ])]
        with patch('pdfplumber.open', return_value=FakePdf(pages)):
            result = parse_pins_from_pdf(io.BytesIO(b'%PDF-fake'))

        self.assertEqual(result['created'], 1)
        self.assertTrue(PinsDumper.objects.filter(ambiental_pin='P34').exists())
        self.assertFalse(PinsDumper.objects.filter(ambiental_pin='P33').exists())

    def test_different_plaques_are_not_affected_by_each_others_history(self):
        pages = [FakePdfPage([
            PDF_HEADER,
            make_pdf_row('P35', placa='AAA000', fecha='01/11/2012'),
            make_pdf_row('P36', placa='BBB000', fecha='01/11/2012'),
        ])]
        with patch('pdfplumber.open', return_value=FakePdf(pages)):
            result = parse_pins_from_pdf(io.BytesIO(b'%PDF-fake'))

        self.assertEqual(result['created'], 2)
        self.assertEqual(result['rejected_count'], 0)

    def test_active_pin_beats_a_more_recent_finalizado_one_for_the_same_plaque(self):
        """~31 placas reales tienen un PIN FINALIZADO con fecha más
        reciente que otro PIN ACTIVO más viejo de la misma placa (un
        re-registro que se cerró después). La fecha más reciente sola no
        basta: el vigente (ACTIVO) debe ganar aunque su fecha sea
        anterior — si no, Vehicle.dumper terminaría apuntando a un
        registro cerrado."""
        pages = [FakePdfPage([
            PDF_HEADER,
            make_pdf_row('P37', placa='XYZ333', fecha='01/01/2020', estado='ACTIVO'),
            make_pdf_row('P38', placa='XYZ333', fecha='01/01/2023', estado='FINALIZADO'),
        ])]
        with patch('pdfplumber.open', return_value=FakePdf(pages)):
            result = parse_pins_from_pdf(io.BytesIO(b'%PDF-fake'))

        self.assertEqual(result['created'], 1)
        self.assertTrue(PinsDumper.objects.filter(ambiental_pin='P37').exists())
        self.assertFalse(PinsDumper.objects.filter(ambiental_pin='P38').exists())


class PinsDumperImportViewTests(TariffFixturesMixin, TestCase):
    def test_pdf_upload_is_routed_to_pdf_parser(self):
        pages = [FakePdfPage([PDF_HEADER, make_pdf_row('P20')])]
        with patch('pdfplumber.open', return_value=FakePdf(pages)):
            upload = SimpleUploadedFile('pines.pdf', b'%PDF-1.4 fake', content_type='application/pdf')
            resp = self.api.post('/api/masters/pins/import/', {'file': upload}, format='multipart')

        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        self.assertEqual(resp.data['created'], 1)
        self.assertTrue(PinsDumper.objects.filter(ambiental_pin='P20').exists())

    def test_unsupported_extension_is_rejected(self):
        upload = SimpleUploadedFile('pines.txt', b'hello', content_type='text/plain')
        resp = self.api.post('/api/masters/pins/import/', {'file': upload}, format='multipart')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_cashier_cannot_import_pins(self):
        upload = SimpleUploadedFile('pines.txt', b'hello', content_type='text/plain')
        resp = self.cashier_api.post('/api/masters/pins/import/', {'file': upload}, format='multipart')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)


class PinsDumperCreateSyncsVehicleTests(TariffFixturesMixin, TestCase):
    """Un vehículo puede quedar registrado con dumper=null porque se creó
    al vuelo desde un viaje antes de que su PIN existiera en el sistema.
    Registrar ese PIN manualmente (POST /masters/pins/) debe enlazarlo de
    una vez, igual que ya hacía la importación masiva (RF-23)."""

    def test_creating_a_pin_links_an_existing_vehicle_with_the_same_plaque(self):
        Vehicle.objects.create(
            vehicle_type=self.vehicle_type, plaque='ABC123',
        )
        resp = self.api.post('/api/masters/pins/', {
            'ambiental_pin': 'P100', 'propietary': 'JUAN PEREZ', 'address': 'CL 1',
            'phone': '3001112233', 'email': 'juan@test.com', 'plaque': 'ABC123',
            'expedition_site': 'BOGOTA', 'model': '2020', 'capacity': '10',
            'driver': 'PEDRO GOMEZ', 'date_register': str(self.today),
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)

        vehicle = Vehicle.objects.get(plaque='ABC123')
        self.assertIsNotNone(vehicle.dumper)
        self.assertEqual(vehicle.dumper.ambiental_pin, 'P100')

    def test_creating_a_pin_for_a_plaque_without_a_vehicle_does_not_error(self):
        resp = self.api.post('/api/masters/pins/', {
            'ambiental_pin': 'P101', 'propietary': 'JUAN PEREZ', 'address': 'CL 1',
            'phone': '3001112233', 'email': 'juan@test.com', 'plaque': 'ZZZ999',
            'expedition_site': 'BOGOTA', 'model': '2020', 'capacity': '10',
            'driver': 'PEDRO GOMEZ', 'date_register': str(self.today),
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
