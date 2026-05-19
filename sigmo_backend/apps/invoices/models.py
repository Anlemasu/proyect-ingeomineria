from django.db import models
from apps.users.models import User


class Invoice(models.Model):
    user = models.ForeignKey(User, on_delete=models.RESTRICT)
    number = models.CharField(max_length=15)

    class Meta:
        db_table = 'INVOICE'

    def __str__(self):
        return self.number