from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from .models import Advance, AdvanceMovement
from .serializers import AdvanceSerializer, AdvanceMovementSerializer


def can_manage_advances(user):
    # RF-29: Superusuario, Contador y Administrador Comercial
    return user.role in ['superuser', 'accountant', 'commercial_admin']


class AdvanceListCreateView(APIView):
    """
    GET  /api/advances/          → lista anticipos con filtro por cliente
    POST /api/advances/          → registra un anticipo (RF-29)
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        advances = Advance.objects.select_related('client', 'user').all().order_by('-date')

        # Filtro por cliente
        client_id = request.query_params.get('client')
        if client_id:
            advances = advances.filter(client_id=client_id)

        serializer = AdvanceSerializer(advances, many=True)
        return Response(serializer.data)

    def post(self, request):
        if not can_manage_advances(request.user):
            return Response(
                {'error': 'No tiene permisos para registrar anticipos.'},
                status=status.HTTP_403_FORBIDDEN
            )
        serializer = AdvanceSerializer(data=request.data)
        if serializer.is_valid():
            advance: Advance = serializer.save(user=request.user)  # type: ignore

            AdvanceMovement.objects.create(
                advance=advance,
                type_movement='ingreso',
                amount=advance.value,
                trips_quantity=0,
                date=advance.date,
                description=f'Anticipo registrado. Ref: {advance.transfer_num}',
            )
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class AdvanceDetailView(APIView):
    """
    GET   /api/advances/<id>/  → detalle con historial de movimientos (RF-32)
    PATCH /api/advances/<id>/  → editar anticipo (solo Superusuario, RF-32B)
    """
    permission_classes = [IsAuthenticated]

    def get_object(self, pk):
        try:
            return Advance.objects.get(pk=pk)
        except Advance.DoesNotExist:
            return None

    def get(self, request, pk):
        obj = self.get_object(pk)
        if not obj:
            return Response(
                {'error': 'Anticipo no encontrado.'},
                status=status.HTTP_404_NOT_FOUND
            )
        return Response(AdvanceSerializer(obj).data)

    def patch(self, request, pk):
        # RF-32B: solo el Superusuario puede modificar anticipos
        if request.user.role != 'superuser':
            return Response(
                {'error': 'Solo el Superusuario puede modificar anticipos.'},
                status=status.HTTP_403_FORBIDDEN
            )
        obj = self.get_object(pk)
        if not obj:
            return Response(
                {'error': 'Anticipo no encontrado.'},
                status=status.HTTP_404_NOT_FOUND
            )
        serializer = AdvanceSerializer(obj, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class AdvanceBalanceView(APIView):
    """
    GET /api/advances/balance/<client_id>/
    Saldo disponible de anticipos de un cliente (RF-30)
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, client_id):
        advances = Advance.objects.filter(client_id=client_id)
        if not advances.exists():
            return Response({'client_id': client_id, 'balance': 0})

        # Calcular saldo total sumando available_balance de cada anticipo
        total_balance: float = 0
        for adv in advances:
            data: dict = dict(AdvanceSerializer(adv).data)  # type: ignore
            total_balance += float(data.get('available_balance', 0))
            
        return Response({
            'client_id': client_id,
            'balance': total_balance,
        })