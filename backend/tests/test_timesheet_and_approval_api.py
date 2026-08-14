from datetime import date
from unittest.mock import patch

from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.models.attendance_daily import AttendanceDaily
from app.models.attendance_log import AttendanceLog
from app.models.attendance_override_audit import AttendanceOverrideAudit
from app.models.timesheet_entry import TimesheetEntry
from app.models.timesheet_period import TimesheetPeriod
from app.models.upload_batch import UploadBatch
from app.models.user import User


def test_get_timesheets_by_period(client, seed_timesheet_data):
    period_start = seed_timesheet_data["period_start"].isoformat()
    period_end = seed_timesheet_data["period_end"].isoformat()

    response = client.get("/api/timesheets", params={"period_start": period_start, "period_end": period_end})

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["approval_status"] == "draft"
    assert payload[0]["total_work_days"] == 20.0


def test_timesheet_approval_flow(client, seed_timesheet_data, seed_basic_employees, db_session: Session):
    timesheet_id = seed_timesheet_data["timesheet"].id
    approver_id = seed_basic_employees["approver"].id

    invalid_response = client.post(
        f"/api/timesheets/{timesheet_id}/approval",
        json={"action": "hold", "approved_by_user_id": approver_id},
    )
    assert invalid_response.status_code == 400

    approve_response = client.post(
        f"/api/timesheets/{timesheet_id}/approval",
        json={"action": "approve", "approved_by_user_id": approver_id},
    )
    assert approve_response.status_code == 200
    payload = approve_response.json()
    assert payload["approval_status"] == "approved"
    assert payload["approved_by_user_id"] == approver_id
    assert payload["approved_at"] is not None


def test_get_timesheets_returns_503_when_database_unavailable(client):
    with patch(
        "app.api.timesheet.Session.query",
        side_effect=OperationalError("SELECT 1", {}, Exception("db down")),
    ):
        response = client.get(
            "/api/timesheets",
            params={"period_start": "2026-04-23", "period_end": "2026-05-22"},
        )

    assert response.status_code == 503
    assert response.json()["detail"] == "database is unavailable"


def test_delete_timesheet_period_clears_all_generated_attendance_data(
    client,
    seed_timesheet_data,
    seed_basic_employees,
    db_session: Session,
):
    worker = seed_basic_employees["worker"]
    approver = seed_basic_employees["approver"]
    timesheet = seed_timesheet_data["timesheet"]
    period_start = seed_timesheet_data["period_start"]
    period_end = seed_timesheet_data["period_end"]
    work_day = date(2026, 4, 24)

    uploader = User(username="batch_uploader", password_hash="hash", role="ADMIN")
    db_session.add(uploader)
    db_session.flush()
    batch = UploadBatch(
        uploaded_by_user_id=uploader.id,
        source_type="checkin_profile",
        file_name="old_timesheet.xlsx",
        file_hash="old-batch",
        period_start=period_start,
        period_end=period_end,
        status="completed",
    )
    db_session.add(batch)
    db_session.flush()
    db_session.add_all(
        [
            TimesheetPeriod(period_start=period_start, period_end=period_end, is_locked=False),
            TimesheetEntry(
                timesheet_id=timesheet.id,
                employee_id=worker.id,
                work_date=work_day,
                original_symbol="X",
                final_symbol="CT",
                is_overridden=True,
                override_reason="Old override",
            ),
            AttendanceDaily(
                employee_id=worker.id,
                work_date=work_day,
                # Deliberately incorrect metadata: delete must still clear by date.
                period_start=date(2026, 1, 23),
                period_end=date(2026, 2, 22),
                attendance_symbol="CT",
                source_priority=1,
                generated_from_batch_id=batch.id,
            ),
            AttendanceLog(
                upload_batch_id=batch.id,
                employee_id=worker.id,
                work_date=work_day,
                raw_time_values="08:30,17:30",
            ),
            AttendanceOverrideAudit(
                employee_id=worker.id,
                work_date=work_day,
                old_symbol="X",
                new_symbol="CT",
                reason="Old override",
                changed_by_user_id=approver.id,
            ),
        ]
    )
    db_session.commit()

    response = client.delete(
        "/api/timesheets/period",
        params={"period_start": period_start.isoformat(), "period_end": period_end.isoformat()},
    )

    assert response.status_code == 200
    assert db_session.query(TimesheetEntry).count() == 0
    assert db_session.query(AttendanceDaily).count() == 0
    assert db_session.query(AttendanceLog).count() == 0
    assert db_session.query(AttendanceOverrideAudit).count() == 0
    assert db_session.query(UploadBatch).count() == 0
    assert db_session.query(TimesheetPeriod).count() == 0
