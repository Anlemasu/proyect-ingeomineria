from django.db import models
from apps.users.models import User


class Client(models.Model):
    user = models.ForeignKey(User, on_delete=models.RESTRICT)
    nit = models.CharField(max_length=15, unique=True)
    name = models.CharField(max_length=50)
    abrev_name = models.CharField(max_length=20)
    address = models.CharField(max_length=20)
    phone = models.DecimalField(max_digits=10, decimal_places=0)
    city = models.CharField(max_length=20, blank=True, null=True)
    facturation_name = models.CharField(max_length=50, blank=True, null=True)
    email = models.CharField(max_length=30, blank=True, null=True)
    validate_certification = models.BooleanField(null=True)
    state = models.BooleanField(default=True)

    class Meta:
        db_table = 'CLIENT'

    def __str__(self):
        return f'{self.name} ({self.nit})'