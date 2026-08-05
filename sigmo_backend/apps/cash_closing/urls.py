from django.urls import path
from .views import (
    DailySummaryListView, DailySummaryCloseView, DailySummaryTodayView,
    DailySummaryRevertView,
)

urlpatterns = [
    path('',                DailySummaryListView.as_view(),   name='cash-closing-list'),
    path('close/',          DailySummaryCloseView.as_view(),  name='cash-closing-close'),
    path('today/',          DailySummaryTodayView.as_view(),  name='cash-closing-today'),
    path('<int:pk>/revert/', DailySummaryRevertView.as_view(), name='cash-closing-revert'),
]