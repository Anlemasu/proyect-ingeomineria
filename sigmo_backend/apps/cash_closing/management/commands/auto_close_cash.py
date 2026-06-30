from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.cash_closing.services import execute_close, AlreadyClosedError
from apps.audit.services import log_action


class Command(BaseCommand):
    help = 'Ejecuta el cierre de caja automático si no fue cerrado manualmente.'

    def handle(self, *args, **options):
        today = timezone.now().date()
        self.stdout.write(f'[auto_close_cash] Verificando cierre para {today}...')

        try:
            summary = execute_close(today)
            self.stdout.write(
                self.style.SUCCESS(
                    f'[auto_close_cash] Cierre ejecutado: {summary.total_trips} viajes, '
                    f'fecha {summary.date}.'
                )
            )
        except AlreadyClosedError:
            self.stdout.write(
                self.style.WARNING(
                    f'[auto_close_cash] El día {today} ya tiene cierre de caja. Sin acción.'
                )
            )
        except Exception as e:
            self.stderr.write(
                self.style.ERROR(f'[auto_close_cash] Error al ejecutar el cierre: {e}')
            )
            raise SystemExit(1)
