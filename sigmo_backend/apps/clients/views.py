from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from drf_spectacular.utils import extend_schema
from apps.audit.services import log_action
from typing import cast

from .models import Client
from .serializers import ClientSerializer

def can_manage_clients(user):
    # RF-07: Superusuario, Administrador Comercial y Contador pueden crear/editar
    return user.role in ['superuser', 'commercial_admin', 'accountant']


class ClientListCreateView(APIView):
    """
    GET  /api/clients/  → lista clientes con filtros opcionales (RF-10)
    POST /api/clients/  → crea un nuevo cliente (RF-07)
    """
    permission_classes = [IsAuthenticated]

    @extend_schema(summary="Listar clientes, con filtros opcionales.")
    def get(self, request):
        """Listar clientes, con filtros opcionales."""
        clients = Client.objects.all().order_by('name')

        # RF-10: filtros opcionales por nombre, NIT y estado
        name = request.query_params.get('name')
        nit = request.query_params.get('nit')
        state = request.query_params.get('state')

        if name:
            clients = clients.filter(name__icontains=name)
        if nit:
            clients = clients.filter(nit__icontains=nit)
        if state is not None:
            # RF-10: por defecto solo activos, pero se puede filtrar
            clients = clients.filter(state=state.lower() == 'true')
        else:
            # RF-10: por defecto solo muestra activos
            clients = clients.filter(state=True)

        serializer = ClientSerializer(clients, many=True)
        return Response(serializer.data)

    @extend_schema(summary="Registrar un nuevo cliente.")
    def post(self, request):
        """Registrar un nuevo cliente."""
        if not can_manage_clients(request.user):
            log_action(request, 'access_denied', 'Client')
            return Response(
                {'error': 'No tiene permisos para crear clientes.'},
                status=status.HTTP_403_FORBIDDEN
            )
        serializer = ClientSerializer(data=request.data)
        if serializer.is_valid():
            # RF-07: el usuario que crea el cliente es el autenticado
            client = cast(Client, serializer.save(user=request.user))
            log_action(
                request, 'create', 'Client',
                object_id=client.id,
                new_data=serializer.data,  # type: ignore
            )
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ClientDetailView(APIView):
    """
    GET   /api/clients/<id>/  → detalle de un cliente (RF-10)
    PATCH /api/clients/<id>/  → editar cliente (RF-09)
    """
    permission_classes = [IsAuthenticated]

    def get_object(self, pk):
        try:
            return Client.objects.get(pk=pk)
        except Client.DoesNotExist:
            return None

    @extend_schema(summary="Consultar el detalle de un cliente.")
    def get(self, request, pk):
        """Consultar el detalle de un cliente."""
        obj = self.get_object(pk)
        if not obj:
            return Response(
                {'error': 'Cliente no encontrado.'},
                status=status.HTTP_404_NOT_FOUND
            )
        return Response(ClientSerializer(obj).data)

    @extend_schema(summary="Editar los datos de un cliente.")
    def patch(self, request, pk):
        """Editar los datos de un cliente."""
        if not can_manage_clients(request.user):
            log_action(request, 'access_denied', 'Client', object_id=pk)
            return Response(
                {'error': 'No tiene permisos para editar clientes.'},
                status=status.HTTP_403_FORBIDDEN
            )
        obj = self.get_object(pk)
        if not obj:
            return Response(
                {'error': 'Cliente no encontrado.'},
                status=status.HTTP_404_NOT_FOUND
            )

        # Capturar datos anteriores ANTES de modificar
        previous = dict(ClientSerializer(obj).data)  # type: ignore

        data = request.data.copy()
        data.pop('nit', None)

        serializer = ClientSerializer(obj, data=data, partial=True)
        if serializer.is_valid():
            serializer.save()
            log_action(
                request, 'update', 'Client',
                object_id=obj.id,
                previous_data=previous,
                new_data=dict(serializer.data),  # type: ignore
            )
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)