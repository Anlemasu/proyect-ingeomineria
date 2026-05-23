from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from .models import VehicleType, MaterialType, PaymentMethod, OriginSite, Tariff, PinsDumper, Vehicle
from .serializers import (
    VehicleTypeSerializer, MaterialTypeSerializer, PaymentMethodSerializer,
    OriginSiteSerializer, TariffSerializer, PinsDumperSerializer, VehicleSerializer
)


# ── Utilidades de permisos ────────────────────────────────────────────────────
def is_superuser(user):
    return user.role == 'superuser'

def is_commercial_admin(user):
    return user.role == 'commercial_admin'

def can_manage_masters(user):
    # Solo superusuario y administrador comercial pueden crear/editar maestros
    return is_superuser(user) or is_commercial_admin(user)


# ── VehicleType (RF-14, RF-15, RF-16) ────────────────────────────────────────
class VehicleTypeListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        # Todos los roles pueden consultar (R en la matriz de roles)
        vehicle_types = VehicleType.objects.all().order_by('name')
        serializer = VehicleTypeSerializer(vehicle_types, many=True)
        return Response(serializer.data)

    def post(self, request):
        if not can_manage_masters(request.user):
            return Response(
                {'error': 'No tiene permisos para crear tipos de vehículo.'},
                status=status.HTTP_403_FORBIDDEN
            )
        serializer = VehicleTypeSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class VehicleTypeDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get_object(self, pk):
        try:
            return VehicleType.objects.get(pk=pk)
        except VehicleType.DoesNotExist:
            return None

    def get(self, request, pk):
        obj = self.get_object(pk)
        if not obj:
            return Response({'error': 'No encontrado.'}, status=status.HTTP_404_NOT_FOUND)
        return Response(VehicleTypeSerializer(obj).data)

    def patch(self, request, pk):
        if not can_manage_masters(request.user):
            return Response(
                {'error': 'No tiene permisos para editar tipos de vehículo.'},
                status=status.HTTP_403_FORBIDDEN
            )
        obj = self.get_object(pk)
        if not obj:
            return Response({'error': 'No encontrado.'}, status=status.HTTP_404_NOT_FOUND)

        serializer = VehicleTypeSerializer(obj, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# ── MaterialType (RF-11, RF-12, RF-13) ───────────────────────────────────────
class MaterialTypeListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        materials = MaterialType.objects.all().order_by('name')
        serializer = MaterialTypeSerializer(materials, many=True)
        return Response(serializer.data)

    def post(self, request):
        if not can_manage_masters(request.user):
            return Response(
                {'error': 'No tiene permisos para crear tipos de material.'},
                status=status.HTTP_403_FORBIDDEN
            )
        serializer = MaterialTypeSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class MaterialTypeDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get_object(self, pk):
        try:
            return MaterialType.objects.get(pk=pk)
        except MaterialType.DoesNotExist:
            return None

    def get(self, request, pk):
        obj = self.get_object(pk)
        if not obj:
            return Response({'error': 'No encontrado.'}, status=status.HTTP_404_NOT_FOUND)
        return Response(MaterialTypeSerializer(obj).data)

    def patch(self, request, pk):
        if not can_manage_masters(request.user):
            return Response(
                {'error': 'No tiene permisos para editar tipos de material.'},
                status=status.HTTP_403_FORBIDDEN
            )
        obj = self.get_object(pk)
        if not obj:
            return Response({'error': 'No encontrado.'}, status=status.HTTP_404_NOT_FOUND)

        serializer = MaterialTypeSerializer(obj, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# ── PaymentMethod (RF-17, RF-18) ──────────────────────────────────────────────
class PaymentMethodListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        payments = PaymentMethod.objects.all().order_by('name')
        serializer = PaymentMethodSerializer(payments, many=True)
        return Response(serializer.data)

    def post(self, request):
        if not can_manage_masters(request.user):
            return Response(
                {'error': 'No tiene permisos para crear medios de pago.'},
                status=status.HTTP_403_FORBIDDEN
            )
        serializer = PaymentMethodSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class PaymentMethodDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get_object(self, pk):
        try:
            return PaymentMethod.objects.get(pk=pk)
        except PaymentMethod.DoesNotExist:
            return None

    def get(self, request, pk):
        obj = self.get_object(pk)
        if not obj:
            return Response({'error': 'No encontrado.'}, status=status.HTTP_404_NOT_FOUND)
        return Response(PaymentMethodSerializer(obj).data)

    def patch(self, request, pk):
        if not can_manage_masters(request.user):
            return Response(
                {'error': 'No tiene permisos para editar medios de pago.'},
                status=status.HTTP_403_FORBIDDEN
            )
        obj = self.get_object(pk)
        if not obj:
            return Response({'error': 'No encontrado.'}, status=status.HTTP_404_NOT_FOUND)

        serializer = PaymentMethodSerializer(obj, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# ── OriginSite (RF-25) ────────────────────────────────────────────────────────
class OriginSiteListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        origins = OriginSite.objects.all().order_by('name')
        serializer = OriginSiteSerializer(origins, many=True)
        return Response(serializer.data)

    def post(self, request):
        if not can_manage_masters(request.user):
            return Response(
                {'error': 'No tiene permisos para crear orígenes.'},
                status=status.HTTP_403_FORBIDDEN
            )
        serializer = OriginSiteSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class OriginSiteDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get_object(self, pk):
        try:
            return OriginSite.objects.get(pk=pk)
        except OriginSite.DoesNotExist:
            return None

    def get(self, request, pk):
        obj = self.get_object(pk)
        if not obj:
            return Response({'error': 'No encontrado.'}, status=status.HTTP_404_NOT_FOUND)
        return Response(OriginSiteSerializer(obj).data)

    def patch(self, request, pk):
        if not can_manage_masters(request.user):
            return Response(
                {'error': 'No tiene permisos para editar orígenes.'},
                status=status.HTTP_403_FORBIDDEN
            )
        obj = self.get_object(pk)
        if not obj:
            return Response({'error': 'No encontrado.'}, status=status.HTTP_404_NOT_FOUND)

        serializer = OriginSiteSerializer(obj, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# ── Tariff (RF-19, RF-20, RF-21) ─────────────────────────────────────────────
class TariffListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        # Filtro opcional por cliente: /api/masters/tariffs/?client=1
        client_id = request.query_params.get('client')
        tariffs = Tariff.objects.all().order_by('client', 'vehicle_type')
        if client_id:
            tariffs = tariffs.filter(client_id=client_id)
        serializer = TariffSerializer(tariffs, many=True)
        return Response(serializer.data)

    def post(self, request):
        if not can_manage_masters(request.user):
            return Response(
                {'error': 'No tiene permisos para crear tarifas.'},
                status=status.HTTP_403_FORBIDDEN
            )
        serializer = TariffSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class TariffDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get_object(self, pk):
        try:
            return Tariff.objects.get(pk=pk)
        except Tariff.DoesNotExist:
            return None

    def get(self, request, pk):
        obj = self.get_object(pk)
        if not obj:
            return Response({'error': 'No encontrado.'}, status=status.HTTP_404_NOT_FOUND)
        return Response(TariffSerializer(obj).data)

    def patch(self, request, pk):
        if not can_manage_masters(request.user):
            return Response(
                {'error': 'No tiene permisos para editar tarifas.'},
                status=status.HTTP_403_FORBIDDEN
            )
        obj = self.get_object(pk)
        if not obj:
            return Response({'error': 'No encontrado.'}, status=status.HTTP_404_NOT_FOUND)

        # RF-21: al modificar una tarifa, cerrar la vigencia de la anterior
        if obj.state:
            from django.utils import timezone
            obj.end_date = timezone.now().date()
            obj.state = False
            obj.save()

            request_data: dict = dict(request.data)  # type: ignore
            old_data: dict = dict(TariffSerializer(obj).data)  # type: ignore

            new_data: dict = {**old_data, **request_data}
            new_data.pop('id', None)
            new_data.pop('end_date', None)
            new_data['state'] = True

            serializer = TariffSerializer(data=new_data)
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data, status=status.HTTP_201_CREATED)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# ── PinsDumper (RF-22) ────────────────────────────────────────────────────────
class PinsDumperListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        # Filtro opcional por placa: /api/masters/pins/?plaque=ABC123
        plaque = request.query_params.get('plaque')
        pins = PinsDumper.objects.all().order_by('plaque')
        if plaque:
            pins = pins.filter(plaque__icontains=plaque)
        serializer = PinsDumperSerializer(pins, many=True)
        return Response(serializer.data)

    def post(self, request):
        if not can_manage_masters(request.user):
            return Response(
                {'error': 'No tiene permisos para registrar pines.'},
                status=status.HTTP_403_FORBIDDEN
            )
        serializer = PinsDumperSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# ── Vehicle ───────────────────────────────────────────────────────────────────
class VehicleListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        # Filtro por placa: /api/masters/vehicles/?plaque=ABC
        plaque = request.query_params.get('plaque')
        vehicles = Vehicle.objects.select_related('vehicle_type', 'dumper').all()
        if plaque:
            vehicles = vehicles.filter(plaque__icontains=plaque)
        serializer = VehicleSerializer(vehicles, many=True)
        return Response(serializer.data)

    def post(self, request):
        if not can_manage_masters(request.user):
            return Response(
                {'error': 'No tiene permisos para registrar vehículos.'},
                status=status.HTTP_403_FORBIDDEN
            )
        serializer = VehicleSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)