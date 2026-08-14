"""Security-boundary tests for the operational role dashboards.

These tests focus on denials as well as allowed access. IT_ADMIN is the
highest role: it inherits every ADMIN business permission and adds IT tools.
"""

from app.api.deps import get_admin_user, get_current_user
from app.main import app
from app.models.employee import Employee
from app.models.user import User


def _assume_role(role: str, *, user_id: int = 9000) -> User:
    user = User(id=user_id, username=f"test_{role.lower()}", role=role)
    # The shared fixture overrides get_admin_user for legacy tests.  Remove
    # that shortcut here so these tests exercise the real role boundary.
    app.dependency_overrides.pop(get_admin_user, None)
    app.dependency_overrides[get_current_user] = lambda: user
    return user


def test_hr_admin_can_manage_hr_but_cannot_read_finance(client, db_session):
    user = _assume_role("HR_ADMIN")
    db_session.add(
        Employee(
            machine_employee_id="HR-RBAC-01",
            employee_code="HRRBAC01",
            full_name="Nhan Su RBAC",
            user_id=user.id,
            contract_salary=99_000_000,
            meal_allowance=1_200_000,
            phone_allowance=2_000_000,
        )
    )
    db_session.commit()

    employees = client.get("/api/hr/employees")
    assert employees.status_code == 200
    row = employees.json()[0]
    assert row["financial_setup_status"] == "RESTRICTED"
    assert "contract_salary" not in row
    assert "meal_allowance" not in row
    assert "phone_allowance" not in row

    assert client.get("/api/role-dashboard/hr").status_code == 200
    assert client.get("/api/salary/employees", params={"period": "2026-07"}).status_code == 403
    assert client.get("/api/commission/periods").status_code == 403
    assert client.get("/api/access/users").status_code == 403
    assert client.get("/api/it/audit").status_code == 403
    assert client.get("/api/it/attendance-overrides").status_code == 403
    assert client.get("/api/role-dashboard/personal").status_code == 200
    assert client.get("/api/user/my-account").status_code == 200
    assert client.get("/api/user/my-payslip-periods").status_code == 200
    assert client.get(
        "/api/user/my-attendance",
        params={"period_start": "2026-06-23", "period_end": "2026-07-22"},
    ).status_code == 200


def test_it_admin_inherits_all_business_admin_and_it_apis(client):
    _assume_role("IT_ADMIN")

    assert client.get("/api/it/backups").status_code == 200
    assert client.get("/api/it/audit").status_code == 200
    assert client.get("/api/it/attendance-overrides").status_code == 200
    assert client.get("/api/role-dashboard/personal").status_code == 200
    assert client.get("/api/role-dashboard/hr").status_code == 200
    assert client.get("/api/hr/employees").status_code == 200
    assert client.get("/api/salary/employees", params={"period": "2026-07"}).status_code == 200
    assert client.get("/api/commission/periods").status_code == 200
    assert client.get("/api/access/users").status_code == 200


def test_employee_role_is_limited_to_own_portal(client, db_session):
    user = _assume_role("USER", user_id=9100)
    db_session.add(
        Employee(
            machine_employee_id="USER-RBAC-01",
            employee_code="RBAC01",
            full_name="Nhan Vien Portal",
            user_id=user.id,
        )
    )
    db_session.commit()

    dashboard = client.get("/api/role-dashboard/personal")
    assert dashboard.status_code == 200
    assert dashboard.json()["employee"]["employee_code"] == "RBAC01"
    assert client.get("/api/hr/employees").status_code == 403
    assert client.get("/api/role-dashboard/hr").status_code == 403
    assert client.get("/api/it/audit").status_code == 403
    assert client.get("/api/it/attendance-overrides").status_code == 403
    assert client.get("/api/salary/employees", params={"period": "2026-07"}).status_code == 403
    assert client.get("/api/commission/periods").status_code == 403


def test_existing_admin_remains_full_business_administrator(client):
    _assume_role("ADMIN")

    assert client.get("/api/role-dashboard/hr").status_code == 200
    assert client.get("/api/hr/employees").status_code == 200
    assert client.get("/api/salary/employees", params={"period": "2026-07"}).status_code == 200
    assert client.get("/api/commission/periods").status_code == 200
    assert client.get("/api/access/users").status_code == 200
    # The current accountant dashboard is not expanded into the IT console.
    assert client.get("/api/it/audit").status_code == 403
    assert client.get("/api/it/attendance-overrides").status_code == 403
