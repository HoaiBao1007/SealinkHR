from app.core.roles import ADMIN, DIRECTOR, HR_ADMIN, IT_ADMIN, USER
from app.models.department import Department
from app.models.employee import Employee
from app.models.organization import OrganizationAssignment, OrganizationUnit
from app.models.user import User
from app.services.access_role_service import (
    infer_employee_access_role,
    sync_employee_access_role,
)


def _employee_with_assignment(db_session, *, name: str, title: str, user_role: str = USER):
    department = db_session.query(Department).filter(Department.name == "IT").one_or_none()
    if department is None:
        department = Department(name="IT")
        db_session.add(department)
        db_session.flush()
    employee = Employee(
        machine_employee_id=f"ROLE-{name}",
        full_name=name,
        department_id=department.id,
        department_name="IT",
        position="IT",
    )
    user = User(username=f"user_{name}", password_hash="hash", role=user_role)
    db_session.add_all([employee, user])
    db_session.flush()
    employee.user_id = user.id
    unit = OrganizationUnit(
        code=f"IT-ADMIN-{name}",
        name="IT & ADMIN TEAM",
        unit_type="TEAM",
        linked_department_id=department.id,
    )
    db_session.add(unit)
    db_session.flush()
    db_session.add(
        OrganizationAssignment(
            employee_id=employee.id,
            org_unit_id=unit.id,
            position_title=title,
            source="TEST",
        )
    )
    db_session.flush()
    return employee, user


def test_personal_it_account_is_user_because_it_uses_shared_admin(db_session):
    employee, user = _employee_with_assignment(
        db_session,
        name="IT Executive",
        title="IT Executive",
        user_role=IT_ADMIN,
    )
    role, _, changed = sync_employee_access_role(db_session, employee)
    assert role == USER
    assert changed is True
    assert user.role == USER


def test_admin_sealink_is_the_shared_it_admin_account(db_session):
    employee, user = _employee_with_assignment(
        db_session,
        name="Shared IT",
        title="IT Executive",
        user_role=ADMIN,
    )
    user.username = "admin_sealink"
    role, reason, changed = sync_employee_access_role(db_session, employee)
    assert role == IT_ADMIN
    assert "Backup" in reason
    assert changed is True
    assert user.role == IT_ADMIN


def test_admin_title_is_derived_as_hr_admin(db_session):
    employee, user = _employee_with_assignment(
        db_session,
        name="Luna",
        title="Admin",
    )
    role, _ = infer_employee_access_role(db_session, employee)
    sync_employee_access_role(db_session, employee)
    assert role == HR_ADMIN
    assert user.role == HR_ADMIN


def test_employee_outside_it_department_is_user_even_with_old_it_assignment(db_session):
    employee, user = _employee_with_assignment(
        db_session,
        name="Moved",
        title="IT Executive",
        user_role=IT_ADMIN,
    )
    other = Department(name="SALES")
    db_session.add(other)
    db_session.flush()
    employee.department_id = other.id
    employee.department_name = other.name
    role, _, changed = sync_employee_access_role(db_session, employee)
    assert role == USER
    assert changed is True
    assert user.role == USER


def test_chief_accountant_role_is_never_changed(db_session):
    employee, user = _employee_with_assignment(
        db_session,
        name="Chief",
        title="IT Executive",
        user_role=ADMIN,
    )
    user.username = "chief_accountant"
    role, _, changed = sync_employee_access_role(db_session, employee)
    assert role == ADMIN
    assert changed is False
    assert user.role == ADMIN


def test_named_directors_inherit_chief_accountant_business_role(db_session):
    for index, full_name in enumerate(("Tôn Thất Trung Kiên", "Tô Tố Vân"), start=1):
        employee, user = _employee_with_assignment(
            db_session,
            name=f"director-{index}",
            title="Director",
            user_role=USER,
        )
        employee.full_name = full_name

        role, reason, changed = sync_employee_access_role(db_session, employee)

        assert role == DIRECTOR
        assert "Giám đốc" in reason
        assert changed is True
        assert user.role == DIRECTOR


def test_hr_employee_account_creation_uses_organization_role(client, db_session):
    department = Department(name="IT")
    employee = Employee(
        machine_employee_id="ROLE-HR-CREATE",
        full_name="HR Account",
        department_name="IT",
        position="Admin",
    )
    db_session.add_all([department, employee])
    db_session.flush()
    employee.department_id = department.id
    unit = OrganizationUnit(
        code="IT-ADMIN-HR-CREATE",
        name="IT & ADMIN TEAM",
        unit_type="TEAM",
        linked_department_id=department.id,
    )
    db_session.add(unit)
    db_session.flush()
    db_session.add(
        OrganizationAssignment(
            employee_id=employee.id,
            org_unit_id=unit.id,
            position_title="Admin",
            source="TEST",
        )
    )
    db_session.commit()

    response = client.patch(
        f"/api/hr/employees/{employee.id}",
        json={
            "username": "hr_account",
            "password": "StrongPassword123!",
        },
    )

    assert response.status_code == 200
    assert response.json()["account_role"] == HR_ADMIN
    stored = db_session.query(User).filter(User.username == "hr_account").one()
    assert stored.role == HR_ADMIN
