from django.db import IntegrityError
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from apps.audit.services import log_action
from typing import cast

from .models import Invoice
from .serializers import InvoiceSerializer


def can_manage_invoices(user):
    return user.role in ['superuser', 'accountant']


class InvoiceListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        invoices = Invoice.objects.all().order_by('-id')
        serializer = InvoiceSerializer(invoices, many=True)
        return Response(serializer.data)

    def post(self, request):
        if not can_manage_invoices(request.user):
            log_action(request, 'access_denied', 'Invoice')
            return Response(
                {'error': 'No tiene permisos para registrar facturas.'},
                status=status.HTTP_403_FORBIDDEN
            )
        serializer = InvoiceSerializer(data=request.data)
        if serializer.is_valid():
            # El UniqueValidator del serializer ya cubre el caso normal; este
            # try/except es la red de seguridad para la carrera entre dos
            # requests concurrentes que pasan esa validación antes de que
            # cualquiera de las dos llegue a hacer el INSERT.
            try:
                invoice = cast(Invoice, serializer.save(user=request.user))
            except IntegrityError:
                return Response(
                    {'error': 'Ya existe una factura con este número.'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            log_action(
                request, 'create', 'Invoice',
                object_id=invoice.id,
                new_data=dict(serializer.data),  # type: ignore
            )
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class InvoiceDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get_object(self, pk):
        try:
            return Invoice.objects.get(pk=pk)
        except Invoice.DoesNotExist:
            return None

    def get(self, request, pk):
        obj = self.get_object(pk)
        if not obj:
            return Response(
                {'error': 'Factura no encontrada.'},
                status=status.HTTP_404_NOT_FOUND
            )
        return Response(InvoiceSerializer(obj).data)