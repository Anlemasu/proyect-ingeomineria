from django.db import IntegrityError, transaction
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from apps.audit.services import log_action
from apps.trips.models import Trip
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

        # 8B.6: `trip_ids` (opcional) — lista ordenada de viajes a asociar a
        # esta factura, ya sea nueva (`number`) o existente (`invoice_id`,
        # para agregarle más viajes a una factura ya creada). Antes esto no
        # vivía en el backend en absoluto: el frontend hacía un POST
        # /invoices/ y luego N PATCH /trips/<id>/ en paralelo, sin ninguna
        # transacción en común — si uno de los PATCH fallaba a mitad de
        # camino, quedaba una factura con solo un subconjunto de viajes
        # asociados, sin ningún rollback posible entre requests separados.
        trip_ids = request.data.get('trip_ids') or []
        existing_invoice_id = request.data.get('invoice_id')

        with transaction.atomic():
            locked_by_id = {}
            if trip_ids:
                # select_for_update() bloquea las filas de los viajes
                # seleccionados ANTES de crear/tocar nada — así, si otra
                # request concurrente está facturando alguno de estos
                # mismos viajes, una de las dos espera a que la otra
                # termine (y su re-lectura después del lock ya reflejará
                # el resultado), en vez de que ambas lean "libre" y una
                # pise a la otra.
                locked_trips = list(Trip.objects.select_for_update().filter(id__in=trip_ids))
                locked_by_id = {t.id: t for t in locked_trips}

                missing = set(trip_ids) - set(locked_by_id)
                if missing:
                    return Response({
                        'error': f'Viaje(s) no encontrado(s): {sorted(missing)}'
                    }, status=status.HTTP_400_BAD_REQUEST)

                # Un viaje solo puede tener una factura asociada. Se permite
                # re-enviar un viaje que YA está en la factura que se está
                # reutilizando (existing_invoice_id) — eso es agregarle más
                # viajes a la misma factura, no un conflicto.
                conflicting = sorted(
                    trip_id for trip_id, trip in locked_by_id.items()
                    if trip.invoice_id is not None and trip.invoice_id != existing_invoice_id
                )
                if conflicting:
                    return Response({
                        'error': 'Uno o más viajes ya tienen otra factura asociada.',
                        'trip_ids': conflicting,
                    }, status=status.HTTP_400_BAD_REQUEST)

            if existing_invoice_id is not None:
                try:
                    invoice = Invoice.objects.get(pk=existing_invoice_id)
                except Invoice.DoesNotExist:
                    return Response(
                        {'error': 'Factura no encontrada.'},
                        status=status.HTTP_404_NOT_FOUND
                    )
                created = False
            else:
                serializer = InvoiceSerializer(data=request.data)
                if not serializer.is_valid():
                    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
                # El UniqueValidator del serializer ya cubre el caso normal;
                # este try/except es la red de seguridad para la carrera
                # entre dos requests concurrentes que pasan esa validación
                # antes de que cualquiera de las dos llegue a hacer el INSERT.
                try:
                    invoice = cast(Invoice, serializer.save(user=request.user))
                except IntegrityError:
                    return Response(
                        {'error': 'Ya existe una factura con este número.'},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                created = True
                log_action(
                    request, 'create', 'Invoice',
                    object_id=invoice.id,
                    new_data=dict(InvoiceSerializer(invoice).data),
                )

            if trip_ids:
                for idx, trip_id in enumerate(trip_ids, start=1):
                    trip = locked_by_id[trip_id]
                    trip.invoice = invoice
                    trip.invoice_pos = idx
                    trip.save(update_fields=['invoice', 'invoice_pos'])
                log_action(
                    request, 'update', 'Invoice',
                    object_id=invoice.id,
                    new_data={'trips_assigned': trip_ids},
                )

        response_data = dict(InvoiceSerializer(invoice).data)  # type: ignore
        response_data['trip_ids_assigned'] = trip_ids
        return Response(
            response_data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


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