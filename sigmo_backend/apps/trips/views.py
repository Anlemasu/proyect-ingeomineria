from decimal import Decimal

from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from drf_spectacular.utils import extend_schema
from django.utils import timezone
from apps.audit.services import log_action
from typing import cast
from django.db import transaction

from .models import Trip
from .serializers import TripReadSerializer, TripWriteSerializer
from .services import (
    sync_advance_movement_on_trip_change,
    reallocate_advance_on_client_change,
    reverse_advance_discount,
    fund_trip_entering_advance_payment,
    InsufficientBalanceError,
    InsufficientBalanceForAdvanceFundingError,
    UnsupportedAdvanceChangeError,
)
from apps.advances.models import Advance, AdvanceMovement
from apps.advances.services import get_active_advance, get_available_balance
from apps.clients.models import Client
from apps.cash_closing.models import DailySummary
from apps.cash_closing.services import resync_if_closed
from apps.pending_entries.models import PendingEntry
from apps.pending_entries.services import (
    execute_pending_transfer,
    PendingEntryNotPendingError,
    PendingEntryTypeMismatchError,
    PendingEntryClientMismatchError,
    PendingEntryValueMismatchError,
)

# Campos cuyo cambio afecta los totales de un DailySummary ya cerrado
# (valor, anulación/reactivación o medio de pago). Un PATCH que solo toca
# 'invoice'/'invoice_pos' no necesita disparar un recálculo del cierre.
FIELDS_AFFECTING_TOTALS = {'value', 'state', 'payment'}

# 8B.4: campos que afectan el valor facturado — no pueden editarse en un
# viaje que ya tiene una factura asociada, para no desalinear lo facturado
# de lo que el sistema muestra como registro operativo. Editarlos exige
# desvincular la factura primero (ver can_unlink_invoice más abajo).
FINANCIAL_FIELDS_LOCKED_WHEN_INVOICED = {'value', 'client', 'payment'}


def can_register_trips(user):
    return user.role in ['superuser', 'cashier', 'commercial_admin']


def can_update_trips(user):
    return user.role in ['superuser', 'commercial_admin', 'cashier']


# 8B.4: desvincular una factura de un viaje es una operación distinta de
# editar el viaje — la puede hacer el superuser o contabilidad (quien
# gestiona la facturación, ver can_manage_invoices en apps/invoices), no
# los mismos roles que registran/editan viajes en el día a día.
def can_unlink_invoice(user):
    return user.role in ['superuser', 'accountant']


# Certificados de disposición final (apps/certificates) — mismo patrón que
# facturación arriba, con su propio rol ('certifier') en vez de 'accountant'.
# No tiene relación con Client.validate_certification (retenciones).
def can_unlink_certificate(user):
    return user.role in ['superuser', 'certifier']


# RF-36: estos dos roles están al mismo nivel en la matriz (CRU, no D) —
# solo pueden tocar viajes registrados el día en curso. Fuera de esa
# ventana, el ajuste es exclusivo de superuser (RF-37, más abajo, mismo
# endpoint). auditor/accountant ni siquiera llegan aquí: los bloquea
# can_update_trips.
SAME_DAY_ONLY_ROLES = {'cashier', 'commercial_admin'}


class TripListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(summary="Listar viajes registrados, con filtros opcionales.")
    def get(self, request):
        """Listar viajes registrados, con filtros opcionales."""
        trips = Trip.objects.select_related(
            'client', 'payment', 'vehicle', 'material_type', 'origin_site'
        ).all().order_by('-date_register')

        client_id  = request.query_params.get('client')
        date_from  = request.query_params.get('date_from')
        date_to    = request.query_params.get('date_to')
        date       = request.query_params.get('date')
        state      = request.query_params.get('state')
        invoice_id = request.query_params.get('invoice')
        advance_id = request.query_params.get('advance')

        if client_id:
            trips = trips.filter(client_id=client_id)
        if date:
            trips = trips.filter(date=date)
        if date_from:
            trips = trips.filter(date__gte=date_from)
        if date_to:
            trips = trips.filter(date__lte=date_to)
        if state is not None:
            trips = trips.filter(state=state.lower() == 'true')
        if invoice_id:
            trips = trips.filter(invoice_id=invoice_id)
        if advance_id:
            trips = trips.filter(advance_id=advance_id)

        serializer = TripReadSerializer(trips, many=True)
        return Response(serializer.data)

    @extend_schema(summary="Registrar un nuevo viaje.")
    def post(self, request):
        """Registrar un nuevo viaje."""
        if not can_register_trips(request.user):
            log_action(request, 'access_denied', 'Trip')
            return Response(
                {'error': 'No tiene permisos para registrar viajes.'},
                status=status.HTTP_403_FORBIDDEN
            )

        # Validar el serializer antes del atomic para retornar errores claros
        data = request.data.copy()
        data['voucher_num'] = 0  # temporal, se reemplaza dentro del atomic

        # RN#5 — si el frontend indicó una "transferencia pendiente" a
        # ejecutar, el medio de pago del viaje se autocompleta con el
        # guardado en el pendiente (sobreescribe lo que haya mandado el
        # caller a propósito). Se valida ANTES de construir el serializer
        # para que el 'payment' autocompletado pase también sus propias
        # validaciones (medio de pago activo, etc.).
        pending_entry = None
        pending_entry_id = request.data.get('pending_entry_id')
        if pending_entry_id:
            try:
                pending_entry = PendingEntry.objects.select_related('payment_method').get(pk=pending_entry_id)
            except PendingEntry.DoesNotExist:
                return Response({'error': 'Transferencia pendiente no encontrada.'}, status=status.HTTP_404_NOT_FOUND)
            if pending_entry.status != 'pending':
                return Response(
                    {'error': 'Este pendiente ya fue ejecutado o cancelado.'},
                    status=status.HTTP_409_CONFLICT
                )
            if pending_entry.entry_type != 'transfer':
                return Response(
                    {'error': 'Este pendiente no corresponde a una transferencia.'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            data['payment'] = pending_entry.payment_method_id

        serializer = TripWriteSerializer(data=data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        payment = serializer.validated_data.get('payment')  # type: ignore
        client  = serializer.validated_data.get('client')   # type: ignore
        value   = serializer.validated_data.get('value')    # type: ignore
        trip_date = serializer.validated_data.get('date')   # type: ignore

        # RN#5 — el cliente del pendiente debe coincidir con el del viaje, y
        # el valor debe coincidir EXACTO (sin justificación de excepción,
        # a diferencia del saldo insuficiente de anticipos más abajo).
        if pending_entry:
            if pending_entry.client_id != client.id:
                return Response(
                    {'error': 'El cliente del pendiente no coincide con el cliente del viaje.'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            if pending_entry.value != value:
                return Response({
                    'error': 'El valor del viaje no coincide con el valor de la transferencia pendiente.',
                    'valor_transferencia_pendiente': str(pending_entry.value),
                    'valor_viaje': str(value),
                }, status=status.HTTP_400_BAD_REQUEST)

        # REQUISITO NUEVO 3.1: un día con cierre de caja vigente no admite
        # viajes nuevos, ni siquiera del superusuario — la única vía es
        # revertir el cierre primero (POST /cash-closing/<id>/revert/) o
        # editar un viaje YA existente de ese día (RF-37, que sí sigue
        # permitido y dispara su propio recálculo, ver TripDetailView.patch).
        if DailySummary.objects.filter(
            date=trip_date, state=DailySummary.STATE_CLOSED
        ).exists():
            return Response({
                'error': (
                    f'El día {trip_date} ya tiene cierre de caja registrado. '
                    f'Debe revertir el cierre para registrar nuevos viajes.'
                )
            }, status=status.HTTP_409_CONFLICT)

        # FASE 3 — reemplaza el bloqueo duro de RF-31B. El anticipo a usar
        # ya NO lo elige quien llama al endpoint: siempre es "el anticipo
        # activo" del cliente (el más reciente, ver get_active_advance).
        # Cualquier `advance` que el caller haya mandado en el body se
        # ignora a propósito para esto (el validate() del serializer solo
        # lo usa como chequeo defensivo de que pertenezca al cliente).
        justification = request.data.get('justification', None)

        # Solo entrar al atomic para las escrituras
        try:
            with transaction.atomic():
                active_advance = None
                active_balance = Decimal('0')
                insufficient = False

                if payment and payment.is_advance:
                    # Lock del Client ANTES de decidir si hay anticipo activo
                    # y si alcanza — sin esto, un viaje que se registra al
                    # mismo tiempo que se crea un anticipo NUEVO para el
                    # mismo cliente (p. ej. cliente sin anticipo todavía)
                    # podía leer "sin anticipo" y quedar como deuda
                    # pendiente, mientras AdvanceListCreateView.post ya había
                    # (o estaba por) correr settle_pending_debts — que SÍ
                    # bloquea esta misma fila de Client — sin ver todavía
                    # este viaje (que aún no existía/no había comprometido).
                    # El viaje quedaba huérfano: nadie vuelve a intentar
                    # liquidarlo hasta que se cree OTRO anticipo futuro para
                    # ese cliente (TripDetailView.patch rechaza asignar
                    # `advance` a mano a una deuda pendiente). Bloqueando acá
                    # la misma fila, las dos operaciones quedan serializadas:
                    # cualquiera de las dos que gane la carrera, la otra ve
                    # el estado ya resuelto (el anticipo nuevo ya comprometido,
                    # o este viaje ya guardado como pendiente y listo para
                    # que settle_pending_debts lo recoja).
                    Client.objects.select_for_update().get(pk=client.id)

                    # FASE 6.1: select_for_update() sobre el anticipo activo
                    # ANTES de leer su saldo, para que dos registros
                    # concurrentes del mismo cliente no lean el mismo saldo
                    # "viejo" y decidan ambos que alcanza (o ambos que no).
                    # El segundo request espera a que el primero termine su
                    # transacción y recalcula el saldo ya actualizado. Mismo
                    # patrón que reallocate_advance_on_client_change y la
                    # liquidación de anticipos (Fase 3, settle_pending_debts).
                    candidate_advance = get_active_advance(client)
                    if candidate_advance:
                        active_advance = Advance.objects.select_for_update().get(pk=candidate_advance.pk)
                    active_balance = get_available_balance(active_advance) if active_advance else Decimal('0')
                    insufficient = value > active_balance

                    if insufficient and not justification:
                        return Response({
                            'error': (
                                'Saldo del anticipo insuficiente. Debe justificar el '
                                'registro para guardarlo como deuda pendiente.'
                            ),
                            'saldo_disponible': str(active_balance),
                            'valor_viaje': str(value),
                            'diferencia': str(value - active_balance),
                        }, status=status.HTTP_400_BAD_REQUEST)

                last_trip = Trip.objects.select_for_update().order_by('-voucher_num').first()
                next_voucher = (last_trip.voucher_num + 1) if last_trip else 1

                save_kwargs = dict(date_register=timezone.now(), voucher_num=next_voucher)
                if payment and payment.is_advance:
                    if insufficient:
                        # Deuda pendiente: sin anticipo asignado todavía, sin
                        # movimiento, con la justificación capturada.
                        save_kwargs['advance'] = None
                        save_kwargs['pending_debt_justification'] = justification
                    else:
                        save_kwargs['advance'] = active_advance

                trip = cast(Trip, serializer.save(**save_kwargs))

                if pending_entry:
                    execute_pending_transfer(pending_entry, trip, request=request)

                if payment and payment.is_advance and not insufficient:
                    AdvanceMovement.objects.create(
                        advance=active_advance,
                        trip=trip,
                        type_movement='egreso',
                        amount=trip.value,
                        trips_quantity=1,
                        date=trip.date,
                        description=f'Descuento por viaje #{trip.voucher_num}',
                    )

                new_data = dict(TripReadSerializer(trip).data)  # type: ignore
                if insufficient:
                    # RF-31B (reemplazado): antes esto solo se auditaba para
                    # el override de superuser; ahora aplica siempre que
                    # ocurra, sin importar el rol.
                    new_data['insufficient_balance_registration'] = {
                        'role': request.user.role,
                        'active_advance': active_advance.id if active_advance else None,
                        'available_balance': str(active_balance),
                        'shortfall': str(value - active_balance),
                    }
                log_action(
                    request, 'create', 'Trip',
                    object_id=trip.id,
                    new_data=new_data,
                    justification=(justification if insufficient else None),
                )

                return Response(
                    TripReadSerializer(trip).data,
                    status=status.HTTP_201_CREATED
                )

        except (PendingEntryNotPendingError, PendingEntryTypeMismatchError, PendingEntryClientMismatchError):
            # Carrera rara: el pendiente se ejecutó/canceló entre la
            # validación de arriba y este punto. El atomic ya revirtió la
            # creación del Trip.
            return Response(
                {'error': 'El pendiente ya no está disponible para ejecutar (puede haber sido ejecutado por otra solicitud).'},
                status=status.HTTP_409_CONFLICT
            )
        except PendingEntryValueMismatchError as e:
            # Defensa ante la misma carrera: si el valor dejó de coincidir
            # entre la validación de arriba y este punto (no debería pasar,
            # el valor del pendiente no cambia una vez creado, pero cubre el
            # caso igual).
            return Response({
                'error': 'El valor del viaje no coincide con el valor de la transferencia pendiente.',
                'valor_transferencia_pendiente': str(e.pending_value),
                'valor_viaje': str(e.actual_value),
            }, status=status.HTTP_400_BAD_REQUEST)
        except Exception:
            return Response(
                {'error': 'Error al registrar el viaje. Intente nuevamente.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class TripDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get_object(self, pk):
        try:
            return Trip.objects.get(pk=pk)
        except Trip.DoesNotExist:
            return None

    @extend_schema(summary="Consultar el detalle de un viaje.")
    def get(self, request, pk):
        """Consultar el detalle de un viaje."""
        obj = self.get_object(pk)
        if not obj:
            return Response(
                {'error': 'Viaje no encontrado.'},
                status=status.HTTP_404_NOT_FOUND
            )
        return Response(TripReadSerializer(obj).data)

    @extend_schema(summary="Editar, anular o desvincular la factura/certificado de un viaje.")
    def patch(self, request, pk):
        """Editar, anular o desvincular la factura/certificado de un viaje."""
        # 8B.4: desvincular una factura (`invoice` explícito en null) es una
        # operación separada, reservada a superuser/contabilidad — se
        # detecta ANTES del gate normal de can_update_trips() para que
        # accountant (que can_update_trips ya bloquea de plano, ver
        # test_accountant_cannot_patch_trip) pueda hacer específicamente
        # esta operación sin abrirle el resto del PATCH.
        is_unlink_request = 'invoice' in request.data and request.data.get('invoice') is None
        # Mismo patrón que is_unlink_request, para certificados de
        # disposición final (ver can_unlink_certificate arriba).
        is_unlink_certificate_request = 'certificate' in request.data and request.data.get('certificate') is None

        # BUG 1/2 (Fase 2): solo estos tres roles pueden ejecutar este PATCH.
        # Antes no había ningún chequeo de rol aquí — cualquier autenticado
        # (incluido 'auditor', que el ERS define como solo lectura absoluta)
        # podía modificar viajes. Se revisa antes de buscar el objeto, igual
        # que en el resto de vistas del proyecto (AdvanceDetailView.patch,
        # ExpenseDetailView.patch, etc.).
        if is_unlink_request:
            if not can_unlink_invoice(request.user):
                log_action(request, 'access_denied', 'Trip', object_id=pk)
                return Response(
                    {'error': 'No tiene permisos para desvincular una factura de un viaje.'},
                    status=status.HTTP_403_FORBIDDEN
                )
        elif is_unlink_certificate_request:
            if not can_unlink_certificate(request.user):
                log_action(request, 'access_denied', 'Trip', object_id=pk)
                return Response(
                    {'error': 'No tiene permisos para desvincular un certificado de un viaje.'},
                    status=status.HTTP_403_FORBIDDEN
                )
        elif not can_update_trips(request.user):
            log_action(request, 'access_denied', 'Trip', object_id=pk)
            return Response(
                {'error': 'No tiene permisos para modificar viajes.'},
                status=status.HTTP_403_FORBIDDEN
            )

        obj = self.get_object(pk)
        if not obj:
            return Response(
                {'error': 'Viaje no encontrado.'},
                status=status.HTTP_404_NOT_FOUND
            )

        # RF-37: registros anulados no pueden modificarse
        if not obj.state:
            return Response(
                {'error': 'No se puede modificar un viaje anulado.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # 8B.4: un viaje ya facturado no puede editar valor/cliente/medio de
        # pago — desalinearía lo facturado de lo que el sistema muestra
        # como registro operativo. Debe desvincularse la factura primero
        # (is_unlink_request arriba), en un request aparte: no se permite
        # combinar "desvincular" y "editar estos campos" en el mismo PATCH,
        # para mantener el flujo explícito en dos pasos.
        if obj.invoice_id is not None:
            touched_locked_fields = FINANCIAL_FIELDS_LOCKED_WHEN_INVOICED & set(request.data.keys())
            if touched_locked_fields:
                log_action(request, 'access_denied', 'Trip', object_id=obj.id)
                return Response({
                    'error': (
                        'Este viaje ya está facturado y no puede editar valor, '
                        'cliente ni medio de pago. Desvincule la factura primero '
                        '(superuser o contabilidad).'
                    ),
                    'fields': sorted(touched_locked_fields),
                }, status=status.HTTP_409_CONFLICT)

        # date_register se guarda en UTC (datetime aware); hay que convertirlo
        # a la zona horaria local antes de comparar fechas de calendario, o si
        # no, durante la ventana diaria en que UTC ya cambió de día pero la
        # zona local (Bogotá) todavía no, un viaje recién creado "hoy" se
        # trataría como histórico.
        is_registered_today = timezone.localtime(obj.date_register).date() == timezone.localdate()

        # RF-36: cashier y commercial_admin solo pueden editar registros del
        # día en curso (mismo nivel en la matriz de roles: CRU, no D).
        #
        # Excepción: commercial_admin sí puede ajustar un registro histórico
        # si el ÚNICO campo que envía es 'observations' — permiso nuevo,
        # equivalente a lo que ya tiene superuser pero acotado a ese campo
        # (todo lo demás sigue bloqueado). cashier no entra en esta excepción.
        if request.user.role in SAME_DAY_ONLY_ROLES and not is_registered_today:
            touched_fields = set(request.data.keys()) - {'justification'}
            is_commercial_admin_observations_only = (
                request.user.role == 'commercial_admin'
                and bool(touched_fields)
                and touched_fields.issubset({'observations'})
            )
            if not is_commercial_admin_observations_only:
                log_action(request, 'access_denied', 'Trip', object_id=obj.id)
                return Response(
                    {'error': 'Solo puede modificar registros del día en curso.'},
                    status=status.HTTP_403_FORBIDDEN
                )

        # Capturar datos anteriores antes de modificar (RF-38)
        previous = dict(TripReadSerializer(obj).data)  # type: ignore

        # El superuser puede editar registros históricos o de un día ya
        # cerrado sin justificar (decisión explícita: se quitó esa exigencia
        # a cambio de concentrar la justificación únicamente en la
        # anulación, más abajo). El bloqueo de día cerrado para los demás
        # roles sigue vigente — esto solo afecta a superuser.

        serializer = TripWriteSerializer(obj, data=request.data, partial=True)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        # RF-37: si es anulación, registrar como 'annul'.
        #
        # 9.2 — se lee de `serializer.validated_data` (ya parseado/validado
        # por DRF), no del payload crudo `request.data`. `request.data.get(
        # 'state') is False` solo detectaba una anulación cuando el campo
        # llegaba como bool nativo de JSON (`false`); si el mismo request
        # llegaba form-encoded (`state=false` como string), DRF igual lo
        # normalizaba a `False` en validated_data (por eso la anulación se
        # aplicaba igual), pero esa comparación cruda nunca lo detectaba —
        # así que la anulación se colaba sin exigir justificación, sin el
        # AuditLog de tipo 'annul', y sin revertir el saldo del anticipo.
        # validated_data.get('state', obj.state) usa el estado actual como
        # default para un PATCH parcial que no toca 'state' en absoluto.
        is_annulment = serializer.validated_data.get('state', obj.state) is False  # type: ignore[union-attr]
        action = 'annul' if is_annulment else 'update'
        justification = request.data.get('justification', None)
        INVOICE_ONLY_FIELDS = {'invoice', 'invoice_pos'}
        CERTIFICATE_ONLY_FIELDS = {'certificate', 'certificate_pos'}
        incoming_fields = set(request.data.keys()) - {'justification'}
        is_invoice_only_patch = incoming_fields.issubset(INVOICE_ONLY_FIELDS)
        is_certificate_only_patch = incoming_fields.issubset(CERTIFICATE_ONLY_FIELDS)

        # Un viaje ya facturado y/o certificado no puede anularse directamente
        # — dejaría la factura/certificado apuntando a un registro anulado,
        # sin ninguna corrección. Mismo principio que
        # FINANCIAL_FIELDS_LOCKED_WHEN_INVOICED (editar value/client/payment
        # de un viaje facturado ya lo bloqueaba), que hasta ahora no cubría
        # 'state'. Se exige desvincular primero, en un request aparte —
        # mismo flujo en dos pasos que ya rige para editar esos otros campos
        # (superuser/contabilidad para factura vía can_unlink_invoice,
        # superuser/certifier para certificado vía can_unlink_certificate).
        if is_annulment:
            linked_to = []
            if obj.invoice_id is not None:
                linked_to.append('factura')
            if obj.certificate_id is not None:
                linked_to.append('certificado')
            if linked_to:
                log_action(request, 'access_denied', 'Trip', object_id=obj.id)
                return Response({
                    'error': (
                        f'Este viaje ya tiene {" y ".join(linked_to)} vinculado y no '
                        f'puede anularse. Desvincule primero.'
                    ),
                    'linked': linked_to,
                }, status=status.HTTP_409_CONFLICT)

        # Decisión: anular un viaje exige justificación siempre, sin importar
        # el rol — incluido superuser. Antes solo se le exigía a cashier/
        # commercial_admin (en vez de bloquearles la anulación por completo,
        # ya que el ERS habla de un flujo de "requiere revisión" que todavía
        # no existe como campo/feature — construirlo es negocio nuevo, fuera
        # de esta fase de permisos); ahora se unifica: la anulación es lo
        # único que pide justificación en este PATCH (ver más abajo: editar
        # un registro histórico o de un día cerrado ya NO la exige).
        if is_annulment and not justification:
            log_action(request, 'access_denied', 'Trip', object_id=obj.id)
            return Response(
                {'error': 'Se requiere justificación para anular un viaje.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # REQUISITO NUEVO (Fase 2): un día con cierre de caja vigente solo
        # puede tocarse mediante el ajuste histórico de superuser (RF-37).
        # No se separó en un endpoint nuevo (ver decisión registrada en el
        # resumen de esta fase) — sigue siendo este mismo PATCH, distinguido
        # por esta condición. Los patches que solo tocan invoice/invoice_pos
        # (o certificate/certificate_pos) quedan exentos, igual que la regla
        # de justificación de abajo, porque no afectan los totales que
        # protege el cierre.
        day_closed = DailySummary.objects.filter(
            date=obj.date, state=DailySummary.STATE_CLOSED
        ).exists()
        if (
            day_closed and request.user.role != 'superuser'
            and not is_invoice_only_patch and not is_certificate_only_patch
        ):
            log_action(request, 'access_denied', 'Trip', object_id=obj.id)
            return Response({
                'error': (
                    'Este viaje pertenece a un día con cierre de caja registrado. '
                    'Solo el superusuario puede modificarlo (ajuste histórico).'
                )
            }, status=status.HTTP_409_CONFLICT)

        # BUG 2 — snapshot de cómo estaba financiado el viaje ANTES de
        # guardar, para poder calcular la reversión/ajuste del anticipo
        # correspondiente después.
        old_value = obj.value
        old_advance = obj.advance
        old_payment = obj.payment
        was_advance_funded = old_payment.is_advance and old_advance is not None
        force = str(request.data.get('force', '')).lower() == 'true'

        # Cambio de cliente: no hay "mismo anticipo" que ajustar por
        # diferencia — el saldo se devuelve completo al cliente anterior y
        # el viaje se reevalúa desde cero contra el anticipo activo del
        # cliente nuevo (reallocate_advance_on_client_change), con las
        # mismas reglas que un registro nuevo.
        #
        # 9.1 (extendido): a diferencia de TripListCreateView.post (donde el
        # chequeo de saldo ya vive DENTRO del atomic, tras el lock), este
        # chequeo se hacía acá ANTES del atomic, sin lock — dos cambios de
        # cliente concurrentes hacia el MISMO cliente destino podían leer el
        # mismo saldo "viejo" y ambos concluir que alcanzaba (o que no). Se
        # movió a reallocate_advance_on_client_change, que ya bloqueaba la
        # fila del Client destino para el descuento: ahora también decide
        # ahí si hace falta justificación, contra el saldo real post-lock
        # (ver InsufficientBalanceForAdvanceFundingError, capturada más abajo).
        new_client = serializer.validated_data.get('client', obj.client)  # type: ignore
        client_changed = new_client.id != obj.client_id and not is_annulment

        # FASE 3: un viaje en deuda pendiente (payment.is_advance=True,
        # advance=NULL) solo puede quedar liquidado a través de
        # settle_pending_debts (automático, FIFO, al registrar un anticipo
        # nuevo para el cliente). No se soporta asignarle un anticipo a
        # mano por este PATCH — eso dejaría el viaje con `advance` puesto
        # pero sin el AdvanceMovement que debería acompañarlo. No aplica
        # cuando el cliente cambia: ahí el `advance` lo recalcula el
        # backend por su cuenta (ver más abajo), ignorando lo que mande el caller.
        was_pending_debt = old_payment.is_advance and old_advance is None
        incoming_advance = request.data.get('advance')
        if (
            was_pending_debt and not client_changed
            and 'advance' in request.data and incoming_advance not in (None, '')
        ):
            return Response({
                'error': (
                    'No se puede asignar manualmente un anticipo a un viaje con '
                    'deuda pendiente. Se liquida automáticamente al registrar un '
                    'anticipo nuevo para el cliente.'
                )
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            with transaction.atomic():
                # Bloquea la fila del viaje durante toda la edición: evita
                # que dos PATCH concurrentes al mismo viaje calculen la
                # reversión de saldo a partir del mismo "valor viejo".
                Trip.objects.select_for_update().get(pk=obj.pk)

                if client_changed:
                    # El backend recalcula 'advance' por su cuenta (igual
                    # que en el registro) — lo que el caller haya mandado
                    # para ese campo se ignora a propósito.
                    trip = cast(Trip, serializer.save(advance=obj.advance))
                    reallocate_advance_on_client_change(
                        trip,
                        old_advance=old_advance,
                        was_advance_funded=was_advance_funded,
                        old_value=old_value,
                        justification=justification,
                        request=request,
                    )
                else:
                    # BUG 1: si el medio de pago deja de ser de tipo
                    # anticipo, el viaje ya no puede seguir financiado por
                    # el anticipo actual — se ignora a propósito cualquier
                    # `advance` que venga en el payload (igual que en la
                    # rama client_changed) y el backend decide el resultado.
                    new_payment = serializer.validated_data.get('payment', obj.payment)  # type: ignore
                    payment_leaving_advance = was_advance_funded and not new_payment.is_advance
                    # 9.7A: el viaje NO estaba financiado por anticipo (ni
                    # siquiera como deuda pendiente — was_pending_debt exige
                    # old_payment.is_advance=True, así que es mutuamente
                    # excluyente con esto) y su medio de pago pasa a ser de
                    # tipo anticipo por primera vez. Antes esto caía en el
                    # `else` de abajo sin hacer nada más que cambiar
                    # `payment`: el viaje quedaba con la misma huella que
                    # una deuda pendiente (payment.is_advance=True,
                    # advance=NULL) pero sin pasar por ninguna validación de
                    # saldo ni crear el AdvanceMovement correspondiente — el
                    # anticipo del cliente seguía mostrando su saldo
                    # completo, aunque el viaje ya "debía" cubrirse contra
                    # él. Se resuelve con las mismas reglas que un cambio de
                    # cliente (ver fund_trip_entering_advance_payment).
                    payment_entering_advance = not old_payment.is_advance and new_payment.is_advance

                    if payment_leaving_advance:
                        trip = cast(Trip, serializer.save(advance=None, pending_debt_justification=None))
                        reverse_advance_discount(
                            trip,
                            advance=old_advance,  # type: ignore[arg-type]
                            amount=old_value,
                            reason=f'Reversión por cambio de medio de pago del viaje #{trip.voucher_num}',
                            request=request,
                        )
                    elif payment_entering_advance:
                        save_kwargs = {}
                        if is_unlink_request:
                            save_kwargs['invoice_pos'] = None
                        if is_unlink_certificate_request:
                            save_kwargs['certificate_pos'] = None
                        trip = cast(Trip, serializer.save(**save_kwargs))
                        fund_trip_entering_advance_payment(
                            trip, justification=justification, request=request,
                        )
                    else:
                        # 8B.4: al desvincular (invoice=None o
                        # certificate=None), limpiar también invoice_pos/
                        # certificate_pos — no tendría sentido dejar un
                        # número de posición colgado sin la factura/
                        # certificado al que pertenecía. El caller solo manda
                        # `invoice: null`/`certificate: null`, no el _pos,
                        # así que se fuerza acá igual que otros campos
                        # derivados en este PATCH.
                        save_kwargs = {}
                        if is_unlink_request:
                            save_kwargs['invoice_pos'] = None
                        if is_unlink_certificate_request:
                            save_kwargs['certificate_pos'] = None
                        trip = cast(Trip, serializer.save(**save_kwargs))
                        if was_advance_funded:
                            sync_advance_movement_on_trip_change(
                                trip,
                                was_advance_funded=True,
                                old_value=old_value,
                                old_advance=old_advance,
                                new_advance=trip.advance,
                                is_annulment=is_annulment,
                                force=force,
                                is_superuser=(request.user.role == 'superuser'),
                                request=request,
                                justification=justification,
                            )

                # Se deja al final, ya con 'advance'/'pending_debt_justification'
                # resueltos: si algo falla más arriba (saldo insuficiente,
                # cambio de anticipo no soportado), el rollback del atomic
                # también deshace este log — no debe quedar un registro de
                # auditoría describiendo un cambio que finalmente no se aplicó.
                log_action(
                    request, action, 'Trip',
                    object_id=obj.id,
                    previous_data=previous,
                    new_data=dict(TripReadSerializer(trip).data),  # type: ignore
                    justification=justification,
                )

                # REQUISITO NUEVO 3.4: si el día de este viaje ya tiene un
                # cierre vigente, se recalcula DESPUÉS del AdvanceMovement de
                # arriba (el total por 'anticipo' del día depende del valor/
                # estado del viaje en este instante). Solo se dispara si el
                # PATCH tocó un campo que puede cambiar los totales.
                if incoming_fields & FIELDS_AFFECTING_TOTALS:
                    resync_if_closed(
                        trip.date,
                        request=request,
                        trigger_note=(
                            f'Recalculado por {action} del viaje '
                            f'#{trip.voucher_num} (RF-37/ajuste histórico).'
                        ),
                    )
        except InsufficientBalanceError as e:
            return Response({
                'error': 'Saldo insuficiente para aplicar este cambio.',
                'saldo_disponible': str(e.balance),
                'valor_requerido': str(e.required),
                'diferencia': str(e.difference),
            }, status=status.HTTP_400_BAD_REQUEST)
        except InsufficientBalanceForAdvanceFundingError as e:
            # Compartido por dos transiciones (cambio de cliente, y medio de
            # pago que pasa a ser de tipo anticipo por primera vez): el
            # mensaje es genérico a propósito, no menciona "nuevo cliente".
            return Response({
                'error': (
                    'Saldo del anticipo insuficiente para financiar este viaje. '
                    'Debe justificar el ajuste para guardarlo como deuda pendiente.'
                ),
                'saldo_disponible': str(e.balance),
                'valor_viaje': str(e.required),
                'diferencia': str(e.difference),
            }, status=status.HTTP_400_BAD_REQUEST)
        except UnsupportedAdvanceChangeError:
            return Response({
                'error': (
                    'No se permite asignar manualmente el campo "advance" '
                    '(a otro anticipo, o a vacío) de un viaje que ya está '
                    'financiado por un anticipo. Para dejar de financiarlo '
                    'con el anticipo actual, cambie el medio de pago a uno '
                    'que no sea de tipo "anticipo", o anule el viaje.'
                )
            }, status=status.HTTP_400_BAD_REQUEST)

        return Response(TripReadSerializer(trip).data)
