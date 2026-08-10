import datetime

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.cash_closing.services import execute_close, AlreadyClosedError


class Command(BaseCommand):
    help = 'Ejecuta el cierre de caja automático si no fue cerrado manualmente.'

    def handle(self, *args, **options):
        # Se ejecuta a las 00:00 vía Task Scheduler, momento en el que ya
        # empezó el día siguiente: hay que cerrar el día que acaba de
        # terminar (ayer), no el que recién comienza (hoy), o se bloquea de
        # inmediato el registro de viajes del día actual.
        target_date = timezone.localdate() - datetime.timedelta(days=1)
        self.stdout.write(f'[auto_close_cash] Verificando cierre para {target_date}...')

        try:
            # source='auto': execute_close deja el registro en AuditLog con
            # user=None (no hay un usuario HTTP autenticado en un cron) y una
            # justificación indicando que fue un cierre automático — antes
            # este comando no dejaba ningún rastro de auditoría.
            summary = execute_close(target_date, source='auto')
            self.stdout.write(
                self.style.SUCCESS(
                    f'[auto_close_cash] Cierre ejecutado: {summary.total_trips} viajes, '
                    f'fecha {summary.date}.'
                )
            )
        except AlreadyClosedError:
            self.stdout.write(
                self.style.WARNING(
                    f'[auto_close_cash] El día {target_date} ya tiene cierre de caja. Sin acción.'
                )
            )
        except Exception as e:
            self.stderr.write(
                self.style.ERROR(f'[auto_close_cash] Error al ejecutar el cierre: {e}')
            )
            raise SystemExit(1)
