from django.db import models
from apps.users.models import User


class AuditLog(models.Model):

    ACTION_CHOICES = [
        ('login',           'Inicio de sesión'),
        ('logout',          'Cierre de sesión'),
        ('create',          'Creación'),
        ('update',          'Modificación'),
        ('delete',          'Eliminación'),
        ('annul',           'Anulación'),
        ('access_denied',   'Acceso denegado'),
        ('revert',          'Reversión de cierre de caja'),
        ('recalculo_cierre', 'Recálculo automático de cierre de caja'),
        # 9.6: antes los intentos fallidos y el bloqueo temporal por fuerza
        # bruta (RF-03) solo quedaban en cache (efímero) — sin estos dos,
        # no había forma de investigar después un patrón de fuerza bruta
        # distribuido en el tiempo.
        ('login_failed',    'Intento fallido de inicio de sesión'),
        ('account_locked',  'Cuenta bloqueada temporalmente por intentos fallidos'),
    ]

    # Usuario que realizó la acción (null si no estaba autenticado)
    user = models.ForeignKey(
        User,
        on_delete=models.RESTRICT,
        null=True,
        blank=True
    )
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)

    # Qué tabla/módulo fue afectado (ej: 'Trip', 'Advance', 'Client')
    model_name = models.CharField(max_length=50)

    # ID del registro afectado
    object_id = models.IntegerField(null=True, blank=True)

    # Valores anteriores y nuevos en JSON (para modificaciones)
    previous_data = models.JSONField(null=True, blank=True)
    new_data = models.JSONField(null=True, blank=True)

    # IP del cliente
    ip_address = models.CharField(max_length=45, null=True, blank=True)

    # Justificación para cambios históricos (RF-37)
    justification = models.TextField(null=True, blank=True)

    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'AUDIT_LOG'
        # El log nunca se modifica ni elimina
        ordering = ['-timestamp']

    def __str__(self):
        return f'{self.timestamp} - {self.user} - {self.action} - {self.model_name}'