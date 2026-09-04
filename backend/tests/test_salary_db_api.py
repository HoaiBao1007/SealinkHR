from datetime import date
from types import SimpleNamespace

from app.api.deps import get_admin_user, get_current_user
from app.core.roles import ADMIN, DIRECTOR, IT_ADMIN, USER
from app.main import app
from app.models.employee import Employee
from app.models.monthly_salary_input import MonthlySalaryInput
from app.models.notification import Notification
from app.models.salary_approval_workflow import SalaryApprovalWorkflow
from app.models.timesheet import Timesheet
from app.models.user import User
from app.services.salary import cake_salary, calculate_period_working_days, resolve_export_salary_policy
from app.services.salary_policy import ensure_default_salary_policy


def test_salary_approval_requires_chief_accountant_request_and_director_or_it_approval(client, db_session):
    employee = client.post(
        "/api/employees",
        json={
            "machine_employee_id": "E798",
            "full_name": "Salary Period Employee",
            "notion_name": "SALARY PERIOD EMPLOYEE",
        },
    )
    assert employee.status_code == 200
    employee_id = employee.json()["id"]

    chief = User(username="chief.accountant", password_hash="test", role=ADMIN)
    director_one = User(username="director.one", password_hash="test", role=DIRECTOR)
    director_two = User(username="director.two", password_hash="test", role=DIRECTOR)
    it_admin = User(username="it.admin", password_hash="test", role=IT_ADMIN)
    employee_user = User(username="salary.employee", password_hash="test", role=USER)
    db_session.add_all([chief, director_one, director_two, it_admin, employee_user])
    db_session.flush()
    chief_id = chief.id
    director_one_id = director_one.id
    director_two_id = director_two.id
    it_admin_id = it_admin.id
    employee_user_id = employee_user.id
    salary_employee = db_session.query(Employee).filter(Employee.id == employee_id).one()
    salary_employee.user_id = employee_user_id
    db_session.commit()

    def authenticate(user_id: int, username: str, role: str) -> None:
        principal = SimpleNamespace(id=user_id, username=username, role=role)
        app.dependency_overrides[get_current_user] = lambda principal=principal: principal
        app.dependency_overrides[get_admin_user] = lambda principal=principal: principal

    authenticate(chief_id, "chief.accountant", ADMIN)

    for period in ("2026-07", "2026-08"):
        created = client.post(
            "/api/salary/inputs",
            json={"employee_id": employee_id, "salary_period": period},
        )
        assert created.status_code == 200
        assert created.json()[0]["is_published"] is False

    confirmed = client.post("/api/salary/approval/confirm", json={"period": "2026-07"})
    assert confirmed.status_code == 200
    assert confirmed.json()["status"] == "CONFIRMED"

    july_before_approval = db_session.query(MonthlySalaryInput).filter(
        MonthlySalaryInput.salary_period == "2026-07"
    ).all()
    assert july_before_approval
    assert all(item.is_published is False for item in july_before_approval)

    requested = client.post("/api/salary/approval/request", json={"period": "2026-07"})
    assert requested.status_code == 200
    assert requested.json()["status"] == "PENDING_APPROVAL"
    assert requested.json()["notified_count"] == 3

    approval_notifications = db_session.query(Notification).filter(
        Notification.event_type == "PAYROLL_APPROVAL_REQUESTED",
        Notification.resource_id == "2026-07",
    ).all()
    assert {item.target_user_id for item in approval_notifications} == {
        director_one_id,
        director_two_id,
        it_admin_id,
    }
    assert all(item.actor_user_id == chief_id for item in approval_notifications)
    assert all(item.action_url == "/admin/salary-matrix" for item in approval_notifications)

    chief_cannot_approve = client.post("/api/salary/approval/approve", json={"period": "2026-07"})
    assert chief_cannot_approve.status_code == 403

    authenticate(director_one_id, "director.one", DIRECTOR)
    approved = client.post("/api/salary/approval/approve", json={"period": "2026-07"})
    assert approved.status_code == 200
    assert approved.json()["status"] == "APPROVED"
    assert approved.json()["published_count"] >= 1

    db_session.expire_all()
    workflow = db_session.query(SalaryApprovalWorkflow).filter(
        SalaryApprovalWorkflow.salary_period == "2026-07"
    ).one()
    assert workflow.confirmed_by_user_id == chief_id
    assert workflow.requested_by_user_id == chief_id
    assert workflow.approved_by_user_id == director_one_id

    payslip_notification = db_session.query(Notification).filter(
        Notification.event_type == "PAYSLIP_PUBLISHED",
        Notification.target_user_id == employee_user_id,
        Notification.resource_id == "2026-07",
    ).one()
    assert payslip_notification.action_url == "/user/my-payslip"

    periods = client.get("/api/salary/periods")
    assert periods.status_code == 200
    rows = periods.json()
    assert [row["period"] for row in rows[:2]] == ["2026-08", "2026-07"]
    by_period = {row["period"]: row for row in rows}
    assert by_period["2026-07"]["is_published"] is True
    assert by_period["2026-08"]["is_published"] is False
    assert by_period["2026-07"]["approval_status"] == "APPROVED"
    assert by_period["2026-08"]["approval_status"] == "DRAFT"
    assert by_period["2026-07"]["input_count"] >= 1

    july_inputs = client.get("/api/salary/inputs", params={"period": "2026-07"})
    assert july_inputs.status_code == 200
    july_employee = next(row for row in july_inputs.json() if row["employee_id"] == employee_id)
    assert july_employee["is_published"] is True

    revised = client.post(
        "/api/salary/inputs",
        json={
            "employee_id": employee_id,
            "salary_period": "2026-07",
            "bonus": 1_234_567,
        },
    )
    assert revised.status_code == 200
    assert revised.json()[0]["is_published"] is True
    assert revised.json()[0]["bonus"] == 1_234_567

    revised_payslip_data = client.get("/api/salary/inputs", params={"period": "2026-07"})
    assert revised_payslip_data.status_code == 200
    revised_employee = next(row for row in revised_payslip_data.json() if row["employee_id"] == employee_id)
    assert revised_employee["is_published"] is True
    assert revised_employee["bonus"] == 1_234_567

    legacy_publish = client.post(
        "/api/salary/publish",
        json={"period": "2026-08", "is_published": True},
    )
    assert legacy_publish.status_code == 409


