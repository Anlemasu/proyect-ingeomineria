from django.db.models import Count, Sum


def _row(r):
    return {
        'client': r['client'],
        'client_name': r['client__name'],
        'trips_count': r['trips_count'],
        # str(): Sum() sobre un DecimalField devuelve Decimal, no el 'or 0'
        # de abajo (int) — sin convertir, un Decimal crudo llegaba intacto
        # hasta AuditLog.new_data (ver DailySummarySerializer.client_details,
        # un SerializerMethodField que DRF no coerciona como sí hace con los
        # DecimalField declarados) y json.dumps no sabe serializarlo. Mismo
        # formato string que ya esperaba el frontend (ver TripsByClientRow).
        'total_value': str(r['total_value'] or 0),
        'total_volume': str(r['total_volume'] or 0),
    }


def build_trips_by_client(trips):
    """
    Desglose "viajes por cliente" a partir de un queryset de Trip que el
    caller ya filtró a state=True.

    Devuelve una lista de dicts ordenada por cantidad de viajes (desc) con,
    por cada cliente: conteo de viajes, valor total y volumen m³ (capacidad
    del tipo de vehículo, misma métrica que usa recalculate_daily_summary
    para total_volume).

    Se centraliza aquí para que el resumen del día en curso
    (DailySummaryTodayView) y el detalle de un cierre histórico
    (DailySummarySerializer.client_details) devuelvan exactamente el mismo
    formato — el histórico se calcula en vivo desde los TRIP vinculados al
    cierre, no se persiste.
    """
    rows = (
        trips.values('client', 'client__name')
        .annotate(
            trips_count=Count('id'),
            total_value=Sum('value'),
            total_volume=Sum('vehicle__vehicle_type__capacity'),
        )
        .order_by('-trips_count', 'client__name')
    )
    return [_row(r) for r in rows]


def build_trips_by_client_by_summary(summary_ids):
    """
    Igual que build_trips_by_client pero para VARIOS cierres a la vez, en una
    sola consulta agregada — evita el N+1 al serializar el histórico de
    cierres (DailySummaryListView). Devuelve {summary_id: [filas...]},
    cada lista ordenada por cantidad de viajes desc.
    """
    from apps.trips.models import Trip  # import diferido: evita ciclo con trips.models

    rows = (
        Trip.objects.filter(summary_id__in=list(summary_ids), state=True)
        .values('summary', 'client', 'client__name')
        .annotate(
            trips_count=Count('id'),
            total_value=Sum('value'),
            total_volume=Sum('vehicle__vehicle_type__capacity'),
        )
        .order_by('-trips_count', 'client__name')
    )
    result: dict = {}
    for r in rows:
        result.setdefault(r['summary'], []).append(_row(r))
    return result
