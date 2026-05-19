from django.db import models
from apps.clients.models import Client


class VehicleType(models.Model):
    name = models.CharField(max_length=20)
    capacity = models.DecimalField(max_digits=10, decimal_places=2)
    description = models.TextField(null=True, blank=True)
    state = models.BooleanField(default=True)

    class Meta:
        db_table = 'VEHICLE_TYPE'

    def __str__(self):
        return self.name


class PinsDumper(models.Model):
    ambiental_pin = models.CharField(max_length=30)
    propietary = models.CharField(max_length=50)
    address = models.CharField(max_length=20)
    phone = models.DecimalField(max_digits=10, decimal_places=0)
    email = models.CharField(max_length=20)
    plaque = models.CharField(max_length=6)
    expedition_site = models.CharField(max_length=20)
    model = models.CharField(max_length=50)
    capacity = models.DecimalField(max_digits=10, decimal_places=2)
    driver = models.CharField(max_length=50)
    date_register = models.DateField()
    state = models.BooleanField(default=True)

    class Meta:
        db_table = 'PINS_DUMPERS'

    def __str__(self):
        return f'{self.plaque} - {self.ambiental_pin}'


class Vehicle(models.Model):
    vehicle_type = models.ForeignKey(VehicleType, on_delete=models.RESTRICT)
    dumper = models.ForeignKey(PinsDumper, on_delete=models.RESTRICT, null=True, blank=True)
    plaque = models.CharField(max_length=6, unique=True)

    class Meta:
        db_table = 'VEHICLE'

    def __str__(self):
        return self.plaque


class MaterialType(models.Model):
    name = models.CharField(max_length=30)
    description = models.TextField(null=True, blank=True)
    state = models.BooleanField(default=True)

    class Meta:
        db_table = 'MATERIAL_TYPE'

    def __str__(self):
        return self.name


class PaymentMethod(models.Model):
    name = models.CharField(max_length=20)
    is_advance = models.BooleanField(default=False)
    state = models.BooleanField(default=True)

    class Meta:
        db_table = 'PAYMENT_METHOD'

    def __str__(self):
        return self.name


class OriginSite(models.Model):
    name = models.CharField(max_length=50)
    state = models.BooleanField(default=True)

    class Meta:
        db_table = 'ORIGIN_SITE'

    def __str__(self):
        return self.name


class Tariff(models.Model):
    client = models.ForeignKey(Client, on_delete=models.RESTRICT, null=True, blank=True)
    vehicle_type = models.ForeignKey(VehicleType, on_delete=models.RESTRICT)
    material_type = models.ForeignKey(MaterialType, on_delete=models.RESTRICT, null=True, blank=True)
    value = models.DecimalField(max_digits=15, decimal_places=2)
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    state = models.BooleanField(default=True)

    class Meta:
        db_table = 'TARIFF'

    def __str__(self):
        return f'{self.client} - {self.vehicle_type} - {self.value}'