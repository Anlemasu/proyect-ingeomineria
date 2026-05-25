from django.db import models
from apps.users.models import User
from apps.clients.models import Client
from apps.masters.models import Vehicle, MaterialType, PaymentMethod, OriginSite
from apps.invoices.models import Invoice
from apps.cash_closing.models import DailySummary
from apps.advances.models import Advance


class Trip(models.Model):
    id = models.AutoField(primary_key=True)
    invoice = models.ForeignKey(Invoice, on_delete=models.RESTRICT, null=True, blank=True)
    payment = models.ForeignKey(PaymentMethod, on_delete=models.RESTRICT)
    origin_site = models.ForeignKey(OriginSite, on_delete=models.RESTRICT)
    material_type = models.ForeignKey(MaterialType, on_delete=models.RESTRICT)
    client = models.ForeignKey(Client, on_delete=models.RESTRICT)
    summary = models.ForeignKey(DailySummary, on_delete=models.RESTRICT, null=True, blank=True)
    vehicle = models.ForeignKey(Vehicle, on_delete=models.RESTRICT)
    advance = models.ForeignKey(Advance, on_delete=models.RESTRICT, null=True, blank=True)
    voucher_num = models.IntegerField(unique=True)
    value = models.DecimalField(max_digits=15, decimal_places=2)
    extern_voucher_num = models.CharField(max_length=20, null=True, blank=True)
    invoice_pos = models.IntegerField(null=True, blank=True)
    date_register = models.DateField()
    date = models.DateField()
    certification_state = models.BooleanField(null=True, blank=True)
    certification_num = models.CharField(max_length=30, null=True, blank=True)
    state = models.BooleanField(default=True)

    class Meta:
        db_table = 'TRIP'

    def __str__(self):
        return f'Viaje {self.voucher_num} - {self.client}'


class Transfer(models.Model):
    trip = models.ForeignKey(Trip, on_delete=models.RESTRICT)
    number = models.IntegerField()

    class Meta:
        db_table = 'TRANSFER'

    def __str__(self):
        return f'Transferencia {self.number}'