import logging

from core.context import request_id_var
from core.masking import redact

from .models import AuditEvent

logger = logging.getLogger("audit")


def client_ip(request) -> str | None:
    if request is None:
        return None
    # Atrás do proxy confiável, o primeiro IP do X-Forwarded-For é o cliente.
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    return (forwarded.split(",")[0].strip() if forwarded else request.META.get("REMOTE_ADDR")) or None


def record(action: str, *, request=None, actor=None, organization=None, target=None, **metadata) -> AuditEvent:
    if actor is None and request is not None and getattr(request, "user", None) and request.user.is_authenticated:
        actor = request.user
    if organization is None and request is not None:
        organization = getattr(request, "organization", None)
    event = AuditEvent.objects.create(
        action=action,
        actor=actor,
        organization=organization,
        target_type=target.__class__.__name__ if target is not None else "",
        target_id=str(getattr(target, "public_id", getattr(target, "pk", ""))) if target is not None else "",
        ip=client_ip(request),
        user_agent=(request.META.get("HTTP_USER_AGENT", "")[:255] if request is not None else ""),
        request_id=request_id_var.get(),
        metadata=redact(metadata),
    )
    logger.info("audit %s", action, extra={"data": {"action": action, "target": event.target_id}})
    return event
