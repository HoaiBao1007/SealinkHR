import json

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import Employee


def _answers() -> dict[str, object]:
    return {
        "full_name": "Nguyen Onboard",
        "english_name": "Onboard Nguyen",
        "date_of_birth": "2000-01-02",
        "address": "Ho Chi Minh City",
        "personal_phone": "0909000000",
        "company_extension": "",
        "email": "onboard@example.com",
        "application_type": "PROBATION",
        "position_applied": "Operations Executive",
        "marital_status": "SINGLE",
        "health_status": "Tot",
        "bank_name": "VCB",
        "bank_account": "123456789",
        "required_documents": ["CV", "DIPLOMA"],
        "company_notes": "",
        "office_days_per_week": "5",
        "available_start_date": "2026-09-01",
    }


def test_public_form_is_bootstrapped_and_versioned(client: TestClient) -> None:
    response = client.get("/api/onboarding/form")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "PUBLISHED"
    assert payload["version_number"] == 1
    assert {field["key"] for field in payload["fields"]} >= {
        "full_name",
        "email",
        "application_type",
        "identity_documents",
    }

    admin_response = client.get("/api/onboarding/admin/config")
    assert admin_response.status_code == 200
    assert admin_response.json()["draft"]["version_number"] == 2


def test_publish_uses_latest_configuration_sent_by_builder(client: TestClient) -> None:
    configuration = client.get("/api/onboarding/admin/config").json()
    draft = configuration["draft"]
    draft["title"] = "Biểu mẫu onboarding vừa chỉnh sửa"
    draft["fields"][0]["label"] = "Họ tên theo phiên bản mới"

    response = client.post(
        "/api/onboarding/admin/config/publish",
        json={
            "title": draft["title"],
            "description": draft["description"],
            "success_message": draft["success_message"],
            "fields": draft["fields"],
        },
    )

    assert response.status_code == 200, response.text
    published = response.json()["published"]
    assert published["title"] == "Biểu mẫu onboarding vừa chỉnh sửa"
    assert published["fields"][0]["label"] == "Họ tên theo phiên bản mới"

    public_form = client.get("/api/onboarding/form")
    assert public_form.status_code == 200
    assert public_form.json()["title"] == "Biểu mẫu onboarding vừa chỉnh sửa"
    assert public_form.json()["fields"][0]["label"] == "Họ tên theo phiên bản mới"


def test_submission_stays_staged_until_admin_approval(
    client: TestClient,
    db_session: Session,
) -> None:
    response = client.post(
        "/api/onboarding/submissions",
        data={
            "answers_json": json.dumps(_answers()),
            "file_keys_json": json.dumps(["identity_documents", "identity_documents"]),
            "website": "",
        },
        files=[
            ("files", ("cccd-front.png", b"front", "image/png")),
            ("files", ("cccd-back.png", b"back", "image/png")),
        ],
    )
    assert response.status_code == 201, response.text
    created = response.json()
    assert created["status"] == "NEW"
    assert db_session.query(Employee).filter(Employee.full_name == "Nguyen Onboard").first() is None

    submissions = client.get("/api/onboarding/admin/submissions")
    assert submissions.status_code == 200
    staged = submissions.json()[0]
    assert staged["full_name"] == "Nguyen Onboard"
    assert len(staged["attachments"]) == 2

    blank_machine_id = client.post(
        f"/api/onboarding/admin/submissions/{staged['id']}/approve",
        json={"machine_employee_id": "   "},
    )
    assert blank_machine_id.status_code == 422
    assert "mã máy chấm công" in blank_machine_id.json()["detail"].lower()

    approval = client.post(
        f"/api/onboarding/admin/submissions/{staged['id']}/approve",
        json={
            "machine_employee_id": "ONB001",
            "employee_code": "SL999",
            "department_id": None,
            "start_date": "2026-09-01",
        },
    )
    assert approval.status_code == 200, approval.text
    approved = approval.json()
    assert approved["status"] == "PROBATION"
    assert approved["employee_id"] is not None

    employee = db_session.query(Employee).filter(Employee.machine_employee_id == "ONB001").one()
    assert employee.full_name == "Nguyen Onboard"
    assert employee.contract_salary == 0
    assert employee.cccd_url


def test_required_dynamic_field_is_validated(client: TestClient) -> None:
    answers = _answers()
    answers.pop("email")
    response = client.post(
        "/api/onboarding/submissions",
        data={
            "answers_json": json.dumps(answers),
            "file_keys_json": json.dumps(["identity_documents"]),
        },
        files=[("files", ("cccd.png", b"image", "image/png"))],
    )
    assert response.status_code == 422
    assert "Email" in response.json()["detail"]


def test_attachment_must_belong_to_a_visible_file_field(client: TestClient) -> None:
    response = client.post(
        "/api/onboarding/submissions",
        data={
            "answers_json": json.dumps(_answers()),
            "file_keys_json": json.dumps(["unknown_upload"]),
        },
        files=[("files", ("cccd.png", b"image", "image/png"))],
    )
    assert response.status_code == 422
    assert "không thuộc trường" in response.json()["detail"]
