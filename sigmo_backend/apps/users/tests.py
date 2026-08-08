import threading

from django.conf import settings
from django.core.cache import cache
from django.db import connection
from django.test import TestCase, TransactionTestCase, override_settings
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError

from apps.audit.models import AuditLog
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


class DeactivatedUserAccessTokenRejectionTests(TestCase):
    """
    BUG 3 (diagnóstico de solo lectura): blacklistear el refresh token al
    desactivar a alguien (arriba) no afecta el access token que ya tenía en
    uso — ese seguía sirviendo hasta sus 8h de vida. Estos tests prueban
    que ActiveUserJWTAuthentication corta el acceso de inmediato, en la
    siguiente request, con un mensaje específico (no el genérico de token
    inválido/expirado).
    """

    def setUp(self):
        self.user = User.objects.create_user(
            username='cash_deact1', email='cash_deact1@test.com', name='Cajero',
            role='cashier', password='x12345',
        )

    def test_deactivated_user_gets_401_with_specific_message_on_protected_endpoint(self):
        access_token = str(RefreshToken.for_user(self.user).access_token)

        self.user.state = False
        self.user.save()

        api = APIClient()
        api.credentials(HTTP_AUTHORIZATION=f'Bearer {access_token}')
        resp = api.get('/api/clients/')

        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED, resp.data)
        self.assertIn('desactivada', str(resp.data.get('detail', resp.data)))

    def test_active_user_token_still_works(self):
        access_token = str(RefreshToken.for_user(self.user).access_token)

        api = APIClient()
        api.credentials(HTTP_AUTHORIZATION=f'Bearer {access_token}')
        resp = api.get('/api/clients/')

        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)


