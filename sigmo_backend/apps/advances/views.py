from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from apps.audit.services import log_action

from .models import Advance, AdvanceMovement
from .serializers import AdvanceSerializer, AdvanceMovementSerializer


def can_manage_advances(user):
    return user.role in ['superuser', 'accountant', 'commercial_admin']


class AdvanceListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        advances = Advance.objects.select_related('client', 'user').all().order_by('-date')
        client_id = request.query_params.get('client')
        if client_id:
            advances = advances.filter(client_id=client_id)
        serializer = AdvanceSerializer(advances, many=True)
        return Response(serializer.data)

    def post(self, request):
        if not can_manage_advances(request.user):
            log_action(request, 'access_denied', 'Advance')
            return Response(
                {'error': 'No tiene permisos para registrar anticipos.'},
                status=status.HTTP_403_FORBIDDEN
            )
        serializer = AdvanceSerializer(data=request.data)
        if serializer.is_valid():
            advance: Advance = serializer.save(user=request.user)  # type: ignore

            try:
                trips_quantity = int(request.data.get('trips_quantity', 0))
                if trips_quantity < 0:
                    trips_quantity = 0
            except (TypeError, ValueError):
                trips_quantity = 0

            AdvanceMovement.objects.create(
                advance=advance,
                type_movement='ingreso',
                amount=advance.value,
                trips_quantity=trips_quantity,
                date=advance.date,
                description=f'Anticipo registrado. Ref: {advance.transfer_num}',
            )
            log_action(
                request, 'create', 'Advance',
                object_id=advance.id,
                new_data=dict(serializer.data),  # type: ignore
            )
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class AdvanceDetailView(APIView):
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
        if request.user.role != 'superuser':
            log_action(request, 'access_denied', 'Advance', object_id=pk)
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

        # Capturar datos anteriores antes de modificar (RF-32B)
        previous = dict(AdvanceSerializer(obj).data)  # type: ignore

        serializer = AdvanceSerializer(obj, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            log_action(
                request, 'update', 'Advance',
                object_id=obj.id,
                previous_data=previous,
                new_data=dict(serializer.data),  # type: ignore
            )
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class AdvanceBalanceView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, client_id):
        advances = Advance.objects.filter(client_id=client_id)
        if not advances.exists():
            return Response({'client_id': client_id, 'balance': 0})

        total_balance: float = 0
        for adv in advances:
            data: dict = dict(AdvanceSerializer(adv).data)  # type: ignore
            total_balance += float(data.get('available_balance', 0))

        return Response({
            'client_id': client_id,
            'balance': total_balance,
        })