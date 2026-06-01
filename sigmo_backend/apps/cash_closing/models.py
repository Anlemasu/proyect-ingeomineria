from django.db import models


class DailySummary(models.Model):
    id = models.AutoField(primary_key=True)
    date = models.DateField()
    total_trips = models.IntegerField()
    total_volume = models.DecimalField(max_digits=15, decimal_places=2)
    avg_trip_value = models.DecimalField(max_digits=15, decimal_places=2)
    total_expenses = models.DecimalField(max_digits=15, decimal_places=2)

    class Meta:
        db_table = 'DAILY_SUMMARY'

    def __str__(self):
        return f'Cierre {self.date}'


class DailySummaryPayment(models.Model):
    id = models.AutoField(primary_key=True)
    summary = models.ForeignKey(
        DailySummary,
        on_delete=models.RESTRICT,
        related_name='payment_details'
    )
    payment_method = models.ForeignKey(
        'masters.PaymentMethod',
        on_delete=models.RESTRICT
    )
    total = models.DecimalField(max_digits=15, decimal_places=2)

    class Meta:
        db_table = 'DAILY_SUMMARY_PAYMENT'

    def __str__(self):
        return f'{self.summary.date} - {self.payment_method.name}: {self.total}'