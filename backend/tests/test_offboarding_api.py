import json
from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import Employee, OffboardingRequest, Timesheet
from app.models.department import Department


def _answers() -> dict[str, object]:
    return {
        "full_name": "Nguyen Nhan Vien",
        "email": "nhanvien@example.com",
        "employee_code": "SL-EMP",
        "position": "Sales Executive",
        "department": "Operations",
        "request_date": "2026-08-28",
        "notice_period_days": "45",
        "desired_last_working_date": "2026-10-12",
        "reason": "Thay đổi định hướng nghề nghiệp.",
        "personal_opinion": "Cảm ơn công ty trong thời gian làm việc.",
        "direct_manager_name": "Tran Truong Phong",
        "no_grievance_confirmed": "YES",
        "handover_commitment_confirmed": "YES",
    }


def test_public_form_is_fixed_link_and_versioned(client: TestClient) -> None:
    public = client.get("/api/offboarding/form")
    assert public.status_code == 200
    payload = public.json()
    assert payload["status"] == "PUBLISHED"
    assert payload["version_number"] == 1
    assert {item["key"] for item in payload["fields"]} >= {"full_name", "email", "reason", "desired_last_working_date"}

    admin = client.get("/api/offboarding/admin/config")
    assert admin.status_code == 200
    assert admin.json()["public_path"] == "/offboarding"
    assert admin.json()["draft"]["version_number"] == 2


def test_builder_publish_updates_public_form(client: TestClient) -> None:
    draft = client.get("/api/offboarding/admin/config").json()["draft"]
    draft["title"] = "Biểu mẫu nghỉ việc đã cập nhật"
    draft["fields"][0]["label"] = "Họ tên nhân viên"
    response = client.post("/api/offboarding/admin/config/publish", json={
        "title": draft["title"], "description": draft["description"],
        "success_message": draft["success_message"], "fields": draft["fields"],
    })
    assert response.status_code == 200, response.text
    public = client.get("/api/offboarding/form").json()
    assert public["title"] == "Biểu mẫu nghỉ việc đã cập nhật"
    assert public["fields"][0]["label"] == "Họ tên nhân viên"


def test_public_submission_stays_pending_until_hr_approval(client: TestClient, db_session: Session) -> None:
    response = client.post("/api/offboarding/submissions", data={
        "answers_json": json.dumps(_answers()), "file_keys_json": json.dumps([]), "website": "",
    })
    assert response.status_code == 201, response.text
    assert response.json()["status"] == "NEW"

    rows = client.get("/api/offboarding/admin/submissions")
    assert rows.status_code == 200
    submission = rows.json()[0]
    assert submission["full_name"] == "Nguyen Nhan Vien"
    assert submission["employee_id"] is None

    department = Department(name="Operations")
    db_session.add(department); db_session.flush()
    employee = Employee(machine_employee_id="OFF-EMP", employee_code="SL-EMP", full_name="Nguyen Nhan Vien", personal_email="nhanvien@example.com", department_id=department.id)
    db_session.add(employee); db_session.commit(); db_session.refresh(employee)
    approved = client.post(f"/api/offboarding/admin/submissions/{submission['id']}/approve", json={
        "confirmed_last_working_date": "2026-10-15", "last_pay_date": "2026-10-31", "note": "Đã tự đối chiếu hồ sơ.",
    })
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "APPROVED"
    assert approved.json()["employee_id"] == employee.id
    db_session.refresh(employee)
    assert employee.resignation_period == "2026-10"
    assert employee.last_working_date == date(2026, 10, 15)
    assert employee.last_pay_date == date(2026, 10, 31)
    assert employee.status == "RESIGNED"
    assert employee.is_active is False

    # Current organization views exclude the employee without deleting their
    # historical department link.
    db_session.refresh(employee)
    assert employee.department_id == department.id
    department_payload = next(row for row in client.get("/api/departments").json() if row["id"] == department.id)
    assert employee.id not in {row["id"] for row in department_payload["employees"]}

    # Payroll history before departure is preserved, while later cycles no
    # longer materialize or display this employee. Even a stale future
    # timesheet cannot make the employee reappear after the final day.
    db_session.add(Timesheet(
        employee_id=employee.id,
        period_start=date(2026, 10, 23),
        period_end=date(2026, 11, 22),
        total_work_days=2,
        total_paid_leave_days=0,
        total_business_trip_days=0,
    ))
    db_session.commit()
    september_ids = {row["id"] for row in client.get("/api/salary/employees", params={"period": "2026-09"}).json()}
    november_ids = {row["id"] for row in client.get("/api/salary/employees", params={"period": "2026-11"}).json()}
    assert employee.id in september_ids
    assert employee.id not in november_ids


def test_required_dynamic_field_is_validated(client: TestClient) -> None:
    answers = _answers(); answers.pop("email")
    response = client.post("/api/offboarding/submissions", data={"answers_json": json.dumps(answers), "file_keys_json": "[]"})
    assert response.status_code == 422
    assert "Email" in response.json()["detail"]


def test_existing_form_version_is_preserved_after_new_publish(client: TestClient, db_session: Session) -> None:
    created = client.post("/api/offboarding/submissions", data={"answers_json": json.dumps(_answers()), "file_keys_json": "[]"})
    assert created.status_code == 201
    row = db_session.query(OffboardingRequest).one()
    original_version = row.form_version_id
    draft = client.get("/api/offboarding/admin/config").json()["draft"]
    client.post("/api/offboarding/admin/config/publish", json={"title": draft["title"], "description": draft["description"], "success_message": draft["success_message"], "fields": draft["fields"]})
    db_session.refresh(row)
    assert row.form_version_id == original_version
