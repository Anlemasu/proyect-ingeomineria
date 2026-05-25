from django.db import models
from apps.users.models import User


class Expense(models.Model):
    id = models.AutoField(primary_key=True)
    user = models.ForeignKey(User, on_delete=models.RESTRICT)
    value = models.DecimalField(max_digits=15, decimal_places=2)
    description = models.TextField()
    date = models.DateField()

    class Meta:
        db_table = 'EXPENSE'

    def __str__(self):
        return f'{self.description} - {self.value}'