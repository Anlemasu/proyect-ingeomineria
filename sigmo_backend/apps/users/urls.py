from django.urls import path
from .views import LoginView, LogoutView, UserListCreateView, UserDetailView, ChangePasswordView

urlpatterns = [
    path('login/',           LoginView.as_view(),          name='login'),
    path('logout/',          LogoutView.as_view(),          name='logout'),
    path('',                 UserListCreateView.as_view(),  name='user-list-create'),
    path('<int:pk>/',        UserDetailView.as_view(),      name='user-detail'),
    path('change-password/', ChangePasswordView.as_view(),  name='change-password'),
]