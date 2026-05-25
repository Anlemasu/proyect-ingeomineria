from .models import AuditLog


def get_client_ip(request) -> str:
    """Extrae la IP real del cliente considerando proxies."""
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
    log_user = user or (request.user if request.user.is_authenticated else None)
    """
    Registra una acción en el log de auditoría.

    Uso:
        log_action(request, 'create', 'Client', object_id=client.id, new_data={...})
        log_action(request, 'update', 'Trip', object_id=1, previous_data={...}, new_data={...})
        log_action(request, 'login', 'User', object_id=user.id)
    """
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