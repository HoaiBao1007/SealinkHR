from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.main import app
from app.models.notification import Notification
from app.models.employee import Employee
from app.models.commission import CommissionJob, CommissionPeriod, CommissionWalletLedger
from app.models.user import User


def _user(db: Session, username: str, role: str) -> User:
    item = User(username=username, password_hash="test-hash", role=role)
    db.add(item)
    db.flush()
    return item


def _as(client: TestClient, user: User):
    app.dependency_overrides[get_current_user] = lambda: user
    return client.get("/api/notifications")


def test_notification_visibility_is_role_aware(client: TestClient, db_session: Session):
    chief = _user(db_session, "chief", "ADMIN")
    it_admin = _user(db_session, "it", "IT_ADMIN")
    hr_admin = _user(db_session, "hr", "HR_ADMIN")
    employee = _user(db_session, "employee", "USER")
    other_employee = _user(db_session, "other", "USER")
    db_session.add_all(
        [
            Notification(category="HR", event_type="EMPLOYEE_CREATED", title="Nhân sự mới", message="Đã thêm hồ sơ"),
            Notification(category="PAYROLL", event_type="PAYSLIP_PUBLISHED", title="Phiếu lương", message="Đã phát hành", target_user_id=employee.id),
            Notification(category="BONUS", event_type="BONUS_PAYOUT_APPROVED", title="Bonus", message="Đã duyệt", target_user_id=other_employee.id),
        ]
    )
    db_session.commit()

    chief_payload = _as(client, chief).json()
    assert chief_payload["unread_count"] == 3
    assert {item["category"] for item in chief_payload["items"]} == {"HR", "PAYROLL", "BONUS"}

    it_payload = _as(client, it_admin).json()
    assert it_payload["unread_count"] == 3

    hr_payload = _as(client, hr_admin).json()
    assert hr_payload["unread_count"] == 1
    assert [item["category"] for item in hr_payload["items"]] == ["HR"]

    employee_payload = _as(client, employee).json()
    assert employee_payload["unread_count"] == 1
    assert [item["category"] for item in employee_payload["items"]] == ["PAYROLL"]
    assert employee_payload["items"][0]["target_name"] == "employee"


def test_read_state_is_private_to_each_account(client: TestClient, db_session: Session):
    chief = _user(db_session, "chief", "ADMIN")
    it_admin = _user(db_session, "it", "IT_ADMIN")
    item = Notification(category="HR", event_type="EMPLOYEE_UPDATED", title="Cập nhật", message="Hồ sơ thay đổi")
    db_session.add(item)
    db_session.commit()
    db_session.refresh(item)

    app.dependency_overrides[get_current_user] = lambda: chief
    response = client.post(f"/api/notifications/items/{item.id}/read")
    assert response.status_code == 200
    assert client.get("/api/notifications").json()["unread_count"] == 0

    app.dependency_overrides[get_current_user] = lambda: it_admin
    assert client.get("/api/notifications").json()["unread_count"] == 1


def test_user_cannot_mark_another_users_notification(client: TestClient, db_session: Session):
    owner = _user(db_session, "owner", "USER")
    stranger = _user(db_session, "stranger", "USER")
    item = Notification(category="PAYROLL", event_type="PAYSLIP_PUBLISHED", title="Phiếu lương", message="Đã phát hành", target_user_id=owner.id)
    db_session.add(item)
    db_session.commit()
    db_session.refresh(item)

    app.dependency_overrides[get_current_user] = lambda: stranger
    response = client.post(f"/api/notifications/items/{item.id}/read")
    assert response.status_code == 404


def test_employee_bonus_request_notifies_chief_accountant_and_it_admin(client: TestClient, db_session: Session):
    employee_user = _user(db_session, "dat", "USER")
    chief = _user(db_session, "chief", "ADMIN")
    it_admin = _user(db_session, "it", "IT_ADMIN")
    hr_admin = _user(db_session, "hr", "HR_ADMIN")
    employee = Employee(
        machine_employee_id="26",
        employee_code="SL003",
        full_name="NGUYEN THANH DAT",
        user_id=employee_user.id,
    )
    period = CommissionPeriod(
        period_label="01-Jul-2026 → 30-Sep-2026",
        from_date=date(2026, 7, 1),
        till_date=date(2026, 9, 30),
    )
    db_session.add_all([employee, period])
    db_session.flush()
    job = CommissionJob(
        period_id=period.id,
        job_no="SEJ-752/26",
        sales_rep=employee.full_name,
        customer="WEB-PRO",
        payment_received="NO",
    )
    db_session.add(job)
    db_session.flush()
    db_session.add(
        CommissionWalletLedger(
            period_id=period.id,
            job_id=job.id,
            sales_rep=employee.full_name,
            employee_id=employee.id,
            entry_type="ACCRUAL_HELD",
            amount=79_415.5,
        )
    )
    db_session.commit()

    app.dependency_overrides[get_current_user] = lambda: employee_user
    requested = client.post(
        f"/api/user/my-held-bonus-jobs/{job.id}/request-accounting",
        json={"note": "Nhờ kế toán kiểm tra"},
    )
    assert requested.status_code == 200

    chief_payload = _as(client, chief).json()
    assert chief_payload["unread_count"] == 1
    assert chief_payload["items"][0]["event_type"] == "BONUS_PAYOUT_REQUESTED"
    assert chief_payload["items"][0]["action_url"] == "/admin/commission"
    assert "SEJ-752/26" in chief_payload["items"][0]["title"]
    action_context = chief_payload["items"][0]["action_context"]
    assert action_context["job_id"] == job.id
    assert action_context["job_no"] == "SEJ-752/26"
    assert action_context["period_id"] == period.id
    assert action_context["period_label"] == period.period_label
    assert action_context["sales_rep"] == employee.full_name
    assert action_context["payout_periods"] == []

    assert _as(client, it_admin).json()["unread_count"] == 1
    assert _as(client, hr_admin).json()["unread_count"] == 0
    assert _as(client, employee_user).json()["unread_count"] == 0
