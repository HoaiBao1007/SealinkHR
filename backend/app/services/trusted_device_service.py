from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timezone

from fastapi import Request
from sqlalchemy.orm import Session

from app.models.trusted_device import TrustedDevice


TRUSTED_DEVICE_COOKIE = "sealink_it_trusted_device"


def hash_device_credential(raw_credential: str) -> str:
    return hashlib.sha256(raw_credential.encode("utf-8")).hexdigest()


def request_source_ip(request: Request) -> str | None:
    # Do not trust X-Forwarded-For unless a trusted reverse proxy is configured.
    return request.client.host if request.client else None


def active_device_for_credential(
    db: Session,
    *,
    user_id: int,
    raw_credential: str | None,
) -> TrustedDevice | None:
    if not raw_credential:
        return None
    candidate_hash = hash_device_credential(raw_credential)
    devices = (
        db.query(TrustedDevice)
        .filter(TrustedDevice.user_id == user_id, TrustedDevice.is_active.is_(True))
        .all()
    )
    for device in devices:
        if device.credential_hash and hmac.compare_digest(device.credential_hash, candidate_hash):
            return device
    return None


def enroll_pending_device(
    db: Session,
    *,
    user_id: int,
    source_ip: str | None,
    require_explicit_enrollment_ip: bool = False,
) -> tuple[TrustedDevice, str] | None:
    pending_query = (
        db.query(TrustedDevice)
        .filter(
            TrustedDevice.user_id == user_id,
            TrustedDevice.is_active.is_(False),
            TrustedDevice.credential_hash.is_(None),
        )
    )
    if require_explicit_enrollment_ip:
        if not source_ip:
            return None
        pending_query = pending_query.filter(TrustedDevice.enrollment_ip == source_ip)
    pending = pending_query.order_by(TrustedDevice.id.asc()).first()
    if not pending:
        return None
    if pending.enrollment_ip and pending.enrollment_ip != source_ip:
        return None

    raw_credential = secrets.token_urlsafe(48)
    now = datetime.now(timezone.utc)
    pending.credential_hash = hash_device_credential(raw_credential)
    pending.is_active = True
    pending.enrolled_at = now
    pending.last_used_at = now
    return pending, raw_credential


def recover_active_device_from_enrollment_ip(
    db: Session,
    *,
    user_id: int,
    source_ip: str | None,
) -> tuple[TrustedDevice, str] | None:
    """Rotate the browser credential for an enrolled device on its known IP.

    A normal web application cannot read the physical MAC address of a remote
    browser.  The MAC-like value stored in ``device_label`` is therefore an
    administrator-facing label, while the HttpOnly cookie is the real browser
    credential.  Private browsing or clearing cookies removes that credential.
    Recovery is deliberately limited to exactly one active device whose
    enrollment IP matches the current request.
    """

    if not source_ip:
        return None

    matching_devices = (
        db.query(TrustedDevice)
        .filter(
            TrustedDevice.user_id == user_id,
            TrustedDevice.is_active.is_(True),
            TrustedDevice.enrollment_ip == source_ip,
        )
        .order_by(TrustedDevice.id.asc())
        .all()
    )
    if len(matching_devices) != 1:
        return None

    device = matching_devices[0]
    raw_credential = secrets.token_urlsafe(48)
    device.credential_hash = hash_device_credential(raw_credential)
    device.last_used_at = datetime.now(timezone.utc)
    return device, raw_credential


def request_device(
    db: Session,
    request: Request,
    *,
    user_id: int,
) -> TrustedDevice | None:
    return active_device_for_credential(
        db,
        user_id=user_id,
        raw_credential=request.cookies.get(TRUSTED_DEVICE_COOKIE),
    )
