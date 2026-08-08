from django.urls import path
from .views import AdvanceListCreateView, AdvanceDetailView, AdvanceBalanceView, AdvanceCorrectValueView

urlpatterns = [
    path('',                       AdvanceListCreateView.as_view(), name='advance-list'),
    path('<int:pk>/',              AdvanceDetailView.as_view(),     name='advance-detail'),
    path('<int:pk>/correct-value/', AdvanceCorrectValueView.as_view(), name='advance-correct-value'),
    path('balance/<int:client_id>/', AdvanceBalanceView.as_view(), name='advance-balance'),
]