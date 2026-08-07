from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db import transaction
from django.utils.dateparse import parse_date
from apps.audit.services import log_action
from typing import cast

from .models import Expense
from .serializers import ExpenseSerializer
from apps.cash_closing.models import DailySummary
from apps.cash_closing.services import resync_if_closed

# Campos cuyo cambio afecta los totales de un DailySummary ya cerrado (mismo
# criterio que FIELDS_AFFECTING_TOTALS en trips/views.py).
FIELDS_AFFECTING_TOTALS = {'value', 'state'}


def can_manage_expenses(user):
    return user.role in ['superuser', 'cashier', 'commercial_admin']


class ExpenseListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        expenses = Expense.objects.all().order_by('-date')

        date = request.query_params.get('date')
        date_from = request.query_params.get('date_from')
        date_to = request.query_params.get('date_to')

        if date:
            expenses = expenses.filter(date=date)
        if date_from:
            expenses = expenses.filter(date__gte=date_from)
        if date_to:
            expenses = expenses.filter(date__lte=date_to)

        serializer = ExpenseSerializer(expenses, many=True)
        return Response(serializer.data)

    def post(self, request):
        if not can_manage_expenses(request.user):
            log_action(request, 'access_denied', 'Expense')
            return Response(
                {'error': 'No tiene permisos para registrar gastos.'},
                status=status.HTTP_403_FORBIDDEN
            )
        serializer = ExpenseSerializer(data=request.data)
        if serializer.is_valid():
            # REQUISITO NUEVO 3.1: mismo bloqueo que en trips — un día con
            # cierre de caja vigente no admite gastos nuevos.
            expense_date = serializer.validated_data.get('date')  # type: ignore
            if DailySummary.objects.filter(
                date=expense_date, state=DailySummary.STATE_CLOSED
            ).exists():
                return Response({
                    'error': (
                        f'El día {expense_date} ya tiene cierre de caja registrado. '
                        f'Debe revertir el cierre para registrar nuevos gastos.'
                    )
                }, status=status.HTTP_409_CONFLICT)

            expense = cast(Expense, serializer.save(user=request.user))
            log_action(
                request, 'create', 'Expense',
                object_id=expense.id,
                new_data=dict(serializer.data),  # type: ignore
            )
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ExpenseDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get_object(self, pk):
        try:
            return Expense.objects.get(pk=pk)
        except Expense.DoesNotExist:
            return None

    def get(self, request, pk):
        obj = self.get_object(pk)
        if not obj:
            return Response(
                {'error': 'Gasto no encontrado.'},
                status=status.HTTP_404_NOT_FOUND
            )
        return Response(ExpenseSerializer(obj).data)

    def patch(self, request, pk):
        if not can_manage_expenses(request.user):
            log_action(request, 'access_denied', 'Expense', object_id=pk)
            return Response(
                {'error': 'No tiene permisos para editar gastos.'},
                status=status.HTTP_403_FORBIDDEN
            )
        obj = self.get_object(pk)
        if not obj:
            return Response(
                {'error': 'Gasto no encontrado.'},
                status=status.HTTP_404_NOT_FOUND
            )

        # Mismo criterio que Trip: un gasto ya anulado no puede modificarse.
        if not obj.state:
            return Response(
                {'error': 'No se puede modificar un gasto anulado.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # FASE 5.3: mismo criterio que Trip (RF-37) — un día con cierre de
        # caja vigente solo puede tocarse (edición o anulación) por
        # superuser, como ajuste histórico. No se creó un ajuste histórico
        # nuevo para gastos: simplemente se bloquea para los demás roles.
        #
        # 8B.2: esta validación debe cubrir tanto la fecha ACTUAL del gasto
        # como la fecha NUEVA propuesta (si `date` viene en el PATCH) — antes
        # solo miraba obj.date, así que mover un gasto hacia o desde un día
        # cerrado, en el mismo request, evadía el bloqueo por completo
        # (se validaba la fecha equivocada). Si el `date` entrante no es un
        # string parseable, se ignora acá — el serializer lo rechazará
        # después con su propio 400, no hace falta duplicar esa validación.
        day_closed_dates = {obj.date}
        incoming_date_raw = request.data.get('date')
        if incoming_date_raw:
            parsed_new_date = (
                parse_date(incoming_date_raw)
                if isinstance(incoming_date_raw, str)
                else incoming_date_raw
            )
            if parsed_new_date:
                day_closed_dates.add(parsed_new_date)

        day_closed = DailySummary.objects.filter(
            date__in=day_closed_dates, state=DailySummary.STATE_CLOSED
        ).exists()
        if day_closed and request.user.role != 'superuser':
            log_action(request, 'access_denied', 'Expense', object_id=obj.id)
            return Response({
                'error': (
                    'Este gasto pertenece a un día con cierre de caja registrado. '
                    'Solo el superusuario puede modificarlo (ajuste histórico).'
                )
            }, status=status.HTTP_409_CONFLICT)

        is_annulment = request.data.get('state') is False
        action = 'annul' if is_annulment else 'update'
        justification = request.data.get('justification', None)
        if is_annulment and not justification:
            log_action(request, 'access_denied', 'Expense', object_id=obj.id)
            return Response(
                {'error': 'Se requiere justificación para anular un gasto.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Capturar datos anteriores antes de modificar
        previous = dict(ExpenseSerializer(obj).data)  # type: ignore
        incoming_fields = set(request.data.keys()) - {'justification'}

        serializer = ExpenseSerializer(obj, data=request.data, partial=True)
        if serializer.is_valid():
            # 8B.1: la anulación/edición del gasto y el recálculo del
            # DailySummary deben confirmarse o fallar juntos — antes corrían
            # como dos pasos independientes sin transacción (si algo fallaba
            # a mitad del recálculo, el gasto ya había quedado guardado).
            # Además, resync_if_closed depende de correr DENTRO de un
            # transaction.atomic() para su propio select_for_update() (ver
            # docstring en cash_closing/services.py) — sin este atomic(),
            # en Postgres eso lanzaría TransactionManagementError fuera de
            # los tests (los TestCase de Django ya envuelven cada test en su
            # propia transacción, lo que enmascaraba el problema ahí).
            with transaction.atomic():
                expense = cast(Expense, serializer.save())
                log_action(
                    request, action, 'Expense',
                    object_id=expense.id,
                    previous_data=previous,
                    new_data=dict(serializer.data),  # type: ignore
                    justification=(justification if is_annulment else None),
                )

                # Mismo motivo que en Trip: un cierre vigente que ya sumó
                # este gasto queda desactualizado si no se recalcula tras
                # la edición.
                if day_closed and incoming_fields & FIELDS_AFFECTING_TOTALS:
                    resync_if_closed(
                        expense.date,
                        request=request,
                        trigger_note=(
                            f'Recalculado por {action} del gasto #{expense.id} '
                            f'(ajuste histórico).'
                        ),
                    )

            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)