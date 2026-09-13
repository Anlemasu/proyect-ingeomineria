from django.urls import path
from .views import PendingEntryListCreateView, PendingEntryDetailView, PendingEntryCancelView

urlpatterns = [
    path('', PendingEntryListCreateView.as_view(), name='pending-entry-list'),
    path('<int:pk>/', PendingEntryDetailView.as_view(), name='pending-entry-detail'),
    path('<int:pk>/cancel/', PendingEntryCancelView.as_view(), name='pending-entry-cancel'),
]
