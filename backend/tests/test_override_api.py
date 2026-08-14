from datetime import date
from unittest.mock import patch

from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.models.attendance_daily import AttendanceDaily
from app.models.attendance_override_audit import AttendanceOverrideAudit
from app.models.timesheet_entry import TimesheetEntry
from app.models.timesheet_period import TimesheetPeriod


def test_override_attendance_updates_and_audit(client, seed_timesheet_data, seed_basic_employees, db_session: Session):
    worker = seed_basic_employees["worker"]
    approver = seed_basic_employees["approver"]
    timesheet = seed_timesheet_data["timesheet"]
    work_day = date(2026, 4, 24)

    entry = TimesheetEntry(
        timesheet_id=timesheet.id,
        employee_id=worker.id,
        work_date=work_day,
        original_symbol="X",
        final_symbol="X",
        check_in_time="08:30",
        check_out_time="17:45",
        late_minutes=0,
        early_minutes=0,
        is_overridden=False,
    )
    daily = AttendanceDaily(
        employee_id=worker.id,
        work_date=work_day,
        period_start=seed_timesheet_data["period_start"],
        period_end=seed_timesheet_data["period_end"],
        check_in_time="08:30",
        check_out_time="17:45",
        late_minutes=0,
        early_minutes=0,
        attendance_symbol="X",
        abnormal_level=None,
        source_priority=1,
    )
    db_session.add_all([entry, daily])
    db_session.commit()

    payload = {
        "employee_id": worker.id,
        "work_date": "2026-04-24",
        "new_symbol": "CT",
        "reason": "Dieu chinh cong tac",
        "changed_by_user_id": approver.id,
        "new_check_in": "08:00",
        "new_check_out": "18:00",
    }
    response = client.post("/api/attendance/override", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["old_symbol"] == "X"
    assert body["new_symbol"] == "CT"

    updated_entry = db_session.query(TimesheetEntry).filter(TimesheetEntry.employee_id == worker.id).first()
    assert updated_entry is not None
    assert updated_entry.final_symbol == "CT"
    assert updated_entry.is_overridden is True
    assert updated_entry.override_reason == "Dieu chinh cong tac"

    updated_daily = db_session.query(AttendanceDaily).filter(AttendanceDaily.employee_id == worker.id).first()
    assert updated_daily is not None
    assert updated_daily.attendance_symbol == "CT"
    assert updated_daily.check_in_time == "08:00"

    audits = db_session.query(AttendanceOverrideAudit).all()
    assert len(audits) == 1
    assert audits[0].reason == "Dieu chinh cong tac"


def test_override_attendance_requires_authenticated_actor_profile(client):
    payload = {
        "employee_id": 1,
        "work_date": "2026-04-24",
        "new_symbol": "CT",
        "reason": "Dieu chinh",
        "changed_by_user_id": 999,
    }
    response = client.post("/api/attendance/override", json=payload)
    # The client-provided actor identifier is ignored; this request reaches the
    # business validation and fails only because no timesheet entry exists.
    assert response.status_code == 404
    assert response.json()["detail"] == "timesheet entry not found for employee/work_date"


def test_locked_timesheet_requires_explicit_override_confirmation(
    client,
    seed_timesheet_data,
    seed_basic_employees,
    db_session: Session,
):
    worker = seed_basic_employees["worker"]
    timesheet = seed_timesheet_data["timesheet"]
    work_day = date(2026, 4, 24)
    db_session.add_all(
        [
            TimesheetEntry(
                timesheet_id=timesheet.id,
                employee_id=worker.id,
                work_date=work_day,
                original_symbol="X",
                final_symbol="X",
                is_overridden=False,
            ),
            TimesheetPeriod(
                period_start=seed_timesheet_data["period_start"],
                period_end=seed_timesheet_data["period_end"],
                is_locked=True,
            ),
        ]
    )
    db_session.commit()

    payload = {
        "employee_id": worker.id,
        "work_date": work_day.isoformat(),
        "new_symbol": "CT",
        "reason": "Điều chỉnh công tác",
    }
    blocked = client.post("/api/attendance/override", json=payload)
    assert blocked.status_code == 403
    assert db_session.query(AttendanceOverrideAudit).count() == 0

    confirmed = client.post("/api/attendance/override", json={**payload, "override_lock": True})
    assert confirmed.status_code == 200
    assert db_session.query(AttendanceOverrideAudit).count() == 1


def test_override_history_keeps_legacy_rows_without_joined_employee(client, db_session: Session):
    db_session.add(
        AttendanceOverrideAudit(
            employee_id=999,
            work_date=date(2026, 4, 24),
            old_symbol="X",
            new_symbol="CT",
            reason="Legacy audit row",
            changed_by_user_id=998,
        )
    )
    db_session.commit()

    response = client.get(
        "/api/attendance/override/history",
        params={"period_start": "2026-04-23", "period_end": "2026-05-22"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["employee_name"] == "Nhân sự #999"
    assert payload[0]["changed_by_name"] == "Tài khoản audit #998"


def test_get_override_history_returns_503_when_database_unavailable(client):
    with patch(
        "app.api.override.Session.query",
        side_effect=OperationalError("SELECT 1", {}, Exception("db down")),
    ):
        response = client.get(
            "/api/attendance/override/history",
            params={"period_start": "2026-04-23", "period_end": "2026-05-22"},
        )

    assert response.status_code == 503
    assert response.json()["detail"] == "database is unavailable"
