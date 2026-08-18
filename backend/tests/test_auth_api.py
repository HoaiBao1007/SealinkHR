import pytest
from app.api.deps import get_current_user, get_admin_user
from app.core.auth import get_password_hash
from app.core.settings import settings
from app.models.user import User
from app.models.employee import Employee
from app.models.monthly_salary_input import MonthlySalaryInput
from app.models.system_audit_event import SystemAuditEvent
from app.models.trusted_device import TrustedDevice
from app.services.trusted_device_service import TRUSTED_DEVICE_COOKIE, hash_device_credential
from app.main import app


def test_it_admin_login_is_bound_to_registered_browser(client, db_session, monkeypatch):
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_admin_user, None)
    monkeypatch.setattr(settings, "it_admin_trusted_device_required", True)

    it_admin = User(
        username="it_device_test",
        password_hash=get_password_hash("safePassword123"),
        role="IT_ADMIN",
    )
    db_session.add(it_admin)
    db_session.flush()
    db_session.add(
        TrustedDevice(
            user_id=it_admin.id,
            device_label="70-A8-D3-1E-B5-4F",
            enrollment_ip="testclient",
            is_active=False,
        )
    )
    db_session.commit()

    first_login = client.post(
        "/api/auth/login",
        json={"username": "it_device_test", "password": "safePassword123"},
    )
    assert first_login.status_code == 200
    device_cookie = client.cookies.get(TRUSTED_DEVICE_COOKIE)
    assert device_cookie
    access_token = first_login.json()["access_token"]

    # The access token is also bound to the registered browser cookie.
    assert client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {access_token}"},
    ).status_code == 200
    client.cookies.clear()
    assert client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {access_token}"},
    ).status_code == 401

    # Private browsing or clearing cookies may lose the HttpOnly credential.
    # The server re-issues it only from the device's enrolled source IP.
    recovered = client.post(
        "/api/auth/login",
        json={"username": "it_device_test", "password": "safePassword123"},
    )
    assert recovered.status_code == 200
    recovered_cookie = client.cookies.get(TRUSTED_DEVICE_COOKIE)
    assert recovered_cookie
    assert recovered_cookie != device_cookie

    recovery_event = (
        db_session.query(SystemAuditEvent)
        .filter(SystemAuditEvent.action == "AUTH_LOGIN_DEVICE_RECOVERED")
        .order_by(SystemAuditEvent.id.desc())
        .first()
    )
    assert recovery_event is not None
    assert recovery_event.device_address == "70-A8-D3-1E-B5-4F"

    # A browser coming from another IP still cannot recover the credential.
    enrolled_device = (
        db_session.query(TrustedDevice)
        .filter(TrustedDevice.user_id == it_admin.id, TrustedDevice.is_active.is_(True))
        .one()
    )
    enrolled_device.enrollment_ip = "different-network"
    db_session.commit()
    client.cookies.clear()
    denied = client.post(
        "/api/auth/login",
        json={"username": "it_device_test", "password": "safePassword123"},
    )
    assert denied.status_code == 403

    enrolled_device.enrollment_ip = "testclient"
    db_session.commit()

    client.cookies.set(TRUSTED_DEVICE_COOKIE, recovered_cookie, path="/api")
    accepted = client.post(
        "/api/auth/login",
        json={"username": "it_device_test", "password": "safePassword123"},
    )
    assert accepted.status_code == 200

    login_event = (
        db_session.query(SystemAuditEvent)
        .filter(SystemAuditEvent.action == "AUTH_LOGIN", SystemAuditEvent.status == "SUCCESS")
        .order_by(SystemAuditEvent.id.desc())
        .first()
    )
    assert login_event is not None
    assert login_event.source_ip == "testclient"
    assert login_event.device_address == "70-A8-D3-1E-B5-4F"


