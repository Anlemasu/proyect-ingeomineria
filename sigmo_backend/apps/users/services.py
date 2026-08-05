from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken


def blacklist_all_outstanding_tokens(user) -> int:
    """
    BUG 3 — invalida de una vez todos los refresh token vigentes de `user`.

    Se usa cuando un superusuario desactiva una cuenta (STATE_USER=false):
    sin esto, el usuario desactivado podía seguir usando su refresh token
    para obtener nuevos access token hasta que ese refresh expirara (hasta
    1 día después), aunque ya no pudiera iniciar sesión de nuevo.

    `OutstandingToken` solo existe con `user` poblado para los tokens
    emitidos DESPUÉS de instalar 'rest_framework_simplejwt.token_blacklist'
    en INSTALLED_APPS (lo registra automáticamente `RefreshToken.for_user()`
    de la librería) — tokens emitidos antes de ese cambio no quedan
    rastreados y seguirán siendo válidos hasta expirar por su cuenta.

    Devuelve cuántos tokens se blacklistearon en esta llamada (para dejarlo
    en el AuditLog).
    """
    already_blacklisted_ids = BlacklistedToken.objects.values_list('token_id', flat=True)
    pending = OutstandingToken.objects.filter(user=user).exclude(id__in=already_blacklisted_ids)

    count = 0
    for token in pending:
        BlacklistedToken.objects.get_or_create(token=token)
        count += 1
    return count
