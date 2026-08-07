from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from .views import LoginView, LogoutView, UserListCreateView, UserDetailView, ChangePasswordView, ResetPasswordAdminView

urlpatterns = [
    path('login/',                        LoginView.as_view(),             name='login'),
    path('logout/',                       LogoutView.as_view(),            name='logout'),
    # 8A.3: TokenRefreshView estándar de simplejwt — permission_classes=()
    # y authentication_classes=() en la propia librería, así que no exige
    # que el caller esté autenticado (el access token ya pudo expirar,
    # que es justo el caso que este endpoint existe para resolver). Con
    # ROTATE_REFRESH_TOKENS=True (settings.py) devuelve access Y refresh
    # nuevos; con token_blacklist instalado, un refresh token ya
    # blacklisteado (logout, desactivación, o 8A.1) se rechaza solo.
    path('token/refresh/',                TokenRefreshView.as_view(),      name='token-refresh'),
    path('',                              UserListCreateView.as_view(),    name='user-list-create'),
    path('<int:pk>/',                     UserDetailView.as_view(),        name='user-detail'),
    path('<int:pk>/reset-password/',      ResetPasswordAdminView.as_view(), name='user-reset-password'),
    path('change-password/',              ChangePasswordView.as_view(),    name='change-password'),
]