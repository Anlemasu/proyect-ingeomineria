from django.contrib import admin
from django.urls import path, include
from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView, SpectacularSwaggerView


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

    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    # Interfaz visual de Swagger
    path('api/docs/swagger/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    # Interfaz visual de Redoc (Lectura limpia)
    path('api/docs/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),
]