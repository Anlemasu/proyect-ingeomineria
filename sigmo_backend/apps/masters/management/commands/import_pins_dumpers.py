from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

DEFAULT_PDF_NAME = 'TRANSPORTADORES INSCRITOS ESCOMBROS_2026.pdf'


class Command(BaseCommand):
    help = (
        'Importa pines ambientales de transportadores/volquetas (RF-23) a '
        'PINS_DUMPERS desde el PDF oficial de la SDA o desde un Excel '
        'exportado del mismo listado. Es idempotente por PIN: reimportar '
        'el mismo archivo actualiza los registros existentes en vez de '
        'duplicarlos.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--file', type=str, default=None,
            help=(
                'Ruta al archivo .pdf o .xlsx a importar. Por defecto usa '
                f'"public/{DEFAULT_PDF_NAME}" dentro del proyecto.'
            ),
        )

    def handle(self, *args, **options):
        file_path = options['file']
        if file_path:
            path = Path(file_path)
        else:
            path = Path(settings.BASE_DIR) / 'public' / DEFAULT_PDF_NAME

        if not path.exists():
            raise CommandError(f'No se encontró el archivo: {path}')

        suffix = path.suffix.lower()
        if suffix == '.pdf':
            from apps.masters.services import parse_pins_from_pdf as parse_fn
        elif suffix in ('.xlsx', '.csv'):
            from apps.masters.services import parse_pins_from_excel as parse_fn
        else:
            raise CommandError(f'Extensión no soportada: "{suffix}". Use .pdf o .xlsx.')

        self.stdout.write(f'Importando pines desde: {path}')

        with path.open('rb') as f:
            result = parse_fn(f)

        if not result.get('success'):
            raise CommandError(result.get('error', 'Error desconocido al importar.'))

        self.stdout.write(self.style.SUCCESS(
            f"Filas leídas: {result['read']} | "
            f"creados: {result['created']} | "
            f"actualizados: {result['updated']} | "
            f"omitidos: {result['rejected_count']} | "
            f"vehículos sincronizados: {result['vehicles_synced']}"
        ))

        if result['rejected']:
            self.stdout.write(self.style.WARNING(f"Detalle de {result['rejected_count']} filas omitidas:"))
            for item in result['rejected']:
                self.stdout.write(f"  - {item['fila']}: {item['motivo']}")