def test_it_admin_can_enroll_an_additional_preapproved_device(client, db_session, monkeypatch):
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_admin_user, None)
    monkeypatch.setattr(settings, "it_admin_trusted_device_required", True)

    it_admin = User(
        username="it_additional_device_test",
        password_hash=get_password_hash("safePassword123"),
        role="IT_ADMIN",
    )
    db_session.add(it_admin)
    db_session.flush()
    existing = TrustedDevice(
        user_id=it_admin.id,
        device_label="70-A8-D3-1E-B5-4F",
        enrollment_ip="existing-network",
        credential_hash=hash_device_credential("existing-browser-credential"),
        is_active=True,
    )
    pending = TrustedDevice(
        user_id=it_admin.id,
        device_label="28-92-00-6F-20-98",
        enrollment_ip="wrong-network",
        is_active=False,
    )
    db_session.add_all([existing, pending])
    db_session.commit()

    # An existing active device does not make an unapproved source eligible.
    denied = client.post(
        "/api/auth/login",
        json={"username": it_admin.username, "password": "safePassword123"},
    )
    assert denied.status_code == 403
    db_session.refresh(pending)
    assert pending.is_active is False
    assert pending.credential_hash is None

    # Once the server operator pins the pending enrollment to this exact IP,
    # the next valid login enrolls it without revoking the existing browser.
    pending.enrollment_ip = "testclient"
    db_session.commit()
    enrolled = client.post(
        "/api/auth/login",
        json={"username": it_admin.username, "password": "safePassword123"},
    )
    assert enrolled.status_code == 200
    assert client.cookies.get(TRUSTED_DEVICE_COOKIE)
    db_session.refresh(existing)
    db_session.refresh(pending)
    assert existing.is_active is True
    assert pending.is_active is True
    assert pending.credential_hash


def test_it_admin_device_gate_can_be_temporarily_disabled(client, db_session, monkeypatch):
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_admin_user, None)
    monkeypatch.setattr(settings, "it_admin_trusted_device_required", False)

    it_admin = User(
        username="it_device_bypass_test",
        password_hash=get_password_hash("safePassword123"),
        role="IT_ADMIN",
    )
    db_session.add(it_admin)
    db_session.commit()

    login = client.post(
        "/api/auth/login",
        json={"username": it_admin.username, "password": "safePassword123"},
    )
    assert login.status_code == 200
    assert client.cookies.get(TRUSTED_DEVICE_COOKIE) is None
    access_token = login.json()["access_token"]
    assert client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {access_token}"},
    ).status_code == 200


