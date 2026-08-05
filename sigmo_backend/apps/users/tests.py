from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError

from .models import User


class JWTBlacklistTests(TestCase):
    """
    FASE 2 — BUG 3: sin 'rest_framework_simplejwt.token_blacklist' instalado,
    ni logout ni desactivar un usuario invalidaban su refresh token — seguía
    sirviendo para pedir access tokens nuevos hasta que expirara solo (hasta
    1 día). Estos tests verifican que, una vez blacklisteado, reconstruir
    el token (RefreshToken(str)) — lo que hace el backend al validarlo —
    lanza TokenError.
    """

    def setUp(self):
        self.superuser = User.objects.create_user(
            username='super1', email='super1@test.com', name='Super',
            role='superuser', password='x12345',
        )
        self.target_user = User.objects.create_user(
            username='cash1', email='cash1@test.com', name='Cajero',
            role='cashier', password='x12345',
        )

    def test_logout_blacklists_the_refresh_token_sent(self):
        refresh = RefreshToken.for_user(self.target_user)
        refresh_str = str(refresh)

        api = APIClient()
        api.force_authenticate(user=self.target_user)
        resp = api.post('/api/users/logout/', {'refresh': refresh_str}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)

        with self.assertRaises(TokenError):
            RefreshToken(refresh_str)

    def test_logout_without_refresh_in_body_does_not_fail(self):
        """El frontend actual todavía no manda `refresh` al hacer logout —
        el logout debe seguir funcionando (sin poder blacklistear nada) en
        vez de romperse, hasta que se actualice en una fase futura."""
        api = APIClient()
        api.force_authenticate(user=self.target_user)
        resp = api.post('/api/users/logout/', {}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)

    def test_deactivating_user_blacklists_their_outstanding_refresh_token(self):
        refresh = RefreshToken.for_user(self.target_user)
        refresh_str = str(refresh)

        # Confirma la premisa: recién emitido, el token todavía es válido.
        RefreshToken(refresh_str)

        api = APIClient()
        api.force_authenticate(user=self.superuser)
        resp = api.patch(f'/api/users/{self.target_user.id}/', {'state': False}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)

        with self.assertRaises(TokenError):
            RefreshToken(refresh_str)

    def test_reactivating_user_does_not_touch_tokens_issued_after(self):
        """No debe blacklistear nada si el cambio no es una desactivación
        (p. ej. editar el nombre, o reactivar a alguien ya activo)."""
        api = APIClient()
        api.force_authenticate(user=self.superuser)
        resp = api.patch(f'/api/users/{self.target_user.id}/', {'name': 'Cajero Editado'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)

        refresh = RefreshToken.for_user(self.target_user)
        RefreshToken(str(refresh))  # no debe lanzar TokenError
