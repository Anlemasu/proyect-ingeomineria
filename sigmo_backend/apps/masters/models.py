from django.db import models
from apps.clients.models import Client
from apps.common.text import uppercase_fields


class VehicleType(models.Model):
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=20)
    capacity = models.DecimalField(max_digits=10, decimal_places=2)
    description = models.TextField(null=True, blank=True)
    state = models.BooleanField(default=True)

    class Meta:
        db_table = 'VEHICLE_TYPE'

    def save(self, *args, **kwargs):
        uppercase_fields(self, 'name')
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class PinsDumper(models.Model):
    id = models.AutoField(primary_key=True)
    # unique: es la clave de idempotencia del importador (RF-23) — la SDA
    # reemite el listado periódicamente con la misma numeración de PIN.
    ambiental_pin = models.CharField(max_length=30, unique=True)
    propietary = models.CharField(max_length=50)
    # 100: el listado oficial trae direcciones de hasta ~73 caracteres,
    # muy por encima del límite original de 20.
    address = models.CharField(max_length=100)
    # null/blank: el teléfono viene vacío en ~30% de las filas del listado
    # oficial (RF-23).
    phone = models.DecimalField(max_digits=10, decimal_places=0, null=True, blank=True)
    # 100: igual que address, el listado trae correos de hasta ~60 caracteres.
    email = models.CharField(max_length=100)
    # blank: filas con ESTADO=FINALIZADO en el listado oficial no traen placa.
    plaque = models.CharField(max_length=6, blank=True)
    expedition_site = models.CharField(max_length=30, blank=True)
    model = models.CharField(max_length=50, blank=True)
    # null/blank: mismo caso que placa, ausente en filas FINALIZADO.
    capacity = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    driver = models.CharField(max_length=50, blank=True)
    date_register = models.DateField()
    state = models.BooleanField(default=True)

    class Meta:
        db_table = 'PINS_DUMPERS'

    def save(self, *args, **kwargs):
        uppercase_fields(
            self, 'ambiental_pin', 'propietary', 'address', 'plaque',
            'expedition_site', 'model', 'driver',
        )
        super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.plaque} - {self.ambiental_pin}'


class Vehicle(models.Model):
    id = models.AutoField(primary_key=True)
    vehicle_type = models.ForeignKey(VehicleType, on_delete=models.RESTRICT)
    dumper = models.ForeignKey(PinsDumper, on_delete=models.RESTRICT, null=True, blank=True)
    plaque = models.CharField(max_length=6, unique=True)

    class Meta:
        db_table = 'VEHICLE'

    def save(self, *args, **kwargs):
        uppercase_fields(self, 'plaque')
        super().save(*args, **kwargs)

    def __str__(self):
        return self.plaque


class MaterialType(models.Model):
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=30)
    description = models.TextField(null=True, blank=True)
    state = models.BooleanField(default=True)

    class Meta:
        db_table = 'MATERIAL_TYPE'

    def save(self, *args, **kwargs):
        uppercase_fields(self, 'name')
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class PaymentMethod(models.Model):
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=20)
    is_advance = models.BooleanField(default=False)
    state = models.BooleanField(default=True)

    class Meta:
        db_table = 'PAYMENT_METHOD'

    def save(self, *args, **kwargs):
        uppercase_fields(self, 'name')
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class OriginSite(models.Model):
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=50)
    state = models.BooleanField(default=True)

    class Meta:
        db_table = 'ORIGIN_SITE'

    def save(self, *args, **kwargs):
        uppercase_fields(self, 'name')
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class City(models.Model):
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=50)
    state = models.BooleanField(default=True)

    class Meta:
        db_table = 'CITY'

    def save(self, *args, **kwargs):
        uppercase_fields(self, 'name')
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class Tariff(models.Model):
    id = models.AutoField(primary_key=True)
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