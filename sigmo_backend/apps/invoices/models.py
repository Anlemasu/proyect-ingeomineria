from django.db import models
from apps.users.models import User
from apps.common.text import uppercase_fields


class Invoice(models.Model):
    id = models.AutoField(primary_key=True)
    user = models.ForeignKey(User, on_delete=models.RESTRICT)
    number = models.CharField(max_length=15, unique=True)

    class Meta:
        db_table = 'INVOICE'

    def save(self, *args, **kwargs):
        uppercase_fields(self, 'number')
        super().save(*args, **kwargs)

    def __str__(self):
        return self.number