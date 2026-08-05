from rest_framework import serializers
from rest_framework.validators import UniqueValidator
from .models import Invoice

class InvoiceSerializer(serializers.ModelSerializer):
    # UniqueValidator explícito para dar un mensaje claro en vez del genérico
    # que arma DRF solo con unique=True ("invoice with this number already
    # exists."). Esta validación cubre el caso normal; el IntegrityError se
    # captura además en la vista como red de seguridad para la carrera entre
    # dos requests concurrentes que pasan esta validación antes de que
    # cualquiera de las dos haga el INSERT.
    number = serializers.CharField(
        max_length=15,
        validators=[UniqueValidator(
            queryset=Invoice.objects.all(),
            message='Ya existe una factura con este número.',
        )],
    )

    class Meta:
        model = Invoice
        fields = ['id', 'user', 'number']
        read_only_fields = ['id', 'user']