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


def test_hr_employee_create_cannot_assign_or_return_financial_fields(client, db_session, tmp_path, monkeypatch):
    from app.api import employees as employees_api
    from app.api import hr_api

    monkeypatch.setattr(employees_api, "UPLOAD_DIRECTORY", tmp_path)
    monkeypatch.setattr(hr_api, "UPLOAD_DIRECTORY", tmp_path)
    _assume_role("HR_ADMIN", user_id=9001)

    rejected = client.post(
        "/api/hr/employees",
        json={
            "machine_employee_id": "HR-NO-FINANCE-01",
            "full_name": "Nhan Su Khong Tai Chinh",
            "contract_salary": 88_000_000,
            "meal_allowance": 9_000_000,
            "bonus_coefficient": 99,
        },
    )
    assert rejected.status_code == 422
    assert db_session.query(Employee).filter(
        Employee.machine_employee_id == "HR-NO-FINANCE-01"
    ).first() is None

    response = client.post(
        "/api/hr/employees",
        json={
            "machine_employee_id": "HR-NO-FINANCE-01",
            "full_name": "Nhan Su Khong Tai Chinh",
            "employee_type": "FULLTIME",
            "contract_type": "PROBATION",
            "contract_sign_date": "2026-08-18",
            "contract_start_date": "2026-08-20",
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert data["financial_setup_status"] == "RESTRICTED"
    assert "contract_salary" not in data
    assert "meal_allowance" not in data
    assert "bonus_coefficient" not in data
    assert data["contract_type"] == "PROBATION"
    assert data["contract_sign_date"] == "2026-08-18"
    assert data["contract_start_date"] is None

    employee = db_session.query(Employee).filter(
        Employee.machine_employee_id == "HR-NO-FINANCE-01"
    ).one()
    assert employee.contract_salary == 0
    assert employee.meal_allowance == 0
    assert employee.bonus_coefficient == 0

    uploaded = client.post(
        f"/api/hr/employees/{employee.id}/upload-contract",
        files={"files": ("hop-dong.pdf", b"%PDF-1.4\ncontract-test", "application/pdf")},
    )
    assert uploaded.status_code == 200
    document_url = uploaded.json()["contract_url"][0]
    assert document_url.startswith(f"/api/hr/employees/{employee.id}/documents/contract/")
    assert client.get(document_url).status_code == 200

    removed = client.post(
        f"/api/hr/employees/{employee.id}/delete-document",
        json={"url": document_url, "doc_type": "contract"},
    )
    assert removed.status_code == 200
    assert removed.json()["contract_url"] == []


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


def test_director_matches_chief_accountant_business_access_without_it_tools(client):
    _assume_role("DIRECTOR")

    assert client.get("/api/role-dashboard/hr").status_code == 200
    assert client.get("/api/hr/employees").status_code == 200
    assert client.get("/api/salary/employees", params={"period": "2026-07"}).status_code == 200
    assert client.get("/api/commission/periods").status_code == 200
    assert client.get("/api/access/users").status_code == 200
    assert client.get("/api/role-dashboard/personal").status_code == 200
    assert client.get("/api/it/backups").status_code == 403
    assert client.get("/api/it/audit").status_code == 403
    assert client.get("/api/it/attendance-overrides").status_code == 403
