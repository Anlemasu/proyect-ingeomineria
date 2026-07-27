from rest_framework import serializers
from .models import VehicleType, PinsDumper, Vehicle, MaterialType, PaymentMethod, OriginSite, City, Tariff


# ── VehicleType (RF-14, RF-15, RF-16) ────────────────────────────────────────
class VehicleTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = VehicleType
        fields = ['id', 'name', 'capacity', 'description', 'state']

    def validate_capacity(self, value):
        # RF-14: capacidad debe ser decimal positivo mayor a cero
        if value <= 0:
            raise serializers.ValidationError(
                'La capacidad debe ser un número mayor a cero.'
            )
        return value

    def validate_name(self, value):
        # Nombre único insensible a mayúsculas
        qs = VehicleType.objects.filter(name__iexact=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError(
                'Ya existe un tipo de vehículo con este nombre.'
            )
        return value

    def validate(self, data):
        # RF-16: no se puede desactivar si hay vehículos activos usándolo
        # Solo validamos en edición (self.instance existe)
        if self.instance and data.get('state') is False:
            if self.instance.vehicle_set.exists():
                raise serializers.ValidationError(
                    'No se puede desactivar: hay vehículos asociados a este tipo.'
                )
        return data


# ── PinsDumper (RF-22) ────────────────────────────────────────────────────────
class PinsDumperSerializer(serializers.ModelSerializer):
    class Meta:
        model = PinsDumper
        fields = [
            'id',
            'ambiental_pin',
            'propietary',
            'address',
            'phone',
            'email',
            'plaque',
            'expedition_site',
            'model',
            'capacity',
            'driver',
            'date_register',
            'state',
        ]

    def validate_capacity(self, value):
        if value <= 0:
            raise serializers.ValidationError(
                'La capacidad debe ser mayor a cero.'
            )
        return value

    def validate_plaque(self, value):
        # Placa siempre en mayúsculas para consistencia
        return value.upper()


# ── Vehicle ───────────────────────────────────────────────────────────────────
class VehicleSerializer(serializers.ModelSerializer):
    """
    Patrón lectura/escritura en un solo serializer:
    - vehicle_type_detail y dumper_detail: objetos completos para el GET
    - vehicle_type y dumper: IDs para el POST/PUT
    """
    vehicle_type_detail = VehicleTypeSerializer(
        source='vehicle_type', read_only=True
    )
    dumper_detail = PinsDumperSerializer(
        source='dumper', read_only=True
    )

    class Meta:
        model = Vehicle
        fields = [
            'id',
            'plaque',
            'vehicle_type',        # ID para escritura
            'vehicle_type_detail', # objeto para lectura
            'dumper',              # ID para escritura (nullable)
            'dumper_detail',       # objeto para lectura
        ]
        read_only_fields = ['id']

    def validate_plaque(self, value):
        return value.upper()

    def validate_vehicle_type(self, value):
        # RF-16: no permitir asignar un tipo de vehículo desactivado
        if not value.state:
            raise serializers.ValidationError(
                'El tipo de vehículo seleccionado está desactivado.'
            )
        return value


# ── MaterialType (RF-11, RF-12, RF-13) ───────────────────────────────────────
class MaterialTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = MaterialType
        fields = ['id', 'name', 'description', 'state']

    def validate_name(self, value):
        # RF-11: nombre único insensible a mayúsculas
        qs = MaterialType.objects.filter(name__iexact=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError(
                'Ya existe un tipo de material con este nombre.'
            )
        return value


# ── PaymentMethod (RF-17, RF-18) ──────────────────────────────────────────────
class PaymentMethodSerializer(serializers.ModelSerializer):
    class Meta:
        model = PaymentMethod
        fields = ['id', 'name', 'is_advance', 'state']

    def validate(self, data):
        # RF-18: debe existir al menos un medio de pago activo en todo momento
        if self.instance and data.get('state') is False:
            otros_activos = PaymentMethod.objects.filter(
                state=True
            ).exclude(pk=self.instance.pk)
            if not otros_activos.exists():
                raise serializers.ValidationError(
                    'Debe existir al menos un medio de pago activo.'
                )
        return data


# ── OriginSite (RF-25) ────────────────────────────────────────────────────────
class OriginSiteSerializer(serializers.ModelSerializer):
    class Meta:
        model = OriginSite
        fields = ['id', 'name', 'state']

    def validate_name(self, value):
        # Nombre único insensible a mayúsculas
        qs = OriginSite.objects.filter(name__iexact=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError(
                'Ya existe un origen con este nombre.'
            )
        return value


# ── City ──────────────────────────────────────────────────────────────────────
class CitySerializer(serializers.ModelSerializer):
    class Meta:
        model = City
        fields = ['id', 'name', 'state']

    def validate_name(self, value):
        # Nombre único insensible a mayúsculas
        qs = City.objects.filter(name__iexact=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError(
                'Ya existe una ciudad con este nombre.'
            )
        return value


# ── Tariff (RF-19, RF-20, RF-21) ─────────────────────────────────────────────
class TariffSerializer(serializers.ModelSerializer):
    # Campos de solo lectura para mostrar nombres en el GET
    client_name = serializers.CharField(
        source='client.name', read_only=True
    )
    vehicle_type_name = serializers.CharField(
        source='vehicle_type.name', read_only=True
    )
    material_type_name = serializers.CharField(
        source='material_type.name', read_only=True,
        default=None   # porque material_type es nullable
    )

    class Meta:
        model = Tariff
        fields = [
            'id',
            'client',              # ID (nullable = tarifa general RF-20)
            'client_name',
            'vehicle_type',        # ID obligatorio
            'vehicle_type_name',
            'material_type',       # ID (nullable)
            'material_type_name',
            'value',
            'start_date',
            'end_date',
            'state',
        ]
        read_only_fields = ['id', 'client_name', 'vehicle_type_name', 'material_type_name']

    def validate_value(self, value):
        # RF-19: el valor debe ser mayor a cero
        if value <= 0:
            raise serializers.ValidationError(
                'El valor de la tarifa debe ser mayor a cero.'
            )
        return value

    def validate(self, data):
        # Validar que end_date no sea anterior a start_date
        start = data.get('start_date')
        end = data.get('end_date')
        if start and end and end < start:
            raise serializers.ValidationError(
                'La fecha de fin no puede ser anterior a la fecha de inicio.'
            )
        return data