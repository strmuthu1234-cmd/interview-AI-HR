from apps.accounts.models import AuditLog, User


def client_ip(request):
    if request is None:
        return None
    fwd = request.META.get("HTTP_X_FORWARDED_FOR")
    return (fwd.split(",")[0].strip() if fwd else request.META.get("REMOTE_ADDR")) or None


def log_action(request, action, entity=None, *, org=None, actor=None, metadata=None):
    """Append an audit record. `entity` is any model instance (or None)."""
    user = actor or (getattr(request, "user", None) if request is not None else None)
    actor_user = user if isinstance(user, User) else None
    is_candidate = bool(getattr(user, "is_candidate", False))
    organization = org or getattr(actor_user, "organization", None) or getattr(entity, "organization", None)
    return AuditLog.objects.create(
        organization=organization,
        actor=actor_user,
        actor_label="" if actor_user else ("candidate" if is_candidate else "system"),
        action=action,
        entity_type=entity.__class__.__name__ if entity is not None else "",
        entity_id=str(entity.pk) if entity is not None and entity.pk else "",
        metadata=metadata or {},
        ip_address=client_ip(request),
    )
