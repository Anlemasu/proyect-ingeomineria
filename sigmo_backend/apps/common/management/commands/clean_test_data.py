from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection

from apps.advances.models import Advance, AdvanceMovement
from apps.audit.models import AuditLog
from apps.cash_closing.models import DailySummary, DailySummaryPayment
from apps.clients.models import Client
from apps.expenses.models import Expense
from apps.invoices.models import Invoice
from apps.masters.models import (
    City, MaterialType, OriginSite, PaymentMethod, PinsDumper, Tariff, Vehicle, VehicleType,
)
from apps.trips.models import Trip

# Orden irrelevante para TRUNCATE (todas las tablas referenciadas se listan
# juntas en el mismo statement), pero se mantiene de "hoja" a "raíz" para
# que los conteos impresos antes de borrar sean fáciles de leer.
TARGET_MODELS = [
    Trip,
    AdvanceMovement,
    Advance,
    Invoice,
    DailySummaryPayment,
    DailySummary,
    Expense,
    AuditLog,
]

# Solo se incluyen con --full: clientes y catálogos de masters. USER nunca
# se toca (ni siquiera con --full).
CATALOG_MODELS = [
    Tariff,
    Vehicle,
    PinsDumper,
    VehicleType,
    MaterialType,
    PaymentMethod,
    OriginSite,
    Client,
    City,
]


class Command(BaseCommand):
    help = (
        'Vacía las tablas transaccionales de prueba (viajes, anticipos, '
        'cierres de caja, facturas, gastos, auditoría) y reinicia sus '
        'contadores de id/voucher_num a 1. Con --full también borra clientes '
        'y todos los catálogos de masters (vehículos, tipos, tarifas, etc.). '
        'En ningún caso toca la tabla de usuarios.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--yes', action='store_true',
            help='No pedir confirmación interactiva.',
        )
        parser.add_argument(
            '--full', action='store_true',
            help='También borra clientes y catálogos de masters (todo excepto Usuarios).',
        )

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError(
                'DEBUG=False: este comando solo corre contra una base de '
                'desarrollo. Abortado por seguridad.'
            )

        models = TARGET_MODELS + CATALOG_MODELS if options['full'] else TARGET_MODELS

        self.stdout.write('Conteo actual:')
        for model in models:
            self.stdout.write(f'  {model.__name__}: {model.objects.count()}')

        if not options['yes']:
            scope = 'TODO (excepto Usuarios)' if options['full'] else 'las tablas de arriba'
            answer = input(
                f'\nEsto BORRA {scope} y reinicia los contadores. '
                'Escribí CONFIRMAR para continuar: '
            )
            if answer.strip() != 'CONFIRMAR':
                self.stdout.write(self.style.WARNING('Cancelado.'))
                return

        tables = ', '.join(
            connection.ops.quote_name(model._meta.db_table)
            for model in models
        )
        with connection.cursor() as cursor:
            cursor.execute(f'TRUNCATE TABLE {tables} RESTART IDENTITY')

        self.stdout.write(self.style.SUCCESS(
            'Listo. Tablas vacías, contadores (id, voucher_num) reiniciados en 1.'
        ))