class PasswordChangeInvalidatesSessionsTests(TestCase):
    """
    8A.1 (diagnóstico de solo lectura): ni el cambio de contraseña propio
    (RF-06B) ni el reset por superusuario (RF-01) invalidaban las sesiones
    ya abiertas con la contraseña anterior — un refresh token emitido antes
    del cambio seguía sirviendo igual hasta expirar solo. Se reutiliza
    blacklist_all_outstanding_tokens, el mismo mecanismo ya usado al
    desactivar un usuario.
    """

    def setUp(self):
        self.superuser = User.objects.create_user(
            username='super_pwd1', email='super_pwd1@test.com', name='Super',
            role='superuser', password='x12345',
        )
        self.target_user = User.objects.create_user(
            username='cash_pwd1', email='cash_pwd1@test.com', name='Cajero',
            role='cashier', password='OldPass123',
        )

    def test_self_change_password_blacklists_previously_issued_refresh_token(self):
        refresh_str = str(RefreshToken.for_user(self.target_user))
        RefreshToken(refresh_str)  # confirma la premisa: arranca válido

        access_token = str(RefreshToken.for_user(self.target_user).access_token)
        api = APIClient()
        api.credentials(HTTP_AUTHORIZATION=f'Bearer {access_token}')
        resp = api.post('/api/users/change-password/', {
            'current_password': 'OldPass123',
            'new_password': 'NewPass456',
            'confirm_password': 'NewPass456',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)

        with self.assertRaises(TokenError):
            RefreshToken(refresh_str)

    def test_self_change_password_does_not_break_the_current_session(self):
        """
        La sesión que HIZO el cambio no debe quedar bloqueada por su propio
        cambio. Nota (8A.4): esto ya NO significa "el mismo access token
        sigue sirviendo" — desde 8A.4, ActiveUserJWTAuthentication rechaza
        cualquier token emitido antes de password_changed_at, incluido el
        que se acaba de usar para hacer el cambio. Lo que garantiza que la
        sesión no se corte a sí misma es que ChangePasswordView ahora
        entrega un token NUEVO en la respuesta (emitido después de fijar
        password_changed_at) — ver PasswordChangedAtRejectsOldTokensTests
        para la cobertura completa de ese mecanismo.
        """
        access_token = str(RefreshToken.for_user(self.target_user).access_token)
        api = APIClient()
        api.credentials(HTTP_AUTHORIZATION=f'Bearer {access_token}')
        resp = api.post('/api/users/change-password/', {
            'current_password': 'OldPass123',
            'new_password': 'NewPass456',
            'confirm_password': 'NewPass456',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)

        # Con el token NUEVO que la respuesta entrega, la sesión sigue
        # funcionando de inmediato.
        api.credentials(HTTP_AUTHORIZATION=f'Bearer {resp.data["access"]}')
        resp2 = api.get('/api/clients/')
        self.assertEqual(resp2.status_code, status.HTTP_200_OK, resp2.data)

    def test_admin_reset_blacklists_target_users_refresh_token(self):
        refresh_str = str(RefreshToken.for_user(self.target_user))

        api = APIClient()
        api.force_authenticate(user=self.superuser)
        resp = api.post(f'/api/users/{self.target_user.id}/reset-password/', {
            'new_password': 'AdminReset99',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)

        with self.assertRaises(TokenError):
            RefreshToken(refresh_str)


class DjangoPasswordValidatorsWiredTests(TestCase):
    """
    8A.2 (diagnóstico de solo lectura): AUTH_PASSWORD_VALIDATORS estaba
    configurado en settings.py pero ningún flujo (creación, cambio propio,
    reset por admin) lo invocaba de verdad — las reglas ahí declaradas no
    tenían ningún efecto real. 'Password1' pasa las reglas manuales (8+,
    mayúscula, dígito) pero está en la lista de contraseñas comunes de
    Django (CommonPasswordValidator) — confirmado contra
    common-passwords.txt.gz antes de escribir este test.
    """

    def setUp(self):
        self.superuser = User.objects.create_user(
            username='super_val1', email='super_val1@test.com', name='Super',
            role='superuser', password='x12345',
        )
        self.target_user = User.objects.create_user(
            username='cash_val1', email='cash_val1@test.com', name='Cajero',
            role='cashier', password='OldPass123',
        )

    def test_create_user_rejects_common_password(self):
        api = APIClient()
        api.force_authenticate(user=self.superuser)
        resp = api.post('/api/users/', {
            'name': 'Nuevo', 'email': 'nuevo1@test.com', 'username': 'nuevo_user1',
            'role': 'cashier', 'password': 'Password1',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST, resp.data)
        self.assertFalse(User.objects.filter(username='nuevo_user1').exists())

    def test_self_change_password_rejects_password_too_similar_to_username(self):
        access_token = str(RefreshToken.for_user(self.target_user).access_token)
        api = APIClient()
        api.credentials(HTTP_AUTHORIZATION=f'Bearer {access_token}')
        resp = api.post('/api/users/change-password/', {
            'current_password': 'OldPass123',
            'new_password': 'Cash_val1X9',  # muy similar al username 'cash_val1'
            'confirm_password': 'Cash_val1X9',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST, resp.data)

    def test_admin_reset_rejects_common_password(self):
        api = APIClient()
        api.force_authenticate(user=self.superuser)
        resp = api.post(f'/api/users/{self.target_user.id}/reset-password/', {
            'new_password': 'Password1',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST, resp.data)


class TokenRefreshEndpointTests(TestCase):
    """8A.3: antes de este fix no existía NINGÚN endpoint de refresh en
    todo el proyecto — el frontend no tenía nada que llamar para renovar
    el access token sin forzar un login completo. Se usa el
    TokenRefreshView estándar de simplejwt (ROTATE_REFRESH_TOKENS=True,
    así que la respuesta trae access Y refresh nuevos); como
    token_blacklist ya está instalado, un refresh token blacklisteado
    (por 8A.1, logout, o desactivación) se rechaza solo, sin código extra."""

    def setUp(self):
        self.user = User.objects.create_user(
            username='cash_refresh1', email='cash_refresh1@test.com', name='Cajero',
            role='cashier', password='x12345',
        )

    def test_valid_refresh_token_returns_new_access_and_refresh(self):
        refresh_str = str(RefreshToken.for_user(self.user))
        api = APIClient()
        resp = api.post('/api/users/token/refresh/', {'refresh': refresh_str}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        self.assertIn('access', resp.data)
        self.assertIn('refresh', resp.data)

    def test_blacklisted_refresh_token_is_rejected(self):
        refresh = RefreshToken.for_user(self.user)
        refresh_str = str(refresh)
        refresh.blacklist()

        api = APIClient()
        resp = api.post('/api/users/token/refresh/', {'refresh': refresh_str}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED, resp.data)


class PasswordChangedAtRejectsOldTokensTests(TestCase):
    """
    8A.4 (continuación de 8A.1): blacklistear el refresh token al cambiar
    contraseña no afecta un access token ya emitido, que seguía sirviendo
    hasta por 8h más aunque la contraseña hubiera cambiado. Se agrega
    User.password_changed_at + el chequeo de `iat` en
    ActiveUserJWTAuthentication (misma clase de la Fase 7).
    """

    def setUp(self):
        self.superuser = User.objects.create_user(
            username='super_pca1', email='super_pca1@test.com', name='Super',
            role='superuser', password='x12345',
        )
        self.target_user = User.objects.create_user(
            username='cash_pca1', email='cash_pca1@test.com', name='Cajero',
            role='cashier', password='OldPass123',
        )

    def test_self_change_password_rejects_the_access_token_issued_before_the_change(self):
        old_access_token = str(RefreshToken.for_user(self.target_user).access_token)

        api = APIClient()
        api.credentials(HTTP_AUTHORIZATION=f'Bearer {old_access_token}')
        resp = api.post('/api/users/change-password/', {
            'current_password': 'OldPass123',
            'new_password': 'NewPass456',
            'confirm_password': 'NewPass456',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)

        # El MISMO token que se acaba de usar para cambiar la contraseña
        # ahora es "anterior" al cambio — debe rechazarse en la siguiente
        # request, con el mensaje específico (no el de token inválido).
        api_old = APIClient()
        api_old.credentials(HTTP_AUTHORIZATION=f'Bearer {old_access_token}')
        resp2 = api_old.get('/api/clients/')
        self.assertEqual(resp2.status_code, status.HTTP_401_UNAUTHORIZED, resp2.data)
        self.assertIn('actualizada', str(resp2.data.get('detail', resp2.data)))

    def test_self_change_password_does_not_lock_out_its_own_session(self):
        """
        REQUISITO 4: el usuario que cambia su propia contraseña debe poder
        seguir usando la app de inmediato — con el token NUEVO que la
        respuesta de ChangePasswordView ahora entrega, no con el viejo.
        """
        old_access_token = str(RefreshToken.for_user(self.target_user).access_token)

        api = APIClient()
        api.credentials(HTTP_AUTHORIZATION=f'Bearer {old_access_token}')
        resp = api.post('/api/users/change-password/', {
            'current_password': 'OldPass123',
            'new_password': 'NewPass456',
            'confirm_password': 'NewPass456',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        self.assertIn('access', resp.data)
        self.assertIn('refresh', resp.data)

        new_access_token = resp.data['access']
        api_new = APIClient()
        api_new.credentials(HTTP_AUTHORIZATION=f'Bearer {new_access_token}')
        resp2 = api_new.get('/api/clients/')
        self.assertEqual(
            resp2.status_code, status.HTTP_200_OK,
            f'el usuario no debe quedar bloqueado por su propio cambio de contraseña: {resp2.data}',
        )

    def test_admin_reset_rejects_target_users_access_token_issued_before_the_reset(self):
        old_access_token = str(RefreshToken.for_user(self.target_user).access_token)

        api = APIClient()
        api.force_authenticate(user=self.superuser)
        resp = api.post(f'/api/users/{self.target_user.id}/reset-password/', {
            'new_password': 'AdminReset99',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)

        api_target = APIClient()
        api_target.credentials(HTTP_AUTHORIZATION=f'Bearer {old_access_token}')
        resp2 = api_target.get('/api/clients/')
        self.assertEqual(resp2.status_code, status.HTTP_401_UNAUTHORIZED, resp2.data)
        self.assertIn('actualizada', str(resp2.data.get('detail', resp2.data)))

    def test_user_who_never_changed_password_is_unaffected(self):
        """password_changed_at=NULL (usuario que nunca ha cambiado su
        contraseña desde que existe este campo) no debe rechazar nada."""
        access_token = str(RefreshToken.for_user(self.target_user).access_token)
        self.assertIsNone(self.target_user.password_changed_at)

        api = APIClient()
        api.credentials(HTTP_AUTHORIZATION=f'Bearer {access_token}')
        resp = api.get('/api/clients/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)


class LoginLockoutAtomicCounterTests(TransactionTestCase):
    """
    9.5 — antes, el conteo de intentos fallidos usaba cache.get() seguido
    de un cache.set() separado ("+1"), no atómico: bajo intentos fallidos
    casi simultáneos para el mismo username, dos requests podían leer el
    mismo valor "viejo" y las dos escribir "+1" sobre él, perdiendo
    incrementos (el conteo real quedaba por debajo del real, permitiendo
    más intentos de los configurados). Ahora usa cache.add() + cache.incr()
    (atómico incluso con LocMemCache dentro de un mismo proceso).

    TransactionTestCase, mismo motivo que los demás tests de concurrencia
    del proyecto: cada hilo necesita su propia conexión de BD (para
    authenticate(), que sí golpea la BD) con commits reales; TestCase
    envuelve todo en una única transacción no confirmada.

    LOGIN_MAX_ATTEMPTS se sube por encima del número de hilos para que
    ningún intento dispare el bloqueo a mitad de la carrera — lo que se
    está probando es la exactitud del conteo, no el bloqueo en sí (eso ya
    lo cubre el resto de LoginView).
    """

    def setUp(self):
        # Username exclusivo de este test: no puede haber una clave de
        # cache previa con este nombre, así que no hace falta limpiarla.
        self.username = 'lockout_race_user_95'
        User.objects.create_user(
            username=self.username, email='lockout95@test.com', name='Lockout Race',
            role='cashier', password='x12345',
        )

    def _failed_login(self):
        api = APIClient()
        try:
            return api.post('/api/users/login/', {
                'username': self.username, 'password': 'contrasena-incorrecta',
            }, format='json')
        finally:
            connection.close()

    @override_settings(LOGIN_MAX_ATTEMPTS=1000)
    def test_concurrent_failed_attempts_do_not_lose_increments(self):
        n_threads = 15
        results = []
        start_barrier = threading.Barrier(n_threads)

        def worker():
            start_barrier.wait()
            results.append(self._failed_login())

        threads = [threading.Thread(target=worker) for _ in range(n_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=15)

        self.assertEqual(len(results), n_threads)
        for r in results:
            self.assertEqual(r.status_code, status.HTTP_401_UNAUTHORIZED, r.data)

        self.assertEqual(
            cache.get(f'attempts_{self.username}'), n_threads,
            'el conteo final debe ser exacto: un incremento por cada intento fallido, sin pérdidas',
        )


class LoginFailureAuditLogTests(TestCase):
    """
    9.6 — los intentos fallidos y el bloqueo temporal por fuerza bruta
    (RF-03) solo quedaban en cache (efímero: se pierde al reiniciar o
    expirar) — ahora también dejan su rastro en el AuditLog persistente,
    para poder investigar después un patrón de fuerza bruta distribuido en
    el tiempo.
    """

    def setUp(self):
        self.username = 'audit_login_user_96'
        User.objects.create_user(
            username=self.username, email='audit96@test.com', name='Audit Login',
            role='cashier', password='x12345',
        )
        # LocMemCache no se limpia entre tests de una misma clase (a
        # diferencia de la BD, que TestCase envuelve en una transacción por
        # test) — sin esto, el bloqueo que deja test_account_lockout_...
        # se filtraría al resto de tests de esta clase.
        cache.delete(f'attempts_{self.username}')
        cache.delete(f'lockout_{self.username}')

    def test_failed_attempt_is_recorded_in_audit_log(self):
        api = APIClient()
        resp = api.post('/api/users/login/', {
            'username': self.username, 'password': 'contrasena-incorrecta',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED, resp.data)

        entry = AuditLog.objects.filter(action='login_failed', model_name='User').latest('timestamp')
        self.assertEqual(entry.new_data.get('username'), self.username)
        self.assertIsNone(entry.user, 'un intento fallido no tiene un usuario autenticado que registrar')
        self.assertNotIn(
            'contrasena-incorrecta', str(entry.new_data),
            'nunca debe quedar la contraseña ingresada en el AuditLog',
        )

    def test_account_lockout_is_recorded_in_audit_log(self):
        api = APIClient()
        for _ in range(settings.LOGIN_MAX_ATTEMPTS):
            api.post('/api/users/login/', {
                'username': self.username, 'password': 'contrasena-incorrecta',
            }, format='json')

        lockout_entry = AuditLog.objects.filter(
            action='account_locked', model_name='User'
        ).latest('timestamp')
        self.assertEqual(lockout_entry.new_data.get('username'), self.username)

        failed_count = AuditLog.objects.filter(
            action='login_failed', model_name='User', new_data__username=self.username,
        ).count()
        self.assertEqual(failed_count, settings.LOGIN_MAX_ATTEMPTS)
