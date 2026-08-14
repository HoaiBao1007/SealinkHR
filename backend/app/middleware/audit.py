"""Best-effort audit trail for authenticated state-changing API requests."""

from collections.abc import Awaitable, Callable

from fastapi import Request, Response

from app.core.auth import verify_token
from app.db.session import SessionLocal
from app.models.user import User
from app.services.audit_service import (
    bind_audit_request_context,
    record_audit,
    reset_audit_request_context,
)
from app.services.trusted_device_service import request_device, request_source_ip


MUTATING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


async def audit_mutating_request(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    """Record who changed which API resource without capturing sensitive bodies.

    Audit persistence is deliberately best-effort and runs after the business
    response.  An audit storage outage must never replace the real API result.
    Detailed domain events (attendance override, HR update, backup, ...) remain
    alongside this universal route-level trace.
    """
    source_ip = request_source_ip(request)
    authorization = request.headers.get("authorization", "")
    payload = None
    actor_for_context = None
    device_for_context = None
    if authorization.startswith("Bearer "):
        payload = verify_token(authorization.removeprefix("Bearer ").strip())
        context_user_id = payload.get("user_id") if payload else None
        if context_user_id:
            context_db = SessionLocal()
            try:
                actor_for_context = context_db.query(User).filter(User.id == context_user_id).first()
                if actor_for_context:
                    device_for_context = request_device(
                        context_db, request, user_id=actor_for_context.id
                    )
            finally:
                context_db.close()
    context_tokens = bind_audit_request_context(
        source_ip=source_ip,
        device_address=device_for_context.device_label if device_for_context else None,
    )
    try:
        response = await call_next(request)
    finally:
        reset_audit_request_context(context_tokens)
    if request.method not in MUTATING_METHODS:
        return response

    if not authorization.startswith("Bearer "):
        return response
    payload = payload or verify_token(authorization.removeprefix("Bearer ").strip())
    user_id = payload.get("user_id") if payload else None
    if not user_id:
        return response

    db = SessionLocal()
    try:
        actor = db.query(User).filter(User.id == user_id).first()
        if not actor:
            return response
        status_name = "SUCCESS" if response.status_code < 400 else "FAILED"
        device = request_device(db, request, user_id=actor.id)
        record_audit(
            db,
            actor=actor,
            action=f"HTTP_{request.method}",
            resource_type="API_MUTATION",
            resource_id=request.url.path,
            summary=f"{request.method} {request.url.path} → HTTP {response.status_code}",
            status=status_name,
            source_ip=source_ip,
            device_address=device.device_label if device else None,
        )
        db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()
    return response
