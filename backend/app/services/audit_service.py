import json
from contextvars import ContextVar, Token
from typing import Any

from sqlalchemy.orm import Session

from app.models.system_audit_event import SystemAuditEvent
from app.models.user import User


_audit_source_ip: ContextVar[str | None] = ContextVar("audit_source_ip", default=None)
_audit_device_address: ContextVar[str | None] = ContextVar("audit_device_address", default=None)


def bind_audit_request_context(
    *, source_ip: str | None, device_address: str | None
) -> tuple[Token, Token]:
    return _audit_source_ip.set(source_ip), _audit_device_address.set(device_address)


def reset_audit_request_context(tokens: tuple[Token, Token]) -> None:
    source_token, device_token = tokens
    _audit_source_ip.reset(source_token)
    _audit_device_address.reset(device_token)


def _json_text(value: Any | None) -> str | None:
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False, default=str, separators=(",", ":"))


def record_audit(
    db: Session,
    *,
    actor: User,
    action: str,
    resource_type: str,
    summary: str,
    resource_id: str | int | None = None,
    before: Any | None = None,
    after: Any | None = None,
    status: str = "SUCCESS",
    source_ip: str | None = None,
    device_address: str | None = None,
) -> SystemAuditEvent:
    """Stage an append-only event in the caller's current transaction."""
    if source_ip is None:
        source_ip = _audit_source_ip.get()
    if device_address is None:
        device_address = _audit_device_address.get()
    event = SystemAuditEvent(
        actor_user_id=actor.id,
        actor_username=actor.username,
        actor_role=actor.role,
        action=action,
        resource_type=resource_type,
        resource_id=str(resource_id) if resource_id is not None else None,
        status=status,
        summary=summary[:500],
        before_json=_json_text(before),
        after_json=_json_text(after),
        source_ip=source_ip,
        device_address=device_address,
    )
    db.add(event)
    return event
