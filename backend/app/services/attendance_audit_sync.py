"""Keep legacy attendance override rows visible in the system-wide IT audit."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.models.attendance_override_audit import AttendanceOverrideAudit
from app.models.employee import Employee
from app.models.system_audit_event import SystemAuditEvent
from app.models.user import User
from app.services.audit_service import record_audit


def attendance_override_summary(audit: AttendanceOverrideAudit) -> str:
    return f"Chỉnh công {audit.work_date.isoformat()} của nhân viên #{audit.employee_id}"


def _timestamp_key(value: datetime | None) -> str:
    if value is None:
        return ""
    return value.replace(tzinfo=None).isoformat(timespec="seconds")


def sync_attendance_override_audit_events(db: Session) -> dict[str, int]:
    """Append missing legacy attendance overrides to ``system_audit_events``.

    Attendance overrides existed before the system-wide audit trail.  The source
    ledger remains immutable; this function only appends missing mirror events.
    It also recognises the earlier event format so it does not duplicate rows
    that had already been mirrored before the dedicated audit ID was added.
    """

    override_rows = (
        db.query(AttendanceOverrideAudit, User)
        .join(Employee, Employee.id == AttendanceOverrideAudit.changed_by_user_id)
        .join(User, User.id == Employee.user_id)
        .order_by(AttendanceOverrideAudit.id.asc())
        .all()
    )
    audit_events = (
        db.query(SystemAuditEvent)
        .filter(SystemAuditEvent.action == "ATTENDANCE_OVERRIDE")
        .all()
    )
    modern_events_by_override_id = {
        str(event.resource_id): event
        for event in audit_events
        if event.resource_type == "ATTENDANCE_OVERRIDE" and event.resource_id is not None
    }
    legacy_events_by_key = {
        (event.actor_user_id, _timestamp_key(event.occurred_at), event.summary): event
        for event in audit_events
    }

    created = 0
    already_synced = 0
    timestamps_aligned = 0
    for override, actor in override_rows:
        summary = attendance_override_summary(override)
        legacy_key = (actor.id, _timestamp_key(override.changed_at), summary)
        existing_modern_event = modern_events_by_override_id.get(str(override.id))
        if existing_modern_event:
            if _timestamp_key(existing_modern_event.occurred_at) != _timestamp_key(override.changed_at):
                existing_modern_event.occurred_at = override.changed_at
                timestamps_aligned += 1
            already_synced += 1
            continue
        legacy_event = legacy_events_by_key.get(legacy_key)
        if legacy_event:
            # Releases created before the dedicated audit ID used the edited
            # timesheet-entry ID as their resource.  Keep the same event, but
            # link it to the immutable attendance-audit row for consistency.
            legacy_event.resource_type = "ATTENDANCE_OVERRIDE"
            legacy_event.resource_id = str(override.id)
            already_synced += 1
            continue

        event = record_audit(
            db,
            actor=actor,
            action="ATTENDANCE_OVERRIDE",
            resource_type="ATTENDANCE_OVERRIDE",
            resource_id=override.id,
            summary=summary,
            before={
                "symbol": override.old_symbol,
                "check_in": override.old_check_in,
                "check_out": override.old_check_out,
            },
            after={
                "symbol": override.new_symbol,
                "check_in": override.new_check_in,
                "check_out": override.new_check_out,
                "reason": override.reason,
                "override_audit_id": override.id,
            },
        )
        # Historical rows retain the original action time in the IT timeline.
        event.occurred_at = override.changed_at
        created += 1

    return {
        "created": created,
        "already_synced": already_synced,
        "timestamps_aligned": timestamps_aligned,
    }
