from datetime import date

from sqlalchemy.orm import Session

from app.models.attendance_daily import AttendanceDaily


def test_dashboard_kpi_summary(client, seed_basic_employees, db_session: Session):
    worker = seed_basic_employees["worker"]
    period_start = date(2026, 4, 23)
    period_end = date(2026, 5, 22)

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
                check_in_time="08:55",
                check_out_time="17:20",
                late_minutes=25,
                early_minutes=10,
                attendance_symbol="V",
                abnormal_level="L1",
                source_priority=1,
            ),
            AttendanceDaily(
                employee_id=worker.id,
                work_date=date(2026, 4, 25),
                period_start=period_start,
                period_end=period_end,
                check_in_time="08:20",
                check_out_time="17:50",
                late_minutes=0,
                early_minutes=0,
                attendance_symbol="CT",
                abnormal_level=None,
                source_priority=1,
            ),
        ]
    )
    db_session.commit()

    response = client.get(
        "/api/dashboard/kpi",
        params={"period_start": period_start.isoformat(), "period_end": period_end.isoformat()},
    )
    assert response.status_code == 200
    payload = response.json()

    assert payload["total_employees"] >= 1
    assert payload["present_days"] == 1
    assert payload["absent_days"] == 1
    assert payload["business_trip_days"] == 1
    assert payload["unpaid_leave_days"] == 1
    assert payload["total_late_minutes"] == 25
    assert payload["total_early_minutes"] == 10
    assert payload["abnormal_days"] == 1
    assert payload["symbol_counts"]["X"] == 1
    assert payload["symbol_counts"]["V"] == 1
    assert payload["symbol_counts"]["CT"] == 1
    assert len(payload["trend"]) == 3
