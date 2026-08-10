from django.db import models
from apps.users.models import User
from apps.common.text import uppercase_fields
from apps.clients.models import Client
from apps.masters.models import Vehicle, MaterialType, PaymentMethod, OriginSite
from apps.invoices.models import Invoice
from apps.cash_closing.models import DailySummary
from apps.advances.models import Advance


class Trip(models.Model):
    id = models.AutoField(primary_key=True)
    invoice = models.ForeignKey(Invoice, on_delete=models.RESTRICT, null=True, blank=True)
    payment = models.ForeignKey(PaymentMethod, on_delete=models.RESTRICT)
    origin_site = models.ForeignKey(OriginSite, on_delete=models.RESTRICT)
    material_type = models.ForeignKey(MaterialType, on_delete=models.RESTRICT)
    client = models.ForeignKey(Client, on_delete=models.RESTRICT)
    summary = models.ForeignKey(DailySummary, on_delete=models.RESTRICT, null=True, blank=True)
    vehicle = models.ForeignKey(Vehicle, on_delete=models.RESTRICT)
    advance = models.ForeignKey(Advance, on_delete=models.RESTRICT, null=True, blank=True)
    voucher_num = models.IntegerField(unique=True)
    value = models.DecimalField(max_digits=15, decimal_places=2)
    extern_voucher_num = models.CharField(max_length=20, null=True, blank=True)
    invoice_pos = models.IntegerField(null=True, blank=True)
    date_register = models.DateTimeField()
    date = models.DateField()
    certification_state = models.BooleanField(null=True, blank=True)
    certification_num = models.CharField(max_length=30, null=True, blank=True)
    state = models.BooleanField(default=True)
    # FASE 3 — decisión de modelo de datos para "deuda pendiente":
    # se reutiliza `advance IS NULL` en un viaje pagado con medio "anticipo"
    # (payment.is_advance=True) para representar "todavía no se liquidó
    # contra ningún anticipo". No se creó una tabla nueva porque ese estado
    # ya es 100% derivable de campos existentes (payment.is_advance +
    # advance IS NULL + state=True) — antes de esta fase, `advance=NULL`
    # con `payment.is_advance=True` estaba prohibido por validación
    # (TripWriteSerializer exigía un anticipo siempre); se revisó ese
    # camino y no lo usaba nada más, así que quedó libre para este
    # significado nuevo sin chocar con ningún otro uso.
    # Este campo solo guarda la justificación capturada en el momento del
    # registro sin saldo suficiente; se conserva aunque el viaje después se
    # liquide o se anule (es un dato histórico de por qué nació pendiente).
    pending_debt_justification = models.TextField(null=True, blank=True)
    observations = models.TextField(null=True, blank=True)

    class Meta:
        db_table = 'TRIP'

    def save(self, *args, **kwargs):
        uppercase_fields(self, 'extern_voucher_num', 'certification_num')
        super().save(*args, **kwargs)

    def __str__(self):
        return f'Viaje {self.voucher_num} - {self.client}'