def test_employee_salary_crud(client):
    # 1. Create an employee first
    emp_payload = {
        "machine_employee_id": "E800",
        "full_name": "Test Salary Employee",
        "notion_name": "TEST SALARY EMP",
    }
    create_emp_res = client.post("/api/employees", json=emp_payload)
    assert create_emp_res.status_code == 200
    emp_id = create_emp_res.json()["id"]

    # 2. Get employee via salary endpoint
    get_res = client.get("/api/salary/employees", params={"q": "TEST SALARY"})
    assert get_res.status_code == 200
    employees = get_res.json()
    assert len(employees) >= 1
    target_emp = next(e for e in employees if e["id"] == emp_id)
    assert target_emp["contract_salary"] == 0
    assert target_emp["employee_type"] == "FULLTIME"

    # 3. Update employee salary fields
    update_payload = {
        "employee_code": "CODE800",
        "fullname": "Test Salary Employee Updated",
        "position": "Senior Developer",
        "contract_salary": 65000000,
        "employee_type": "FULLTIME",
        "dependents_count": 2,
        "account_number": "123456789",
        "bank_name": "Vietcombank",
    }
    put_res = client.put(f"/api/salary/employees/{emp_id}", json=update_payload)
    assert put_res.status_code == 200
    updated = put_res.json()
    assert updated["employee_code"] == "CODE800"
    assert updated["fullname"] == "Test Salary Employee Updated"
    assert updated["position"] == "Senior Developer"
    assert updated["contract_salary"] == 65000000
    assert updated["dependents_count"] == 2
    assert updated["account_number"] == "123456789"
    assert updated["bank_name"] == "Vietcombank"

    # 4. Create monthly salary input
    input_payload = {
        "employee_id": emp_id,
        "salary_period": "2026-05",
        "actual_working_days": 21.5,
        "meal_allowance_free": 1200000,
        "phone_allowance_free": 500000,
        "perf_allowance_tax": 3000000,
        "bonus": 10000000,
        "advance_payment": 2000000,
    }
    post_res = client.post("/api/salary/inputs", json=input_payload)
    assert post_res.status_code == 200
    created_inputs = post_res.json()
    assert len(created_inputs) == 1
    input_item = created_inputs[0]
    input_id = input_item["id"]
    assert input_item["actual_working_days"] == 21.5
    assert input_item["perf_allowance_tax"] == 3000000
    assert input_item["salary_period"] == "2026-05"

    # 5. Get list of inputs filtered by period
    get_inputs_res = client.get("/api/salary/inputs", params={"period": "2026-05"})
    assert get_inputs_res.status_code == 200
    inputs = get_inputs_res.json()
    assert len(inputs) >= 1
    assert any(x["id"] == input_id for x in inputs)

    # 6. Update single input record
    update_input_payload = {
        "actual_working_days": 22.0,
        "bonus": 12000000,
    }
    put_input_res = client.put(f"/api/salary/inputs/{input_id}", json=update_input_payload)
    assert put_input_res.status_code == 200
    updated_input = put_input_res.json()
    assert updated_input["actual_working_days"] == 22.0
    assert updated_input["bonus"] == 12000000

    # 7. Upsert (update existing via POST)
    upsert_payload = {
        "employee_id": emp_id,
        "salary_period": "2026-05",
        "actual_working_days": 20.0,
        "bonus": 5000000,
    }
    post_upsert_res = client.post("/api/salary/inputs", json=upsert_payload)
    assert post_upsert_res.status_code == 200
    upserted_inputs = post_upsert_res.json()
    assert len(upserted_inputs) == 1
    upserted_item = upserted_inputs[0]
    assert upserted_item["id"] == input_id
    assert upserted_item["actual_working_days"] == 20.0
    assert upserted_item["bonus"] == 5000000

    # 7.5 Test export endpoint
    export_res = client.get("/api/salary/export", params={"period": "2026-05"})
    assert export_res.status_code == 200
    assert "content-disposition" in export_res.headers
    assert "salary_table_2026-05.xlsx" in export_res.headers["content-disposition"]

    # 8. Delete input
    delete_res = client.delete(f"/api/salary/inputs/{input_id}")
    assert delete_res.status_code == 204

    # Verify deleted
    get_deleted_res = client.get("/api/salary/inputs", params={"period": "2026-05"})
    assert get_deleted_res.status_code == 200
    assert not any(x["id"] == input_id for x in get_deleted_res.json())


