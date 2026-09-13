from django.db import models
from apps.users.models import User
from apps.advances.models import Advance

CLOSURE_ACTION_CHOICES = [
    ('close', 'Cerrar'),
    ('undo_close', 'Deshacer cierre'),
    ('reopen', 'Reabrir'),
]


class PhysicalCountEntry(models.Model):
    """
    Bitácora append-only del conteo físico diario de vales por anticipo.

    Nunca se edita ni se borra un registro existente: corregir el conteo de
    un día ya guardado crea un registro NUEVO para el mismo (advance, date) —
    mismo principio que AdvanceMovement en apps.advances. El valor vigente de
    un día es el último registro (por id) para ese (advance, date); ver
    apps.physical_reports.services.get_latest_entries_by_date.
    """
    id = models.AutoField(primary_key=True)
    advance = models.ForeignKey(Advance, on_delete=models.RESTRICT)
    date = models.DateField()
    count = models.IntegerField()
    user = models.ForeignKey(User, on_delete=models.RESTRICT)
    created_at = models.DateTimeField(auto_now_add=True)
    # Obligatorio solo cuando ya existía un registro previo para este mismo
    # (advance, date) — validado en el serializer/servicio, no aquí.
    justification = models.TextField(null=True, blank=True)

    class Meta:
        db_table = 'PHYSICAL_COUNT_ENTRY'

    def __str__(self):
        return f'Conteo físico {self.advance_id} - {self.date} - {self.count}'


class PhysicalCountClosure(models.Model):
    """
    Bitácora append-only de cierre/reapertura del conteo físico de un
    anticipo. El estado vigente de un anticipo es el de la última acción
    (ver apps.physical_reports.services.is_closed): 'close' = cerrado,
    'undo_close'/'reopen' = abierto, sin ninguna acción todavía = abierto.
    """
    id = models.AutoField(primary_key=True)
    advance = models.ForeignKey(Advance, on_delete=models.RESTRICT)
    action = models.CharField(max_length=20, choices=CLOSURE_ACTION_CHOICES)
    user = models.ForeignKey(User, on_delete=models.RESTRICT)
    created_at = models.DateTimeField(auto_now_add=True)
    # Obligatorio solo para 'reopen' (una reapertura después de que ya pasó
    # la ventana de deshacer inmediato, ver services.UNDO_WINDOW_MINUTES).
    justification = models.TextField(null=True, blank=True)

    class Meta:
        db_table = 'PHYSICAL_COUNT_CLOSURE'

    def __str__(self):
        return f'{self.action} - anticipo {self.advance_id}'
