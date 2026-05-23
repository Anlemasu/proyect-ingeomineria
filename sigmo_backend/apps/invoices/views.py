from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from .models import Invoice
from .serializers import InvoiceSerializer


def can_manage_invoices(user):
    # RF-39: Superusuario y Contador
    return user.role in ['superuser', 'accountant']


class InvoiceListCreateView(APIView):
    """
    GET  /api/invoices/  → lista facturas
    POST /api/invoices/  → registra número de factura electrónica (RF-39)
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        invoices = Invoice.objects.all().order_by('-id')
        serializer = InvoiceSerializer(invoices, many=True)
        return Response(serializer.data)

    def post(self, request):
        if not can_manage_invoices(request.user):
            return Response(
                {'error': 'No tiene permisos para registrar facturas.'},
                status=status.HTTP_403_FORBIDDEN
            )
        serializer = InvoiceSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(user=request.user)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class InvoiceDetailView(APIView):
    """
    GET /api/invoices/<id>/  → detalle de factura
    """
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