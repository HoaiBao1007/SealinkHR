from datetime import date

from sqlalchemy.orm import Session

from app.models.attendance_daily import AttendanceDaily
from app.models.off_request import OffRequest
from app.models.timesheet_entry import TimesheetEntry


def test_policy_summary(client, seed_basic_employees, db_session: Session):
    worker = seed_basic_employees["worker"]

    db_session.add_all(
        [
            OffRequest(
                employee_id=worker.id,
                request_type="paid_leave",
                start_date=date(2026, 5, 1),
                end_date=date(2026, 5, 1),
                total_days=1,
                reason="Phep nam",
                status="approved",
            ),
            OffRequest(
                employee_id=worker.id,
                request_type="unpaid_leave",
                start_date=date(2026, 5, 2),
                end_date=date(2026, 5, 2),
                total_days=0.5,
                reason="Viec rieng",
                status="approved",
            ),
        ]
    )
    db_session.commit()

    response = client.get(
        "/api/timesheets/policy-summary",
        params={"period_start": "2026-04-23", "period_end": "2026-05-22"},
    )

    assert response.status_code == 200
    rows = response.json()
    worker_row = next((r for r in rows if r["employee_id"] == worker.id), None)
    assert worker_row is not None
    assert worker_row["paid_leave_days"] == 1.0
    assert worker_row["unpaid_leave_days"] == 0.5


def test_conflict_audit_priority_override_abnormal_checkin(client, seed_timesheet_data, seed_basic_employees, db_session: Session):
    worker = seed_basic_employees["worker"]
    period_start = seed_timesheet_data["period_start"]
    period_end = seed_timesheet_data["period_end"]

    db_session.add_all(
        [
            AttendanceDaily(
                employee_id=worker.id,
                work_date=date(2026, 4, 23),
                period_start=period_start,
                period_end=period_end,
                check_in_time="08:30",
                check_out_time="17:45",
                late_minutes=0,
                early_minutes=0,
                attendance_symbol="X",
                abnormal_level=None,
                source_priority=1,
            ),
            AttendanceDaily(
                employee_id=worker.id,
                work_date=date(2026, 4, 24),
                period_start=period_start,
                period_end=period_end,
                check_in_time="08:50",
                check_out_time="17:20",
                late_minutes=20,
                early_minutes=10,
                attendance_symbol="X",
                abnormal_level="L1",
                source_priority=1,
            ),
            AttendanceDaily(
                employee_id=worker.id,
                work_date=date(2026, 4, 25),
                period_start=period_start,
                period_end=period_end,
                check_in_time="08:55",
                check_out_time="17:10",
                late_minutes=25,
                early_minutes=15,
                attendance_symbol="X",
                abnormal_level="L2",
                source_priority=1,
            ),
        ]
    )

    db_session.add(
        TimesheetEntry(
            timesheet_id=seed_timesheet_data["timesheet"].id,
            employee_id=worker.id,
            work_date=date(2026, 4, 25),
            original_symbol="X",
            final_symbol="CT",
            check_in_time="08:00",
            check_out_time="18:00",
            late_minutes=0,
            early_minutes=0,
            is_overridden=True,
            override_reason="Dieu chinh cong tac",
            overridden_by_user_id=seed_basic_employees["approver"].id,
        )
    )
    db_session.commit()

    response = client.get(
        "/api/timesheets/conflict-audit",
        params={"period_start": period_start.isoformat(), "period_end": period_end.isoformat()},
    )
    assert response.status_code == 200
    rows = response.json()

    source_by_day = {r["work_date"]: r["resolved_source"] for r in rows}
    assert source_by_day["2026-04-23"] == "checkin_profile"
    assert source_by_day["2026-04-24"] == "abnormal"
    assert source_by_day["2026-04-25"] == "override"