def test_authentication_and_authorization_flow(client, db_session):
    # 1. Clear conftest mock authentication overrides to test actual logic
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_admin_user, None)

    # 2. Seed test data directly in the test session
    admin_pw = get_password_hash("admin123")
    user_pw = get_password_hash("password123")

    admin = User(username="admin_test", password_hash=admin_pw, role="ADMIN")
    regular = User(username="user_test", password_hash=user_pw, role="USER")
    
    db_session.add_all([admin, regular])
    db_session.commit()
    db_session.refresh(admin)
    db_session.refresh(regular)

    emp = Employee(
        machine_employee_id="38",
        full_name="Hoaibao Test",
        employee_code="SL038",
        contract_salary=20000000,
        employee_type="PROBATION",
        user_id=regular.id,
    )
    db_session.add(emp)
    db_session.commit()
    db_session.refresh(emp)

    salary_input = MonthlySalaryInput(
        employee_id=emp.id,
        salary_period="2026-05",
        actual_working_days=22.0,
        other_income=750000,
        other_income_note="Hỗ trợ dự án nội bộ tháng 5",
        is_published=False,
    )
    db_session.add(salary_input)
    db_session.commit()

    # --- Test Login ---
    # Invalid Login
    login_res = client.post("/api/auth/login", json={"username": "admin_test", "password": "wrongpassword"})
    assert login_res.status_code == 400
    assert "Tên đăng nhập hoặc mật khẩu không chính xác" in login_res.json()["detail"]

    # Valid Admin Login
    login_res = client.post("/api/auth/login", json={"username": "admin_test", "password": "admin123"})
    assert login_res.status_code == 200
    admin_data = login_res.json()
    assert admin_data["role"] == "ADMIN"
    assert "access_token" in admin_data
    admin_token = admin_data["access_token"]

    # Valid User Login
    login_res = client.post("/api/auth/login", json={"username": "user_test", "password": "password123"})
    assert login_res.status_code == 200
    user_data = login_res.json()
    assert user_data["role"] == "USER"
    assert user_data["fullname"] == "Hoaibao Test"
    user_token = user_data["access_token"]

    # --- Test Profile ---
    headers_admin = {"Authorization": f"Bearer {admin_token}"}
    headers_user = {"Authorization": f"Bearer {user_token}"}

    me_res = client.get("/api/auth/me", headers=headers_admin)
    assert me_res.status_code == 200
    assert me_res.json()["username"] == "admin_test"

    me_res = client.get("/api/auth/me", headers=headers_user)
    assert me_res.status_code == 200
    assert me_res.json()["username"] == "user_test"

    # --- Test Protected Paths (Admin role check) ---
    # Anonymous -> 401
    res = client.get("/api/salary/employees")
    assert res.status_code == 401

    # User Role -> 403 Forbidden
    res = client.get("/api/salary/employees", headers=headers_user)
    assert res.status_code == 403

    # Admin Role -> 200 OK
    res = client.get("/api/salary/employees", headers=headers_admin)
    assert res.status_code == 200

    # --- Test User Portal Endpoints ---
    # Fetch unpublished payslip -> 403 Forbidden
    payslip_res = client.get("/api/user/my-payslip", params={"period": "2026-05"}, headers=headers_user)
    assert payslip_res.status_code == 403
    assert "chưa được phát hành" in payslip_res.json()["detail"]

    # Admin publishes payslips
    pub_res = client.post("/api/salary/publish", json={"period": "2026-05", "is_published": True}, headers=headers_admin)
    assert pub_res.status_code == 200
    assert pub_res.json()["published_count"] == 1

    # The employee selector exposes only issued periods, avoiding requests for
    # arbitrary months that cannot have a payslip yet.
    periods_res = client.get("/api/user/my-payslip-periods", headers=headers_user)
    assert periods_res.status_code == 200
    assert periods_res.json() == ["2026-05"]

    # Fetch published payslip -> 200 OK
    payslip_res = client.get("/api/user/my-payslip", params={"period": "2026-05"}, headers=headers_user)
    assert payslip_res.status_code == 200
    payslip_data = payslip_res.json()
    assert payslip_data["employee_name"] == "Hoaibao Test"
    assert payslip_data["contract_salary"] == 20000000
    assert payslip_data["inputs"]["other_income"] == 750000
    assert payslip_data["inputs"]["other_income_note"] == "Hỗ trợ dự án nội bộ tháng 5"

    # The downloaded document is a server-generated PDF, not a canvas image.
    pdf_res = client.get("/api/user/my-payslip-pdf", params={"period": "2026-05"}, headers=headers_user)
    assert pdf_res.status_code == 200
    assert pdf_res.headers["content-type"].startswith("application/pdf")
    assert "attachment" in pdf_res.headers["content-disposition"]
    assert pdf_res.content.startswith(b"%PDF")

    # Fetch personal attendance -> 200 OK
    att_res = client.get("/api/user/my-attendance", params={"period_start": "2026-04-23", "period_end": "2026-05-22"}, headers=headers_user)
    assert att_res.status_code == 200
    att_data = att_res.json()
    assert len(att_data) == 30  # 30 days between April 23 and May 22
    assert att_data[0]["work_date"] == "2026-04-23"

    # --- Test self-service account management ---
    account_res = client.get("/api/user/my-account", headers=headers_user)
    assert account_res.status_code == 200
    account_data = account_res.json()
    assert account_data["employee_id"] == emp.id
    assert account_data["username"] == "user_test"
    assert account_data["role"] == "USER"

    # A username/password change must be confirmed with the current password.
    missing_password_res = client.patch(
        "/api/user/my-account",
        headers=headers_user,
        json={"username": "user_test_changed"},
    )
    assert missing_password_res.status_code == 400

    # Fields outside the self-service allow-list (role, salary, etc.) are rejected.
    forbidden_field_res = client.patch(
        "/api/user/my-account",
        headers=headers_user,
        json={"role": "ADMIN"},
    )
    assert forbidden_field_res.status_code == 422

    update_account_res = client.patch(
        "/api/user/my-account",
        headers=headers_user,
        json={
            "username": "user_test_changed",
            "current_password": "password123",
            "new_password": "newPassword456",
        },
    )
    assert update_account_res.status_code == 200
    assert update_account_res.json()["username"] == "user_test_changed"

    old_login_res = client.post(
        "/api/auth/login",
        json={"username": "user_test", "password": "password123"},
    )
    assert old_login_res.status_code == 400

    new_login_res = client.post(
        "/api/auth/login",
        json={"username": "user_test_changed", "password": "newPassword456"},
    )
    assert new_login_res.status_code == 200
    assert new_login_res.json()["role"] == "USER"
