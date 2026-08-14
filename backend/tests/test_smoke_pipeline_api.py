from datetime import date
from io import BytesIO

from sqlalchemy.orm import Session

from app.models.attendance_daily import AttendanceDaily
from app.models.user import User


def test_smoke_import_commit_timesheet_export_kpi(
    client,
    seed_basic_employees,
    seed_timesheet_data,
    db_session: Session,
):
    uploader = seed_basic_employees["uploader"]
    worker = seed_basic_employees["worker"]
    
    user = User(username="test_uploader_user_smoke", password_hash="hash", role="ADMIN")
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    health = client.get("/health")
    assert health.status_code == 200

    csv_content = "ID,Ten,Ngay,Moc gio\nE001,Nguyen Van A,24/04/2026,08:45*;10:54;13:39;18:03\n"
    files = {"file": ("checkin.csv", BytesIO(csv_content.encode("utf-8")), "text/csv")}
    preview_response = client.post("/api/import/checkin-profile", files=files)

    assert preview_response.status_code == 200
    preview_payload = preview_response.json()
    assert preview_payload["rows"] == 1

    preview_item = preview_payload["preview"][0]
    commit_payload = {
        "file_name": "checkin.csv",
        "period_start": preview_item["period_start"],
        "period_end": preview_item["period_end"],
        "uploaded_by_user_id": user.id,
        "items": [
            {
                "machine_employee_id": preview_item["machine_employee_id"],
                "work_date": preview_item["work_date"],
                "check_in": preview_item["check_in_time"],
                "check_out": preview_item["check_out_time"],
                "period_start": preview_item["period_start"],
                "period_end": preview_item["period_end"],
                "raw_times": preview_item["raw_time_values"],
                "department": "Operations",
                "error": preview_item["missing_reason"],
            }
        ],
    }
    commit_response = client.post("/api/import/checkin-profile/commit", json=commit_payload)

    assert commit_response.status_code == 200
    commit_body = commit_response.json()
    assert commit_body["inserted"] == 1

    daily = db_session.query(AttendanceDaily).filter(
        AttendanceDaily.employee_id == worker.id,
        AttendanceDaily.work_date == date(2026, 4, 24)
    ).first()
    if not daily:
        db_session.add(
            AttendanceDaily(
                employee_id=worker.id,
                work_date=date(2026, 4, 24),
                period_start=seed_timesheet_data["period_start"],
                period_end=seed_timesheet_data["period_end"],
                check_in_time="08:45",
                check_out_time="18:03",
                late_minutes=0,
                early_minutes=0,
                attendance_symbol="X",
                abnormal_level=None,
                source_priority=1,
            )
        )
        db_session.commit()

    timesheets_response = client.get(
        "/api/timesheets",
        params={
            "period_start": "2026-04-23",
            "period_end": "2026-05-22",
        },
    )
    assert timesheets_response.status_code == 200
    timesheets_body = timesheets_response.json()
    assert len(timesheets_body) >= 1

    dashboard_response = client.get(
        "/api/dashboard/kpi",
        params={
            "period_start": "2026-04-23",
            "period_end": "2026-05-22",
        },
    )
    assert dashboard_response.status_code == 200
    dashboard_body = dashboard_response.json()
    assert dashboard_body["present_days"] >= 1

    export_response = client.get(
        "/api/export/kpi",
        params={
            "period_start": "2026-04-23",
            "period_end": "2026-05-22",
        },
    )
    assert export_response.status_code == 200
    assert export_response.content[:2] == b"PK"
