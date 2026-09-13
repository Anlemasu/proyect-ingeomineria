from django.db import migrations


def backfill_expected_trips_quantity(apps, schema_editor):
    """
    El nuevo módulo "Reporte Físico" (apps.physical_reports) lee
    Advance.expected_trips_quantity, pero ese campo es nuevo — los anticipos
    creados ANTES de este cambio nunca lo tuvieron, aunque muchos ya
    guardaban el mismo dato en AdvanceMovement.trips_quantity (el
    movimiento de 'ingreso' inicial, ver AdvanceListCreateView.post). Sin
    este backfill, esos anticipos aparecerían en "Reporte Físico" pidiendo
    "Definir cupo" para un dato que el sistema ya tenía.
    """
    Advance = apps.get_model('advances', 'Advance')
    AdvanceMovement = apps.get_model('advances', 'AdvanceMovement')

    initial_movements = (
        AdvanceMovement.objects.filter(
            type_movement='ingreso', trips_quantity__gt=0,
            advance__expected_trips_quantity__isnull=True,
        )
        .order_by('advance_id', 'id')
        .values('advance_id', 'trips_quantity')
    )
    # Un anticipo puede tener varios movimientos de 'ingreso' con
    # trips_quantity > 0 (p.ej. el inicial y alguna corrección posterior);
    # nos quedamos con el PRIMERO por anticipo, que es el que representa el
    # cupo esperado original declarado al crearlo.
    quantity_by_advance: dict[int, int] = {}
    for row in initial_movements:
        quantity_by_advance.setdefault(row['advance_id'], row['trips_quantity'])

    for advance_id, quantity in quantity_by_advance.items():
        Advance.objects.filter(pk=advance_id).update(expected_trips_quantity=quantity)


def noop_reverse(apps, schema_editor):
    # No revertimos el backfill: quitarlo no restaura ningún estado previo
    # útil, y dejar el cupo ya definido no rompe nada si se hace rollback.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('advances', '0003_advance_expected_trips_quantity'),
    ]

    operations = [
        migrations.RunPython(backfill_expected_trips_quantity, noop_reverse),
    ]
