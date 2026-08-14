from datetime import date, datetime, timezone

from app.models.attendance_override_audit import AttendanceOverrideAudit
from app.models.employee import Employee
from app.models.system_audit_event import SystemAuditEvent
from app.models.user import User
from app.services.attendance_audit_sync import sync_attendance_override_audit_events


def test_historical_attendance_override_is_mirrored_once_to_system_audit(db_session):
    actor = User(username="audit.actor", password_hash="hash", role="IT_ADMIN")
    db_session.add(actor)
    db_session.flush()
    employee = Employee(machine_employee_id="AUD-01", full_name="Nhân viên Audit", user_id=actor.id)
    db_session.add(employee)
    db_session.flush()
    override = AttendanceOverrideAudit(
        employee_id=employee.id,
        work_date=date(2026, 7, 10),
        old_symbol="V",
        new_symbol="X",
        old_check_in=None,
        new_check_in="08:00",
        old_check_out=None,
        new_check_out="17:30",
        reason="Bổ sung công",
        changed_by_user_id=employee.id,
        changed_at=datetime(2026, 7, 10, 8, 30, tzinfo=timezone.utc),
    )
    db_session.add(override)
    db_session.commit()

    first_sync = sync_attendance_override_audit_events(db_session)
    db_session.commit()
    assert first_sync == {"created": 1, "already_synced": 0, "timestamps_aligned": 0}
    event = db_session.query(SystemAuditEvent).one()
    assert event.action == "ATTENDANCE_OVERRIDE"
    assert event.resource_type == "ATTENDANCE_OVERRIDE"
    assert event.resource_id == str(override.id)
    assert "2026-07-10" in event.summary
    assert event.occurred_at == override.changed_at

    second_sync = sync_attendance_override_audit_events(db_session)
    assert second_sync == {"created": 0, "already_synced": 1, "timestamps_aligned": 0}