def test_salary_input_defaults_to_employee_approved_timesheet_days(client, db_session):
    created = client.post(
        "/api/employees",
        json={
            "machine_employee_id": "E801",
            "full_name": "Attendance Driven Salary",
            "notion_name": "ATTENDANCE DRIVEN SALARY",
            "contract_salary": 22_000_000,
        },
    )
    assert created.status_code == 200
    employee_id = created.json()["id"]
    db_session.add(
        Timesheet(
            employee_id=employee_id,
            period_start=date(2026, 7, 23),
            period_end=date(2026, 8, 22),
            approval_status="approved",
            total_work_days=7,
            total_paid_leave_days=0.5,
            total_payroll_days=9.25,
        )
    )
    db_session.commit()

    response = client.get("/api/salary/inputs", params={"period": "2026-08"})
    assert response.status_code == 200
    row = next(item for item in response.json() if item["employee_id"] == employee_id)
    assert row["actual_working_days"] == 9.25

    # Salary must use the accountant-approved "Ngày công" value (9.25),
    # not the raw attendance value "Ngày công TT" (7).
    calculated = cake_salary(
        {
            "type": "FULLTIME",
            "contract_salary": 22_000_000,
            "actual_working_days": row["actual_working_days"],
            "standard_working_days": calculate_period_working_days("2026-08"),
        }
    )
    assert calculated["actual_salary"] == 9_250_000

    materialized = client.post(
        "/api/salary/inputs",
        json={"employee_id": employee_id, "salary_period": "2026-08"},
    )
    assert materialized.status_code == 200
    assert materialized.json()[0]["actual_working_days"] == 9.25


