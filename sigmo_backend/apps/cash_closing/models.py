from django.db import models


class DailySummary(models.Model):
    STATE_CLOSED = 'closed'
    STATE_REVERTED = 'reverted'
    STATE_CHOICES = [
        (STATE_CLOSED, 'Cerrado'),
        (STATE_REVERTED, 'Revertido'),
    ]

    id = models.AutoField(primary_key=True)
    # unique=True: un mismo día no puede tener dos cierres. Es la guarda
    # real contra la condición de carrera de dos cierres simultáneos —
    # el chequeo ".exists()" en el código de servicio no alcanza porque
    # dos transacciones pueden pasarlo al mismo tiempo antes de que
    # ninguna haya insertado su fila. La base de datos, en cambio, no dejará
    # que la segunda inserción concurrente se complete (ver execute_close).
    date = models.DateField(unique=True)
    # closed = cierre vigente, bloquea nuevos viajes/gastos de ese día.
    # reverted = el superusuario lo revirtió; la fila se conserva para no
    # perder el histórico de que existió un cierre.
    state = models.CharField(max_length=10, choices=STATE_CHOICES, default=STATE_CLOSED)
    total_trips = models.IntegerField()
    total_volume = models.DecimalField(max_digits=15, decimal_places=2)
    avg_trip_value = models.DecimalField(max_digits=15, decimal_places=2)
    total_expenses = models.DecimalField(max_digits=15, decimal_places=2)

    class Meta:
        db_table = 'DAILY_SUMMARY'

    def __str__(self):
        return f'Cierre {self.date} ({self.state})'


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