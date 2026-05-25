from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from apps.audit.services import log_action
from typing import cast

from .models import Expense
from .serializers import ExpenseSerializer


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

        # Capturar datos anteriores antes de modificar
        previous = dict(ExpenseSerializer(obj).data)  # type: ignore

        serializer = ExpenseSerializer(obj, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            log_action(
                request, 'update', 'Expense',
                object_id=obj.id,
                previous_data=previous,
                new_data=dict(serializer.data),  # type: ignore
            )
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)