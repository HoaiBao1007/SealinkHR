from datetime import date

from sqlalchemy.orm import Session

from app.models.attendance_override_audit import AttendanceOverrideAudit


def test_override_history_success(client, seed_basic_employees, db_session: Session):
    worker = seed_basic_employees["worker"]
    approver = seed_basic_employees["approver"]

    db_session.add(
        AttendanceOverrideAudit(
            employee_id=worker.id,
            work_date=date(2026, 4, 24),
            old_symbol="V",
            new_symbol="CT",
            old_check_in=None,
            new_check_in="08:00",
            old_check_out=None,
            new_check_out="18:00",
            reason="Dieu chinh cong tac",
            changed_by_user_id=approver.id,
        )
    )
    db_session.commit()

    response = client.get(
        "/api/attendance/override/history",
        params={
            "period_start": "2026-04-23",
            "period_end": "2026-05-22",
            "limit": 50,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    row = payload[0]
    assert row["employee_id"] == worker.id
    assert row["employee_name"] == worker.full_name
    assert row["new_symbol"] == "CT"
    assert row["changed_by_user_id"] == approver.id
    assert row["changed_by_name"] == approver.full_name


def test_override_history_invalid_period(client):
    response = client.get(
        "/api/attendance/override/history",
        params={
            "period_start": "2026-05-22",
            "period_end": "2026-04-23",
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "period_start must be <= period_end"
