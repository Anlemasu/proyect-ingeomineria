from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.cash_closing.models import DailySummary
from apps.cash_closing.services import execute_close, AlreadyClosedError
from apps.trips.models import Trip


class Command(BaseCommand):
    help = (
        'Repara cierres de caja que quedaron sin ejecutar por fallas del '
        'cron (ver auto_close_cash.log — varias fechas de julio y agosto '
        'de 2026 quedaron sin cierre). Recorre un rango de fechas hacia '
        'atrás y cierra retroactivamente los días que tienen viajes '
        'activos pero ningún DailySummary asociado. Nunca toca un día que '
        'ya tiene un DailySummary (cerrado o revertido) — solo repara '
        'días completamente huérfanos, para no pisar una reversión '
        'intencional del superusuario.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--days', type=int, default=30,
            help='Cuántos días hacia atrás revisar desde hoy (por defecto 30).'
        )
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Solo lista las fechas huérfanas detectadas, sin cerrarlas.'
        )

    def handle(self, *args, **options):
        days = options['days']
        dry_run = options['dry_run']
        today = timezone.localdate()
        start = today - timedelta(days=days)

        # El día de hoy se excluye a propósito: todavía está "abierto" y su
        # cierre le corresponde a auto_close_cash / al cierre manual, no a
        # una reparación retroactiva.
        existing_dates = set(
            DailySummary.objects.filter(date__gte=start, date__lt=today)
            .values_list('date', flat=True)
        )
        trip_dates = set(
            Trip.objects.filter(date__gte=start, date__lt=today, state=True)
            .values_list('date', flat=True)
            .distinct()
        )
        missing_dates = sorted(trip_dates - existing_dates)

        if not missing_dates:
            self.stdout.write(self.style.SUCCESS(
                f'No hay cierres huérfanos en los últimos {days} días.'
            ))
            return

        self.stdout.write(
            f'Fechas sin cierre detectadas ({len(missing_dates)}): '
            f'{", ".join(str(d) for d in missing_dates)}'
        )
        if dry_run:
            self.stdout.write(self.style.WARNING('--dry-run: no se ejecutó ningún cierre.'))
            return

        for date in missing_dates:
            try:
                summary = execute_close(date, source='recovery')
                self.stdout.write(self.style.SUCCESS(
                    f'  {date}: cierre creado ({summary.total_trips} viajes, '
                    f'gastos {summary.total_expenses}).'
                ))
            except AlreadyClosedError:
                # Otro proceso (p. ej. auto_close_cash corriendo en paralelo)
                # cerró esta fecha entre la detección y el intento de cierre.
                self.stdout.write(self.style.WARNING(
                    f'  {date}: ya tiene cierre (se adelantó otro proceso), se omite.'
                ))
            except Exception as e:
                self.stderr.write(self.style.ERROR(f'  {date}: error al cerrar — {e}'))