def test_salary_policy_snapshot_supports_multiple_employee_rows(client, db_session):
    policy = ensure_default_salary_policy(db_session)
    employees = [
        Employee(machine_employee_id="POLICY-01", full_name="Policy Employee One"),
        Employee(machine_employee_id="POLICY-02", full_name="Policy Employee Two"),
    ]
    db_session.add_all(employees)
    db_session.flush()
    db_session.add_all(
        [
            MonthlySalaryInput(
                employee_id=employee.id,
                salary_period="2026-08",
                salary_policy_id=policy.id,
                actual_working_days=22,
            )
            for employee in employees
        ]
    )
    db_session.commit()

    response = client.get("/api/salary/policy", params={"period": "2026-08"})
    assert response.status_code == 200
    assert response.json()["snapshot"] is True
    assert response.json()["policy"]["id"] == policy.id

    export_policy = resolve_export_salary_policy(db_session, "2026-08")
    assert export_policy["id"] == policy.id


def test_other_income_evidence_round_trip(client):
    created = client.post(
        "/api/employees",
        json={
            "machine_employee_id": "E899",
            "full_name": "Other Income Employee",
            "notion_name": "OTHER INCOME EMPLOYEE",
        },
    )
    assert created.status_code == 200
    employee_id = created.json()["id"]

    missing_reason = client.post(
        f"/api/salary/other-income-evidence/{employee_id}",
        data={"period": "2026-08", "other_income": "750000", "note": ""},
    )
    assert missing_reason.status_code == 422

    saved = client.post(
        f"/api/salary/other-income-evidence/{employee_id}",
        data={
            "period": "2026-08",
            "other_income": "750000",
            "note": "Hỗ trợ dự án theo quyết định nội bộ",
        },
        files={"document": ("quyet-dinh.pdf", b"%PDF-1.4 test evidence", "application/pdf")},
    )
    assert saved.status_code == 200
    body = saved.json()
    assert body["other_income"] == 750000
    assert body["other_income_note"] == "Hỗ trợ dự án theo quyết định nội bộ"
    assert body["other_income_document_name"] == "quyet-dinh.pdf"
    assert "other_income_document_path" not in body

    salary_inputs = client.get("/api/salary/inputs", params={"period": "2026-08"})
    assert salary_inputs.status_code == 200
    saved_input = next(row for row in salary_inputs.json() if row["employee_id"] == employee_id)
    assert saved_input["other_income"] == 750000
    assert saved_input["other_income_note"] == "Hỗ trợ dự án theo quyết định nội bộ"
    assert saved_input["other_income_document_name"] == "quyet-dinh.pdf"
    assert "other_income_document_path" not in saved_input

    downloaded = client.get(
        f"/api/salary/other-income-evidence/{employee_id}/file",
        params={"period": "2026-08"},
    )
    assert downloaded.status_code == 200
    assert downloaded.content == b"%PDF-1.4 test evidence"
    assert "quyet-dinh.pdf" in downloaded.headers["content-disposition"]

    deleted = client.delete(
        f"/api/salary/other-income-evidence/{employee_id}/file",
        params={"period": "2026-08"},
    )
    assert deleted.status_code == 204
    assert client.get(
        f"/api/salary/other-income-evidence/{employee_id}/file",
        params={"period": "2026-08"},
    ).status_code == 404


