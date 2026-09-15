from django.db import IntegrityError, transaction
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from drf_spectacular.utils import extend_schema
from apps.audit.services import log_action
from apps.trips.models import Trip
from typing import cast

from .models import Certificate
from .serializers import CertificateSerializer


def can_manage_certificates(user):
    return user.role in ['superuser', 'certifier']


class CertificateListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(summary="Listar certificados registrados.")
    def get(self, request):
        """Listar certificados registrados."""
        certificates = Certificate.objects.all().order_by('-id')
        serializer = CertificateSerializer(certificates, many=True)
        return Response(serializer.data)

    @extend_schema(summary="Crear un certificado o asociarle viajes a uno existente.")
    def post(self, request):
        """Crear un certificado o asociarle viajes a uno existente."""
        if not can_manage_certificates(request.user):
            log_action(request, 'access_denied', 'Certificate')
            return Response(
                {'error': 'No tiene permisos para registrar certificados.'},
                status=status.HTTP_403_FORBIDDEN
            )

        # Mismo patrón que InvoiceListCreateView.post (ver 8B.6 en
        # apps/invoices/views.py): `trip_ids` (opcional) asocia viajes al
        # certificado nuevo o existente (`certificate_id`) dentro de la misma
        # transacción atómica, evitando que un certificado quede con solo un
        # subconjunto de viajes asociados si algo falla a mitad de camino.
        trip_ids = request.data.get('trip_ids') or []
        existing_certificate_id = request.data.get('certificate_id')

        with transaction.atomic():
            locked_by_id = {}
            if trip_ids:
                # select_for_update() bloquea las filas de los viajes
                # seleccionados ANTES de crear/tocar nada, igual que en
                # InvoiceListCreateView.post.
                locked_trips = list(Trip.objects.select_for_update().filter(id__in=trip_ids))
                locked_by_id = {t.id: t for t in locked_trips}

                missing = set(trip_ids) - set(locked_by_id)
                if missing:
                    return Response({
                        'error': f'Viaje(s) no encontrado(s): {sorted(missing)}'
                    }, status=status.HTTP_400_BAD_REQUEST)

                # Un viaje solo puede tener un certificado asociado. Se
                # permite re-enviar un viaje que YA está en el certificado
                # que se está reutilizando (existing_certificate_id).
                conflicting = sorted(
                    trip_id for trip_id, trip in locked_by_id.items()
                    if trip.certificate_id is not None and trip.certificate_id != existing_certificate_id
                )
                if conflicting:
                    return Response({
                        'error': 'Uno o más viajes ya tienen otro certificado asociado.',
                        'trip_ids': conflicting,
                    }, status=status.HTTP_400_BAD_REQUEST)

            if existing_certificate_id is not None:
                try:
                    certificate = Certificate.objects.get(pk=existing_certificate_id)
                except Certificate.DoesNotExist:
                    return Response(
                        {'error': 'Certificado no encontrado.'},
                        status=status.HTTP_404_NOT_FOUND
                    )
                created = False
            else:
                serializer = CertificateSerializer(data=request.data)
                if not serializer.is_valid():
                    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
                # El UniqueValidator del serializer ya cubre el caso normal;
                # este try/except es la red de seguridad para la carrera
                # entre dos requests concurrentes, igual que en invoices.
                try:
                    certificate = cast(Certificate, serializer.save(user=request.user))
                except IntegrityError:
                    return Response(
                        {'error': 'Ya existe un certificado con este número.'},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                created = True
                log_action(
                    request, 'create', 'Certificate',
                    object_id=certificate.id,
                    new_data=dict(CertificateSerializer(certificate).data),
                )

            if trip_ids:
                for idx, trip_id in enumerate(trip_ids, start=1):
                    trip = locked_by_id[trip_id]
                    trip.certificate = certificate
                    trip.certificate_pos = idx
                    trip.save(update_fields=['certificate', 'certificate_pos'])
                log_action(
                    request, 'update', 'Certificate',
                    object_id=certificate.id,
                    new_data={'trips_assigned': trip_ids},
                )

        response_data = dict(CertificateSerializer(certificate).data)  # type: ignore
        response_data['trip_ids_assigned'] = trip_ids
        return Response(
            response_data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class CertificateDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get_object(self, pk):
        try:
            return Certificate.objects.get(pk=pk)
        except Certificate.DoesNotExist:
            return None

    @extend_schema(summary="Consultar el detalle de un certificado.")
    def get(self, request, pk):
        """Consultar el detalle de un certificado."""
        obj = self.get_object(pk)
        if not obj:
            return Response(
                {'error': 'Certificado no encontrado.'},
                status=status.HTTP_404_NOT_FOUND
            )
        return Response(CertificateSerializer(obj).data)
