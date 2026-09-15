from rest_framework import serializers
from rest_framework.validators import UniqueValidator
from .models import Certificate


class CertificateSerializer(serializers.ModelSerializer):
    # UniqueValidator explícito para dar un mensaje claro en vez del genérico
    # que arma DRF solo con unique=True. Mismo patrón que InvoiceSerializer.
    number = serializers.CharField(
        max_length=15,
        validators=[UniqueValidator(
            queryset=Certificate.objects.all(),
            message='Ya existe un certificado con este número.',
        )],
    )

    class Meta:
        model = Certificate
        fields = ['id', 'user', 'number']
        read_only_fields = ['id', 'user']
