from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import authenticate
from django.core.cache import cache
from django.conf import settings
from apps.audit.services import log_action
from typing import cast

from .models import User
from .serializers import UserReadSerializer, UserCreateSerializer, ChangePasswordSerializer


def is_superuser(user):
    return user.role == 'superuser'


class LoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        username = request.data.get('username')
        password = request.data.get('password')

        if not username or not password:
            return Response(
                {'error': 'Usuario y contraseña son requeridos.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        lockout_key = f'lockout_{username}'
        attempts_key = f'attempts_{username}'

        if cache.get(lockout_key):
            return Response(
                {'error': 'Cuenta bloqueada temporalmente. Intente en 15 minutos.'},
                status=status.HTTP_429_TOO_MANY_REQUESTS
            )

        auth_user = authenticate(request, username=username, password=password)

        if auth_user is None:
            attempts = cache.get(attempts_key, 0) + 1
            cache.set(attempts_key, attempts, timeout=60 * settings.LOGIN_LOCKOUT_MINUTES)

            if attempts >= settings.LOGIN_MAX_ATTEMPTS:
                cache.set(lockout_key, True, timeout=60 * settings.LOGIN_LOCKOUT_MINUTES)
                cache.delete(attempts_key)
                return Response(
                    {'error': 'Cuenta bloqueada por 15 minutos por múltiples intentos fallidos.'},
                    status=status.HTTP_429_TOO_MANY_REQUESTS
                )

            return Response(
                {'error': f'Credenciales incorrectas. Intentos fallidos: {attempts}/{settings.LOGIN_MAX_ATTEMPTS}.'},
                status=status.HTTP_401_UNAUTHORIZED
            )

        user: User = auth_user  # type: ignore

        if not user.state:
            return Response(
                {'error': 'Usuario inactivo. Contacte al administrador.'},
                status=status.HTTP_403_FORBIDDEN
            )

        cache.delete(attempts_key)
        cache.delete(lockout_key)

        refresh = RefreshToken.for_user(user)

        # RF-05: registrar inicio de sesión exitoso
        log_action(request, 'login', 'User', object_id=user.id, user=user)

        return Response({
            'access': str(refresh.access_token),
            'refresh': str(refresh),
            'user': UserReadSerializer(user).data,
        }, status=status.HTTP_200_OK)


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        # RF-05: registrar cierre de sesión
        log_action(request, 'logout', 'User', object_id=request.user.id)
        return Response(
            {'message': 'Sesión cerrada correctamente.'},
            status=status.HTTP_200_OK
        )


class UserListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not is_superuser(request.user):
            log_action(request, 'access_denied', 'User')
            return Response(
                {'error': 'No tiene permisos para ver usuarios.'},
                status=status.HTTP_403_FORBIDDEN
            )
        users = User.objects.all().order_by('name')
        serializer = UserReadSerializer(users, many=True)
        return Response(serializer.data)

    def post(self, request):
        if not is_superuser(request.user):
            log_action(request, 'access_denied', 'User')
            return Response(
                {'error': 'No tiene permisos para crear usuarios.'},
                status=status.HTTP_403_FORBIDDEN
            )
        serializer = UserCreateSerializer(data=request.data)
        if serializer.is_valid():
            new_user = cast(User, serializer.save())
            log_action(
                request, 'create', 'User',
                object_id=new_user.id,
                new_data={
                    'username': new_user.username,
                    'email': new_user.email,
                    'role': new_user.role,
                }
            )
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class UserDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get_object(self, pk):
        try:
            return User.objects.get(pk=pk)
        except User.DoesNotExist:
            return None

    def get(self, request, pk):
        if not is_superuser(request.user):
            log_action(request, 'access_denied', 'User', object_id=pk)
            return Response(
                {'error': 'No tiene permisos.'},
                status=status.HTTP_403_FORBIDDEN
            )
        user = self.get_object(pk)
        if not user:
            return Response(
                {'error': 'Usuario no encontrado.'},
                status=status.HTTP_404_NOT_FOUND
            )
        return Response(UserReadSerializer(user).data)

    def patch(self, request, pk):
        if not is_superuser(request.user):
            log_action(request, 'access_denied', 'User', object_id=pk)
            return Response(
                {'error': 'No tiene permisos para editar usuarios.'},
                status=status.HTTP_403_FORBIDDEN
            )
        user = self.get_object(pk)
        if not user:
            return Response(
                {'error': 'Usuario no encontrado.'},
                status=status.HTTP_404_NOT_FOUND
            )

        # Capturar datos anteriores antes de modificar
        previous = dict(UserReadSerializer(user).data)  # type: ignore

        serializer = UserReadSerializer(user, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            log_action(
                request, 'update', 'User',
                object_id=user.id,
                previous_data=previous,
                new_data=dict(serializer.data),  # type: ignore
            )
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ChangePasswordView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ChangePasswordSerializer(
            data=request.data,
            context={'request': request}
        )
        if serializer.is_valid():
            new_password: str = serializer.validated_data.get('new_password')  # type: ignore
            request.user.set_password(new_password)
            request.user.save()
            # RF-05: registrar cambio de contraseña sin guardar la contraseña
            log_action(
                request, 'update', 'User',
                object_id=request.user.id,
                new_data={'action': 'password_changed'},
            )
            return Response(
                {'message': 'Contraseña actualizada correctamente.'},
                status=status.HTTP_200_OK
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)