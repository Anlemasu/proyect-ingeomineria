from django.db import models
from apps.clients.models import Client
from apps.masters.models import PaymentMethod
from apps.users.models import User

ENTRY_TYPE_CHOICES = [
    ('advance', 'Anticipo'),
    ('transfer', 'Transferencia'),
]

STATUS_CHOICES = [
    ('pending', 'Pendiente'),
    ('executed', 'Ejecutado'),
    ('cancelled', 'Cancelado'),
]


class PendingEntry(models.Model):
    """
    Aviso de un anticipo o una transferencia que un cliente va a cargar
    próximamente, registrado por auditor/superusuario (ver
    can_manage_pending_entries en views.py) para que quede visible al resto
    de roles y se pueda relacionar con el registro real cuando se cree.

    'advance' se relaciona con un Advance (saldo acumulable, no exige
    coincidencia de valor). 'transfer' se relaciona con un Trip puntual y sí
    exige que el valor coincida exactamente (ver
    apps.pending_entries.services.execute_pending_transfer) — por eso
    `payment_method` solo aplica a este segundo caso: es el medio de pago
    que se autocompletará en el viaje al ejecutar.
    """
    id = models.AutoField(primary_key=True)
    entry_type = models.CharField(max_length=20, choices=ENTRY_TYPE_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    client = models.ForeignKey(Client, on_delete=models.RESTRICT)
    value = models.DecimalField(max_digits=15, decimal_places=2)
    date = models.DateField()
    # Obligatorio solo si entry_type='transfer', prohibido si es 'advance'
    # (ver PendingEntryWriteSerializer.validate). Lo elige manualmente quien
    # registra el pendiente, de la lista de medios de pago ya existente.
    payment_method = models.ForeignKey(
        PaymentMethod, on_delete=models.RESTRICT, null=True, blank=True
    )
    observations = models.TextField(null=True, blank=True)

    # Vínculo al registro real creado al ejecutar — mutuamente excluyentes
    # según entry_type. related_name='+': Advance/Trip no necesitan navegar
    # de vuelta a esto, siempre se consulta desde PendingEntry.
    executed_advance = models.ForeignKey(
        'advances.Advance', on_delete=models.RESTRICT, null=True, blank=True, related_name='+'
    )
    executed_trip = models.ForeignKey(
        'trips.Trip', on_delete=models.RESTRICT, null=True, blank=True, related_name='+'
    )

    created_by = models.ForeignKey(User, on_delete=models.RESTRICT, related_name='+')
    executed_by = models.ForeignKey(User, on_delete=models.RESTRICT, null=True, blank=True, related_name='+')
    executed_at = models.DateTimeField(null=True, blank=True)
    cancelled_by = models.ForeignKey(User, on_delete=models.RESTRICT, null=True, blank=True, related_name='+')
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancellation_justification = models.TextField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'PENDING_ENTRY'

    def __str__(self):
        return f'{self.entry_type} pendiente - {self.client} - {self.value}'
