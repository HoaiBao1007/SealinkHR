from datetime import date

from sqlalchemy.orm import Session

from app.models.attendance_daily import AttendanceDaily


def test_export_kpi_success(client, seed_basic_employees, db_session: Session):
    worker = seed_basic_employees["worker"]
    period_start = date(2026, 4, 23)
    period_end = date(2026, 5, 22)

    db_session.add(
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
        )
    )
    db_session.commit()

    response = client.get(
        "/api/export/kpi",
        params={"period_start": period_start.isoformat(), "period_end": period_end.isoformat()},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    assert "attachment; filename=\"kpi_2026-04-23_2026-05-22.xlsx\"" in response.headers.get(
        "content-disposition", ""
    )
    assert response.content[:2] == b"PK"


def test_export_kpi_not_found(client):
    response = client.get(
        "/api/export/kpi",
        params={"period_start": "2026-04-23", "period_end": "2026-05-22"},
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "no KPI data for selected period"