def test_employee_type_change_from_salary_period_preserves_history_and_propagates(client, db_session):
    """A type selected for one payroll period applies from that period forward only."""
    created = client.post(
        "/api/employees",
        json={
            "machine_employee_id": "E801",
            "full_name": "Type Timeline Employee",
            "notion_name": "TYPE TIMELINE EMPLOYEE",
        },
    )
    assert created.status_code == 200
    employee_id = created.json()["id"]

    # Simulate legacy snapshots that still say FULLTIME in both an old and a
    # future row. The timeline must supersede the future legacy snapshot.
    db_session.add_all(
        [
            MonthlySalaryInput(
                employee_id=employee_id,
                salary_period="2026-06",
                employee_type="FULLTIME",
                meal_allowance_free=1_200_000,
                phone_allowance_free=2_000_000,
                trans_allowance_tax=2_000_000,
            ),
            MonthlySalaryInput(
                employee_id=employee_id,
                salary_period="2026-08",
                employee_type="FULLTIME",
                meal_allowance_free=1_200_000,
                phone_allowance_free=2_000_000,
                trans_allowance_tax=2_000_000,
            ),
        ]
    )
    db_session.commit()

    changed = client.put(
        f"/api/salary/employees/{employee_id}",
        params={"period": "2026-07"},
        json={"employee_type": "PROBATION"},
    )
    assert changed.status_code == 200

    june = client.get("/api/salary/employees", params={"period": "2026-06"}).json()
    july = client.get("/api/salary/employees", params={"period": "2026-07"}).json()
    august = client.get("/api/salary/employees", params={"period": "2026-08"}).json()
    assert next(row for row in june if row["id"] == employee_id)["employee_type"] == "FULLTIME"
    assert next(row for row in july if row["id"] == employee_id)["employee_type"] == "PROBATION"
    assert next(row for row in august if row["id"] == employee_id)["employee_type"] == "PROBATION"

    august_inputs = client.get("/api/salary/inputs", params={"period": "2026-08"}).json()
    august_input = next(row for row in august_inputs if row["employee_id"] == employee_id)
    assert august_input["meal_allowance_free"] == 0
    assert august_input["phone_allowance_free"] == 0
    assert august_input["trans_allowance_tax"] == 0


def test_departed_employee_requires_real_timesheet_days_in_new_salary_period(client, db_session):
    active_employee = Employee(
        machine_employee_id="PAY-ACTIVE",
        full_name="Active Payroll Employee",
        is_active=True,
        status="ACTIVE",
    )
    departed_without_work = Employee(
        machine_employee_id="PAY-LEFT-NO-WORK",
        full_name="Departed Without Work",
        is_active=False,
        status="RESIGNED",
        resignation_period="2026-08",
    )
    departed_with_work = Employee(
        machine_employee_id="PAY-LEFT-WITH-WORK",
        full_name="Departed With Work",
        is_active=False,
        status="RESIGNED",
        resignation_period="2026-08",
    )
    db_session.add_all([active_employee, departed_without_work, departed_with_work])
    db_session.flush()
    db_session.add_all(
        [
            # These legacy/default rows must not be mistaken for attendance.
            MonthlySalaryInput(
                employee_id=departed_without_work.id,
                salary_period="2026-08",
                actual_working_days=22,
            ),
            MonthlySalaryInput(
                employee_id=departed_with_work.id,
                salary_period="2026-08",
                actual_working_days=2,
            ),
            Timesheet(
                employee_id=departed_with_work.id,
                period_start=date(2026, 7, 23),
                period_end=date(2026, 8, 22),
                total_work_days=2,
                total_paid_leave_days=0,
                total_business_trip_days=0,
            ),
        ]
    )
    db_session.commit()

    salary_employees = client.get("/api/salary/employees", params={"period": "2026-08"})
    assert salary_employees.status_code == 200
    salary_employee_ids = {row["id"] for row in salary_employees.json()}
    assert active_employee.id in salary_employee_ids
    assert departed_with_work.id in salary_employee_ids
    assert departed_without_work.id not in salary_employee_ids

    salary_inputs = client.get("/api/salary/inputs", params={"period": "2026-08"})
    assert salary_inputs.status_code == 200
    salary_input_employee_ids = {row["employee_id"] for row in salary_inputs.json()}
    assert active_employee.id in salary_input_employee_ids
    assert departed_with_work.id in salary_input_employee_ids
    assert departed_without_work.id not in salary_input_employee_ids

    # Confirmation/materialisation must follow the same eligibility rule, so a
    # hidden stale row is not accidentally published later.
    from app.api.salary_api import _materialize_salary_inputs

    materialized = _materialize_salary_inputs(db_session, "2026-08")
    assert active_employee.id in materialized
    assert departed_with_work.id in materialized
    assert departed_without_work.id not in materialized
