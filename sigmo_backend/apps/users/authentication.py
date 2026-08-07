from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import AuthenticationFailed


class ActiveUserJWTAuthentication(JWTAuthentication):
    """
    BUG 3 (diagnóstico de solo lectura) — JWTAuthentication.get_user() ya
    intenta rechazar usuarios inactivos vía `user.is_active`, pero User
    (AbstractBaseUser sin PermissionsMixin) nunca define ese atributo:
    hereda el valor fijo `is_active = True` de AbstractBaseUser, así que ese
    chequeo nunca rechaza nada en este proyecto. El campo real de
    "activo/inactivo" es `User.state`.

    Esta clase reutiliza toda la lógica de JWTAuthentication (validación de
    firma/expiración del token, etc.) y solo añade la verificación de
    `state` DESPUÉS de resolver el usuario, en CADA request autenticado —
    no solo en /login/ — para que desactivar a alguien (UserDetailView.patch)
    también le corte de inmediato el acceso con su access token todavía
    vigente. Antes, desactivar solo invalidaba el refresh token
    (blacklist_all_outstanding_tokens); el access token seguía sirviendo
    hasta sus 8h de vida (ACCESS_TOKEN_LIFETIME). Complementa esa
    protección, no la reemplaza.

    Decisión de producto: verificar `state` en cada request, aceptando el
    costo de una consulta extra por request — el volumen del sistema es
    bajo (hasta 200 viajes diarios, máx. 10 usuarios concurrentes).

    8A.4 — el mismo hueco existía para el cambio de contraseña: blacklistear
    el refresh token (8A.1) no afecta un access token ya emitido, que sigue
    sirviendo hasta por 8h aunque la contraseña haya cambiado (ej. porque
    se sospechaba que ese mismo token estaba comprometido). Se añade un
    segundo chequeo, en el mismo lugar: si el token fue emitido (`iat`)
    ANTES del último cambio de contraseña (`User.password_changed_at`), se
    rechaza igual que un usuario desactivado.
    """

    def get_user(self, validated_token):
        user = super().get_user(validated_token)
        if not user.state:
            raise AuthenticationFailed(
                'Tu cuenta ha sido desactivada. Contacta al administrador.',
                code='user_deactivated',
            )

        if user.password_changed_at is not None:
            # `iat` es NumericDate (segundos enteros, RFC 7519) — comparar
            # con la marca completa (con microsegundos) de
            # password_changed_at rechazaría por error un token recién
            # emitido EN EL MISMO segundo del cambio (ej. el token nuevo
            # que ChangePasswordView emite para que la propia sesión que
            # cambió su contraseña no se corte a sí misma). Se trunca
            # password_changed_at al segundo (piso) antes de comparar, para
            # que un token con el mismo `iat` en segundos nunca se
            # considere "anterior" al cambio.
            changed_at_ts = int(user.password_changed_at.timestamp())
            if validated_token['iat'] < changed_at_ts:
                raise AuthenticationFailed(
                    'Tu sesión ya no es válida porque tu contraseña fue '
                    'actualizada. Inicia sesión nuevamente.',
                    code='password_changed',
                )

        return user
