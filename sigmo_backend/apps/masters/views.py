from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from apps.audit.services import log_action
from typing import cast
from django.db import transaction
from django.utils import timezone

from .models import VehicleType, MaterialType, PaymentMethod, OriginSite, City, Tariff, PinsDumper, Vehicle
from .serializers import (
    VehicleTypeSerializer, MaterialTypeSerializer, PaymentMethodSerializer,
    OriginSiteSerializer, CitySerializer, TariffSerializer, PinsDumperSerializer, VehicleSerializer
)


def is_superuser(user):
    return user.role == 'superuser'

def is_commercial_admin(user):
    return user.role == 'commercial_admin'

def can_manage_masters(user):
    return is_superuser(user) or is_commercial_admin(user)


# ── VehicleType ───────────────────────────────────────────────────────────────
class VehicleTypeListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        vehicle_types = VehicleType.objects.all().order_by('name')
        serializer = VehicleTypeSerializer(vehicle_types, many=True)
        return Response(serializer.data)

    def post(self, request):
        if not can_manage_masters(request.user):
            log_action(request, 'access_denied', 'VehicleType')
            return Response(
                {'error': 'No tiene permisos para crear tipos de vehículo.'},
                status=status.HTTP_403_FORBIDDEN
            )
        serializer = VehicleTypeSerializer(data=request.data)
        if serializer.is_valid():
            obj = cast(VehicleType, serializer.save())
            log_action(
                request, 'create', 'VehicleType',
                object_id=obj.id,
                new_data=dict(serializer.data),  # type: ignore
            )
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
            log_action(request, 'access_denied', 'VehicleType', object_id=pk)
            return Response(
                {'error': 'No tiene permisos para editar tipos de vehículo.'},
                status=status.HTTP_403_FORBIDDEN
            )
        obj = self.get_object(pk)
        if not obj:
            return Response({'error': 'No encontrado.'}, status=status.HTTP_404_NOT_FOUND)

        previous = dict(VehicleTypeSerializer(obj).data)  # type: ignore
        serializer = VehicleTypeSerializer(obj, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            log_action(
                request, 'update', 'VehicleType',
                object_id=obj.id,
                previous_data=previous,
                new_data=dict(serializer.data),  # type: ignore
            )
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# ── MaterialType ──────────────────────────────────────────────────────────────
class MaterialTypeListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        materials = MaterialType.objects.all().order_by('name')
        serializer = MaterialTypeSerializer(materials, many=True)
        return Response(serializer.data)

    def post(self, request):
        if not can_manage_masters(request.user):
            log_action(request, 'access_denied', 'MaterialType')
            return Response(
                {'error': 'No tiene permisos para crear tipos de material.'},
                status=status.HTTP_403_FORBIDDEN
            )
        serializer = MaterialTypeSerializer(data=request.data)
        if serializer.is_valid():
            obj = cast(MaterialType, serializer.save())
            log_action(
                request, 'create', 'MaterialType',
                object_id=obj.id,
                new_data=dict(serializer.data),  # type: ignore
            )
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
            log_action(request, 'access_denied', 'MaterialType', object_id=pk)
            return Response(
                {'error': 'No tiene permisos para editar tipos de material.'},
                status=status.HTTP_403_FORBIDDEN
            )
        obj = self.get_object(pk)
        if not obj:
            return Response({'error': 'No encontrado.'}, status=status.HTTP_404_NOT_FOUND)

        previous = dict(MaterialTypeSerializer(obj).data)  # type: ignore
        serializer = MaterialTypeSerializer(obj, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            log_action(
                request, 'update', 'MaterialType',
                object_id=obj.id,
                previous_data=previous,
                new_data=dict(serializer.data),  # type: ignore
            )
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# ── PaymentMethod ─────────────────────────────────────────────────────────────
class PaymentMethodListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        payments = PaymentMethod.objects.all().order_by('name')
        serializer = PaymentMethodSerializer(payments, many=True)
        return Response(serializer.data)

    def post(self, request):
        if not can_manage_masters(request.user):
            log_action(request, 'access_denied', 'PaymentMethod')
            return Response(
                {'error': 'No tiene permisos para crear medios de pago.'},
                status=status.HTTP_403_FORBIDDEN
            )
        serializer = PaymentMethodSerializer(data=request.data)
        if serializer.is_valid():
            obj = cast(PaymentMethod, serializer.save())
            log_action(
                request, 'create', 'PaymentMethod',
                object_id=obj.id,
                new_data=dict(serializer.data),  # type: ignore
            )
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
            log_action(request, 'access_denied', 'PaymentMethod', object_id=pk)
            return Response(
                {'error': 'No tiene permisos para editar medios de pago.'},
                status=status.HTTP_403_FORBIDDEN
            )
        obj = self.get_object(pk)
        if not obj:
            return Response({'error': 'No encontrado.'}, status=status.HTTP_404_NOT_FOUND)

        previous = dict(PaymentMethodSerializer(obj).data)  # type: ignore
        serializer = PaymentMethodSerializer(obj, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            log_action(
                request, 'update', 'PaymentMethod',
                object_id=obj.id,
                previous_data=previous,
                new_data=dict(serializer.data),  # type: ignore
            )
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# ── OriginSite ────────────────────────────────────────────────────────────────
class OriginSiteListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        origins = OriginSite.objects.all().order_by('name')
        serializer = OriginSiteSerializer(origins, many=True)
        return Response(serializer.data)

    def post(self, request):
        if not can_manage_masters(request.user):
            log_action(request, 'access_denied', 'OriginSite')
            return Response(
                {'error': 'No tiene permisos para crear orígenes.'},
                status=status.HTTP_403_FORBIDDEN
            )
        serializer = OriginSiteSerializer(data=request.data)
        if serializer.is_valid():
            obj = cast(OriginSite, serializer.save())
            log_action(
                request, 'create', 'OriginSite',
                object_id=obj.id,
                new_data=dict(serializer.data),  # type: ignore
            )
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
            log_action(request, 'access_denied', 'OriginSite', object_id=pk)
            return Response(
                {'error': 'No tiene permisos para editar orígenes.'},
                status=status.HTTP_403_FORBIDDEN
            )
        obj = self.get_object(pk)
        if not obj:
            return Response({'error': 'No encontrado.'}, status=status.HTTP_404_NOT_FOUND)

        previous = dict(OriginSiteSerializer(obj).data)  # type: ignore
        serializer = OriginSiteSerializer(obj, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            log_action(
                request, 'update', 'OriginSite',
                object_id=obj.id,
                previous_data=previous,
                new_data=dict(serializer.data),  # type: ignore
            )
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# ── City ──────────────────────────────────────────────────────────────────────
class CityListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        cities = City.objects.all().order_by('name')
        serializer = CitySerializer(cities, many=True)
        return Response(serializer.data)

    def post(self, request):
        if not can_manage_masters(request.user):
            log_action(request, 'access_denied', 'City')
            return Response(
                {'error': 'No tiene permisos para crear ciudades.'},
                status=status.HTTP_403_FORBIDDEN
            )
        serializer = CitySerializer(data=request.data)
        if serializer.is_valid():
            obj = cast(City, serializer.save())
            log_action(
                request, 'create', 'City',
                object_id=obj.id,
                new_data=dict(serializer.data),  # type: ignore
            )
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class CityDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get_object(self, pk):
        try:
            return City.objects.get(pk=pk)
        except City.DoesNotExist:
            return None

    def get(self, request, pk):
        obj = self.get_object(pk)
        if not obj:
            return Response({'error': 'No encontrado.'}, status=status.HTTP_404_NOT_FOUND)
        return Response(CitySerializer(obj).data)

    def patch(self, request, pk):
        if not can_manage_masters(request.user):
            log_action(request, 'access_denied', 'City', object_id=pk)
            return Response(
                {'error': 'No tiene permisos para editar ciudades.'},
                status=status.HTTP_403_FORBIDDEN
            )
        obj = self.get_object(pk)
        if not obj:
            return Response({'error': 'No encontrado.'}, status=status.HTTP_404_NOT_FOUND)

        previous = dict(CitySerializer(obj).data)  # type: ignore
        serializer = CitySerializer(obj, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            log_action(
                request, 'update', 'City',
                object_id=obj.id,
                previous_data=previous,
                new_data=dict(serializer.data),  # type: ignore
            )
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# ── Tariff ────────────────────────────────────────────────────────────────────
class TariffListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        client_id      = request.query_params.get('client')
        vehicle_type   = request.query_params.get('vehicle_type')
        state          = request.query_params.get('state')
        tariffs = Tariff.objects.all().order_by('client', 'vehicle_type')
        if client_id:
            tariffs = tariffs.filter(client_id=client_id)
        if vehicle_type:
            tariffs = tariffs.filter(vehicle_type_id=vehicle_type)
        if state is not None:
            tariffs = tariffs.filter(state=state.lower() == 'true')
        serializer = TariffSerializer(tariffs, many=True)
        return Response(serializer.data)

    def post(self, request):
        if not can_manage_masters(request.user):
            log_action(request, 'access_denied', 'Tariff')
            return Response(
                {'error': 'No tiene permisos para crear tarifas.'},
                status=status.HTTP_403_FORBIDDEN
            )
        serializer = TariffSerializer(data=request.data)
        if serializer.is_valid():
            obj = cast(Tariff, serializer.save())
            log_action(
                request, 'create', 'Tariff',
                object_id=obj.id,
                new_data=dict(serializer.data),  # type: ignore
            )
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
            log_action(request, 'access_denied', 'Tariff', object_id=pk)
            return Response(
                {'error': 'No tiene permisos para editar tarifas.'},
                status=status.HTTP_403_FORBIDDEN
            )
        obj = self.get_object(pk)
        if not obj:
            return Response({'error': 'No encontrado.'}, status=status.HTTP_404_NOT_FOUND)

        # Bug 2: si la tarifa ya está inactiva no hay nada que modificar
        if not obj.state:
            return Response(
                {'error': 'Esta tarifa ya está inactiva.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Bug 6: atomic() garantiza que si falla la creación de la nueva tarifa,
        # la antigua no queda cerrada sin reemplazo
        try:
            with transaction.atomic():
                previous = dict(TariffSerializer(obj).data)  # type: ignore

                # Cerrar tarifa anterior (RF-21)
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
                if not serializer.is_valid():
                    # Al lanzar excepción, el atomic revierte el obj.save() de arriba
                    raise ValueError(str(serializer.errors))

                new_obj = cast(Tariff, serializer.save())

                log_action(
                    request, 'update', 'Tariff',
                    object_id=obj.id,
                    previous_data=previous,
                    new_data={'closed': True, 'new_tariff_id': new_obj.id},
                )
                log_action(
                    request, 'create', 'Tariff',
                    object_id=new_obj.id,
                    new_data=dict(serializer.data),  # type: ignore
                )
                return Response(serializer.data, status=status.HTTP_201_CREATED)

        except ValueError as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception:
            return Response(
                {'error': 'Error al actualizar la tarifa. Intente nuevamente.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


# ── PinsDumper ────────────────────────────────────────────────────────────────
class PinsDumperListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        plaque = request.query_params.get('plaque')
        pins = PinsDumper.objects.all().order_by('plaque')
        if plaque:
            pins = pins.filter(plaque__icontains=plaque)
        serializer = PinsDumperSerializer(pins, many=True)
        return Response(serializer.data)

    def post(self, request):
        if not can_manage_masters(request.user):
            log_action(request, 'access_denied', 'PinsDumper')
            return Response(
                {'error': 'No tiene permisos para registrar pines.'},
                status=status.HTTP_403_FORBIDDEN
            )
        serializer = PinsDumperSerializer(data=request.data)
        if serializer.is_valid():
            obj = cast(PinsDumper, serializer.save())
            log_action(
                request, 'create', 'PinsDumper',
                object_id=obj.id,
                new_data=dict(serializer.data),  # type: ignore
            )
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# ── Vehicle ───────────────────────────────────────────────────────────────────
class VehicleListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        plaque = request.query_params.get('plaque')
        vehicles = Vehicle.objects.select_related('vehicle_type', 'dumper').all()
        if plaque:
            vehicles = vehicles.filter(plaque__icontains=plaque)
        serializer = VehicleSerializer(vehicles, many=True)
        return Response(serializer.data)

    def post(self, request):
        if not can_manage_masters(request.user):
            log_action(request, 'access_denied', 'Vehicle')
            return Response(
                {'error': 'No tiene permisos para registrar vehículos.'},
                status=status.HTTP_403_FORBIDDEN
            )
        serializer = VehicleSerializer(data=request.data)
        if serializer.is_valid():
            obj = cast(Vehicle, serializer.save())
            log_action(
                request, 'create', 'Vehicle',
                object_id=obj.id,
                new_data=dict(serializer.data),  # type: ignore
            )
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
class PinsDumperImportView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        if not can_manage_masters(request.user):
            log_action(request, 'access_denied', 'PinsDumper')
            return Response(
                {'error': 'No tiene permisos para importar pines.'},
                status=status.HTTP_403_FORBIDDEN
            )

        if 'file' not in request.FILES:
            return Response(
                {'error': 'Debe enviar un archivo .xlsx o .csv.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        file = request.FILES['file']

        if not file.name.endswith(('.xlsx', '.csv')):
            return Response(
                {'error': 'El archivo debe ser .xlsx o .csv.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        from .services import parse_pins_from_excel
        result = parse_pins_from_excel(file)

        if not result['success']:
            return Response(
                {'error': result.get('error', 'Error al procesar el archivo.')},
                status=status.HTTP_400_BAD_REQUEST
            )

        log_action(
            request, 'create', 'PinsDumper',
            new_data={
                'import_result': {
                    'created': result['created'],
                    'updated': result['updated'],
                    'rejected': result['rejected_count'],
                }
            }
        )

        return Response(result, status=status.HTTP_200_OK)