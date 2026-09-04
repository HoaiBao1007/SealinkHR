from datetime import date

from sqlalchemy.orm import Session

from app.models.attendance_daily import AttendanceDaily
from app.models.off_request import OffRequest


def test_get_timesheet_grid(client, seed_timesheet_data, seed_basic_employees, db_session: Session):
    worker = seed_basic_employees["worker"]
    period_start = seed_timesheet_data["period_start"]
    period_end = seed_timesheet_data["period_end"]

    rows = [
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
            check_in_time="08:55",
            check_out_time="17:20",
            late_minutes=25,
            early_minutes=10,
            attendance_symbol="X",
            abnormal_level="L1",
            source_priority=1,
        ),
    ]
    db_session.add_all(rows)
    db_session.commit()

    response = client.get(
        "/api/timesheets/grid",
        params={"period_start": period_start.isoformat(), "period_end": period_end.isoformat()},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["period_start"] == period_start.isoformat()
    assert payload["period_end"] == period_end.isoformat()
    assert len(payload["day_keys"]) == 30
    assert len(payload["rows"]) == 1

    row = next(item for item in payload["rows"] if item["employee_id"] == worker.id)
    assert row["employee_id"] == worker.id
    assert row["days"]["2026-04-23"] == "X"
    assert row["days"]["2026-04-24"] == "X"
    assert row["abnormal_days"] == 1
    assert row["total_late_minutes"] == 25
    assert row["total_early_minutes"] == 10


def test_timesheet_grid_uses_vietnamese_employee_name(client, seed_timesheet_data, seed_basic_employees, db_session: Session):
    worker = seed_basic_employees["worker"]
    worker.full_name = "ĐẶNG HOÀI BẢO"
    worker.notion_name = "Baron"
    db_session.add(worker)
    db_session.commit()

    response = client.get(
        "/api/timesheets/grid",
        params={
            "period_start": seed_timesheet_data["period_start"].isoformat(),
            "period_end": seed_timesheet_data["period_end"].isoformat(),
        },
    )

    assert response.status_code == 200
    row = next(item for item in response.json()["rows"] if item["employee_id"] == worker.id)
    assert row["full_name"] == "ĐẶNG HOÀI BẢO"


def test_get_timesheet_grid_applies_hr_matrix_and_leave_summary(client, seed_timesheet_data, seed_basic_employees, db_session: Session):
    worker = seed_basic_employees["worker"]
    period_start = seed_timesheet_data["period_start"]
    period_end = seed_timesheet_data["period_end"]
    worker.paid_leave_balance = 12

    db_session.add_all(
        [
            AttendanceDaily(
                employee_id=worker.id,
                work_date=date(2026, 4, 23),
                period_start=period_start,
                period_end=period_end,
                check_in_time="08:30",
                check_out_time="17:30",
                late_minutes=0,
                early_minutes=0,
                attendance_symbol="X",
                abnormal_level=None,
                source_priority=1,
            ),
            AttendanceDaily(
                employee_id=worker.id,
                work_date=date(2026, 4, 25),
                period_start=period_start,
                period_end=period_end,
                check_in_time=None,
                check_out_time=None,
                late_minutes=0,
                early_minutes=0,
                attendance_symbol="V",
                abnormal_level=None,
                source_priority=1,
            ),
            AttendanceDaily(
                employee_id=worker.id,
                work_date=date(2026, 4, 27),
                period_start=period_start,
                period_end=period_end,
                check_in_time="08:35",
                check_out_time="17:15",
                late_minutes=5,
                early_minutes=0,
                attendance_symbol="X",
                abnormal_level=None,
                source_priority=1,
            ),
            AttendanceDaily(
                employee_id=worker.id,
                work_date=date(2026, 4, 28),
                period_start=period_start,
                period_end=period_end,
                check_in_time=None,
                check_out_time=None,
                late_minutes=0,
                early_minutes=0,
                attendance_symbol="V",
                abnormal_level=None,
                source_priority=1,
            ),
        ]
    )
    db_session.add_all(
        [
            OffRequest(
                employee_id=worker.id,
                request_type="paid_leave",
                start_date=date(2026, 4, 24),
                end_date=date(2026, 4, 24),
                total_days=1,
                reason="Phep ca ngay",
                status="approved",
            ),
            OffRequest(
                employee_id=worker.id,
                request_type="paid_leave_pm",
                start_date=date(2026, 4, 27),
                end_date=date(2026, 4, 27),
                total_days=0.5,
                reason="Phep nua ngay",
                status="approved",
            ),
        ]
    )
    db_session.commit()

    response = client.get(
        "/api/timesheets/grid",
        params={"period_start": period_start.isoformat(), "period_end": period_end.isoformat()},
    )

    assert response.status_code == 200
    payload = response.json()
    row = next(item for item in payload["rows"] if item["employee_id"] == worker.id)
    assert payload["day_columns"][2]["weekday_label"] == "T7"
    assert payload["day_columns"][3]["weekday_label"] == "CN"
    assert row["days"]["2026-04-23"] == "X"
    assert row["days"]["2026-04-24"] == "P"
    assert row["days"]["2026-04-25"] == ""
    assert row["days"]["2026-04-26"] == ""
    assert row["days"]["2026-04-27"] == "X/P"
    assert row["days"]["2026-04-28"] == "Ro"
    assert row["paid_leave_days"] == 1.5
    assert row["unpaid_leave_days"] == 1.0
    assert row["remaining_paid_leave_days"] == 11.5
