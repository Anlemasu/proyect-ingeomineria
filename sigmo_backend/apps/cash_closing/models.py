from django.db import models


class DailySummary(models.Model):
    date = models.DateField()
    total_trips = models.DecimalField(max_digits=15, decimal_places=2)
    total_volume = models.DecimalField(max_digits=15, decimal_places=2)
    income_cash = models.DecimalField(max_digits=15, decimal_places=2)
    income_transfer = models.DecimalField(max_digits=15, decimal_places=2)
    income_advance = models.DecimalField(max_digits=15, decimal_places=2)
    avg_trip_value = models.DecimalField(max_digits=15, decimal_places=2)
    total_expenses = models.DecimalField(max_digits=15, decimal_places=2)

    class Meta:
        db_table = 'DAILY_SUMMARY'

    def __str__(self):
        return f'Cierre {self.date}'