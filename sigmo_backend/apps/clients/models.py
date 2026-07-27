from django.db import models
from apps.users.models import User
from apps.common.text import uppercase_fields


class Client(models.Model):
    id = models.AutoField(primary_key=True)
    user = models.ForeignKey(User, on_delete=models.RESTRICT)
    nit = models.CharField(max_length=15, unique=True)
    name = models.CharField(max_length=50)
    abrev_name = models.CharField(max_length=20)
    address = models.CharField(max_length=20)
    phone = models.DecimalField(max_digits=10, decimal_places=0)
    city = models.ForeignKey('masters.City', on_delete=models.RESTRICT, null=True, blank=True)
    facturation_name = models.CharField(max_length=50, blank=True, null=True)
    email = models.CharField(max_length=30, blank=True, null=True)
    validate_certification = models.BooleanField(null=True)
    state = models.BooleanField(default=True)

    class Meta:
        db_table = 'CLIENT'

    def save(self, *args, **kwargs):
        uppercase_fields(self, 'nit', 'name', 'abrev_name', 'address', 'facturation_name')
        super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.name} ({self.nit})'