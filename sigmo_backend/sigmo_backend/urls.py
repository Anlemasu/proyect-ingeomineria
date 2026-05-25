from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/',         admin.site.urls),
    path('api/users/',     include('apps.users.urls')),
    path('api/masters/',   include('apps.masters.urls')),
    path('api/clients/',   include('apps.clients.urls')),
    path('api/advances/',  include('apps.advances.urls')),
    path('api/expenses/',  include('apps.expenses.urls')),
    path('api/invoices/',  include('apps.invoices.urls')),
    path('api/trips/',     include('apps.trips.urls')),
    path('api/cash-closing/', include('apps.cash_closing.urls')),
    path('api/audit/', include('apps.audit.urls')),
]