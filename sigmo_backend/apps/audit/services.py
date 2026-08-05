from .models import AuditLog


def get_client_ip(request) -> str | None:
    """Extrae la IP real del cliente considerando proxies."""
    if request is None:
        return None
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        return x_forwarded_for.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', '')


def log_action(
    request,
    action: str,
    model_name: str,
    object_id: int | None = None,
    previous_data: dict | None = None,
    new_data: dict | None = None,
    justification: str | None = None,
    user=None,
):
    """
    Registra una acción en el log de auditoría.

    `request` es opcional: los procesos sin request HTTP (comando
    `auto_close_cash`, `recover_missed_closings`) lo omiten y en su lugar
    pasan `user=None` (queda como "acción del sistema") y una
    `justification` explicando el origen automático. Cuando hay `request`,
    el usuario y la IP se derivan de él igual que antes.

    Uso:
        log_action(request, 'create', 'Client', object_id=client.id, new_data={...})
        log_action(request, 'update', 'Trip', object_id=1, previous_data={...}, new_data={...})
        log_action(request, 'login', 'User', object_id=user.id)
        log_action(None, 'create', 'DailySummary', object_id=s.id, user=None, justification='Cierre automático')
    """
    if user is not None:
        log_user = user
    elif request is not None and request.user.is_authenticated:
        log_user = request.user
    else:
        log_user = None

    AuditLog.objects.create(
        user=log_user,
        action=action,
        model_name=model_name,
        object_id=object_id,
        previous_data=previous_data,
        new_data=new_data,
        ip_address=get_client_ip(request),
        justification=justification,
    )