from django.db import models
from apps.users.models import User
from apps.clients.models import Client

MOVEMENT_TYPE_CHOICES = [
    ('ingreso', 'Ingreso'),
    ('egreso', 'Egreso'),
]


class Advance(models.Model):
    id = models.AutoField(primary_key=True)
    client = models.ForeignKey(Client, on_delete=models.RESTRICT)
    user = models.ForeignKey(User, on_delete=models.RESTRICT)
    value = models.DecimalField(max_digits=15, decimal_places=2)
    transfer_num = models.IntegerField()
    date = models.DateField()
    proforma_number = models.IntegerField(null=True, blank=True)
    observations = models.TextField(null=True, blank=True)

    class Meta:
        db_table = 'ADVANCE'

    def __str__(self):
        return f'Anticipo {self.client} - {self.value}'


class AdvanceMovement(models.Model):
    id = models.AutoField(primary_key=True)
    advance = models.ForeignKey(Advance, on_delete=models.RESTRICT)
    trip = models.ForeignKey('trips.Trip', on_delete=models.RESTRICT, null=True, blank=True)
    type_movement = models.CharField(max_length=30, choices=MOVEMENT_TYPE_CHOICES)
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    trips_quantity = models.IntegerField()
    date = models.DateField()
    description = models.TextField(null=True, blank=True)

    class Meta:
        db_table = 'ADVANCE_MOVEMENT'

    def __str__(self):
        return f'{self.type_movement} - {self.amount}'