from django.urls import path
from .views import (
    PhysicalReportListView,
    ClosedPhysicalReportListView,
    PhysicalReportBulkEntryView,
    PhysicalReportDetailView,
    PhysicalReportEntryView,
    PhysicalReportQuotaView,
    PhysicalReportCloseView,
    PhysicalReportUndoCloseView,
    PhysicalReportReopenView,
)

urlpatterns = [
    path('',                    PhysicalReportListView.as_view(),        name='physical-report-list'),
    path('closed/',             ClosedPhysicalReportListView.as_view(),  name='physical-report-closed-list'),
    path('bulk-entries/',       PhysicalReportBulkEntryView.as_view(),   name='physical-report-bulk-entries'),
    path('<int:pk>/',           PhysicalReportDetailView.as_view(),      name='physical-report-detail'),
    path('<int:pk>/entries/',   PhysicalReportEntryView.as_view(),       name='physical-report-entry'),
    path('<int:pk>/quota/',     PhysicalReportQuotaView.as_view(),       name='physical-report-quota'),
    path('<int:pk>/close/',     PhysicalReportCloseView.as_view(),       name='physical-report-close'),
    path('<int:pk>/undo-close/', PhysicalReportUndoCloseView.as_view(),  name='physical-report-undo-close'),
    path('<int:pk>/reopen/',    PhysicalReportReopenView.as_view(),      name='physical-report-reopen'),
]
