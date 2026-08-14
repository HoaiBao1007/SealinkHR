from datetime import date

from sqlalchemy.orm import Session

from app.models.attendance_daily import AttendanceDaily
from app.models.attendance_log import AttendanceLog
from app.models.employee import Employee
from app.models.upload_batch import UploadBatch
from app.models.user import User


def test_commit_checkin_profile_with_skip_unknown_employee(client, seed_basic_employees, db_session: Session):
    uploader = seed_basic_employees["uploader"]
    
    # Seed a User for the uploader
    user = User(username="test_uploader_user", password_hash="hash", role="ADMIN")
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    payload = {
        "file_name": "checkin_2026_04.csv",
        "period_start": "2026-04-23",
        "period_end": "2026-05-22",
        "uploaded_by_user_id": user.id,
        "items": [
            {
                "machine_employee_id": "E001",
                "work_date": "2026-04-24",
                "check_in": "08:30",
                "check_out": "17:45",
                "period_start": "2026-04-23",
                "period_end": "2026-05-22",
                "raw_times": "08:30;17:45",
                "department": "Operations",
                "error": None,
            },
            {
                "machine_employee_id": "UNKNOWN",
                "work_date": "2026-04-24",
                "check_in": "08:40",
                "check_out": "17:35",
                "period_start": "2026-04-23",
                "period_end": "2026-05-22",
                "raw_times": "08:40;17:35",
                "department": "Operations",
                "error": None,
            },
        ],
    }

    response = client.post("/api/import/checkin-profile/commit", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["inserted"] == 1
    assert data["status"] == "completed_with_errors"
    assert len(data["skipped"]) == 1
    assert data["skipped"][0]["reason"] == "employee_not_found"

    batch = db_session.query(UploadBatch).filter(UploadBatch.id == data["batch_id"]).first()
    assert batch is not None
    assert batch.source_type == "checkin_profile"

    logs = db_session.query(AttendanceLog).all()
    assert len(logs) == 1
    assert logs[0].work_date == date(2026, 4, 24)


def test_commit_checkin_profile_ignores_spoofed_uploader(client):
    payload = {
        "file_name": "checkin_2026_04.csv",
        "period_start": "2026-04-23",
        "period_end": "2026-05-22",
        "uploaded_by_user_id": 9999,
        "items": [],
    }
    response = client.post("/api/import/checkin-profile/commit", json=payload)

    assert response.status_code == 200
    assert response.json()["inserted"] == 0
    assert "batch_id" in response.json()


def test_commit_checkin_profile_flexible_dates(client, seed_basic_employees, db_session: Session):
    uploader = seed_basic_employees["uploader"]
    
    # Seed a User for the uploader
    user = User(username="test_uploader_user_flex", password_hash="hash", role="ADMIN")
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    payload = {
        "file_name": "checkin_2026_04.csv",
        "period_start": "2026-04-23 00:00:00",  # Flexible format
        "period_end": "22/05/2026",            # Flexible format
        "uploaded_by_user_id": user.id,
        "items": [
            {
                "machine_employee_id": "E001",
                "work_date": "24/04/2026",        # Flexible format
                "raw_times": "08:30;17:45",
                # Missing optional fields: check_in, check_out, error, department, period_start, period_end
            }
        ],
    }

    response = client.post("/api/import/checkin-profile/commit", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["inserted"] == 1
    assert data["status"] == "completed"


def test_commit_merges_primary_and_secondary_biometric_profiles(client, db_session: Session):
    employee = Employee(
        machine_employee_id="29",
        biometric_id="42",
        full_name="Nguyễn Thị Thanh Hương",
        department_name="IT",
    )
    db_session.add(employee)
    db_session.commit()

    payload = {
        "file_name": "ruby_two_profiles.xls",
        "period_start": "2026-06-23",
        "period_end": "2026-07-22",
        "items": [
            {
                "machine_employee_id": "#29",
                "work_date": "2026-07-20",
                "check_in": "09:07",
                "raw_times": "09:07",
            },
            {
                "machine_employee_id": "＃42",
                "work_date": "2026-07-20",
                "check_in": "09:32",
                "check_out": "17:38",
                "raw_times": "09:32;17:38",
            },
            {
                "machine_employee_id": "42",
                "work_date": "2026-07-18",
                "check_in": "08:10",
                "check_out": "17:40",
                "raw_times": "08:10;17:40",
                "attendance_symbol": "X",
            },
        ],
    }

    response = client.post("/api/import/checkin-profile/commit", json=payload)

    assert response.status_code == 200
    assert response.json()["inserted"] == 2
    logs = db_session.query(AttendanceLog).filter(AttendanceLog.employee_id == employee.id).all()
    assert len(logs) == 2
    weekday = db_session.query(AttendanceDaily).filter_by(employee_id=employee.id, work_date=date(2026, 7, 20)).one()
    weekend = db_session.query(AttendanceDaily).filter_by(employee_id=employee.id, work_date=date(2026, 7, 18)).one()
    assert (weekday.check_in_time, weekday.check_out_time) == ("09:07", "17:38")
    assert weekend.attendance_symbol == ""

