from django.urls import path
from .views import (
    VehicleTypeListCreateView, VehicleTypeDetailView,
    MaterialTypeListCreateView, MaterialTypeDetailView,
    PaymentMethodListCreateView, PaymentMethodDetailView,
    OriginSiteListCreateView, OriginSiteDetailView,
    CityListCreateView, CityDetailView,
    TariffListCreateView, TariffDetailView,
    PinsDumperListCreateView, PinsDumperImportView,
    VehicleListCreateView,
)

urlpatterns = [
    # Tipos de vehículo
    path('vehicle-types/',          VehicleTypeListCreateView.as_view(),  name='vehicle-type-list'),
    path('vehicle-types/<int:pk>/', VehicleTypeDetailView.as_view(),      name='vehicle-type-detail'),
    # Tipos de material
    path('material-types/',          MaterialTypeListCreateView.as_view(), name='material-type-list'),
    path('material-types/<int:pk>/', MaterialTypeDetailView.as_view(),     name='material-type-detail'),
    # Medios de pago
    path('payment-methods/',          PaymentMethodListCreateView.as_view(), name='payment-method-list'),
    path('payment-methods/<int:pk>/', PaymentMethodDetailView.as_view(),     name='payment-method-detail'),
    # Orígenes
    path('origin-sites/',          OriginSiteListCreateView.as_view(), name='origin-site-list'),
    path('origin-sites/<int:pk>/', OriginSiteDetailView.as_view(),     name='origin-site-detail'),
    # Ciudades
    path('cities/',          CityListCreateView.as_view(), name='city-list'),
    path('cities/<int:pk>/', CityDetailView.as_view(),      name='city-detail'),
    # Tarifas
    path('tariffs/',          TariffListCreateView.as_view(), name='tariff-list'),
    path('tariffs/<int:pk>/', TariffDetailView.as_view(),     name='tariff-detail'),
    # Pines
    path('pins/',  PinsDumperListCreateView.as_view(), name='pins-list'),
    path('pins/import/',   PinsDumperImportView.as_view(),     name='pins-import'),
    # Vehículos
    path('vehicles/', VehicleListCreateView.as_view(), name='vehicle-list'),
]