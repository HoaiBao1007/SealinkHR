from app.models.department import Department
from app.models.employee import Employee
from app.models.organization import OrganizationAssignment, OrganizationUnit


def test_organization_chart_uses_live_department_and_assignment_metadata(client, db_session):
    docs = Department(name="DOC")
    export = Department(name="DOC - EXPORT", parent=docs, sort_order=10)
    db_session.add_all([docs, export])
    db_session.flush()

    leader = Employee(
        machine_employee_id="ORG-001",
        employee_code="SL001",
        full_name="Nguyễn Trưởng Nhóm",
        notion_name="LEADER",
        position="Trưởng nhóm",
        company_email="leader@sea-link.com",
        phone_number="0901000001",
        company_phone_number="02873075768",
        department_id=export.id,
    )
    member = Employee(
        machine_employee_id="ORG-002",
        employee_code="SL002",
        full_name="Nguyễn Nhân Viên",
        notion_name="MEMBER",
        position="Nhân viên",
        company_email="member@sea-link.com",
        department_id=export.id,
    )
    new_member = Employee(
        machine_employee_id="ORG-003",
        employee_code="SL003",
        full_name="Nhân Viên Mới",
        notion_name="NEW MEMBER",
        position="Nhân viên",
        company_email="new-member@sea-link.com",
        department_id=export.id,
    )
    db_session.add_all([leader, member, new_member])
    db_session.flush()

    root_unit = OrganizationUnit(
        code="DOCS",
        name="DOCS TEAM",
        unit_type="DEPARTMENT",
        linked_department_id=docs.id,
        sort_order=10,
    )
    export_unit = OrganizationUnit(
        code="DOCS_EXPORT",
        name="EXPORT OPERATION",
        unit_type="TEAM",
        parent=root_unit,
        linked_department_id=export.id,
        leader_employee_id=leader.id,
        sort_order=20,
    )
    db_session.add_all([root_unit, export_unit])
    db_session.flush()
    db_session.add_all(
        [
            OrganizationAssignment(
                employee_id=leader.id,
                org_unit_id=export_unit.id,
                position_title="Export Supervisor",
                display_order=10,
                source="TEST",
            ),
            OrganizationAssignment(
                employee_id=member.id,
                org_unit_id=export_unit.id,
                reports_to_employee_id=leader.id,
                position_title="Export Executive",
                display_order=20,
                source="TEST",
            ),
        ]
    )
    db_session.commit()

    response = client.get("/api/organization/chart")
    assert response.status_code == 200
    payload = response.json()
    assert payload["employee_count"] == 3

    export_payload = next(unit for unit in payload["units"] if unit["code"] == "DOCS_EXPORT")
    assert export_payload["parent_id"] == root_unit.id
    assert [member["full_name"] for member in export_payload["members"]] == [
        "Nguyễn Trưởng Nhóm",
        "Nguyễn Nhân Viên",
        "Nhân Viên Mới",
    ]
    assert export_payload["members"][0]["position_title"] == "Export Supervisor"
    assert export_payload["members"][0]["phone_number"] == "0901000001"
    assert export_payload["members"][0]["company_phone_number"] == "02873075768"
    assert export_payload["members"][1]["reports_to_employee_id"] == leader.id
    assert export_payload["members"][2]["source"] == "DEPARTMENT"


def test_departed_employees_are_removed_from_chart_and_department_members(client, db_session):
    department = Department(name="CURRENT TEAM")
    db_session.add(department)
    db_session.flush()

    active_employee = Employee(
        machine_employee_id="ORG-ACTIVE",
        full_name="Current Employee",
        department_id=department.id,
        is_active=True,
        status="ACTIVE",
    )
    resigned_employee = Employee(
        machine_employee_id="ORG-RESIGNED",
        full_name="Resigned Employee",
        department_id=department.id,
        is_active=True,
        status="RESIGNED",
        resignation_period="2026-08",
    )
    inactive_employee = Employee(
        machine_employee_id="ORG-INACTIVE",
        full_name="Inactive Employee",
        department_id=department.id,
        is_active=False,
        status="INACTIVE",
    )
    db_session.add_all([active_employee, resigned_employee, inactive_employee])
    db_session.flush()
    department.manager_id = resigned_employee.id

    unit = OrganizationUnit(
        code="CURRENT_TEAM",
        name="CURRENT TEAM",
        unit_type="DEPARTMENT",
        linked_department_id=department.id,
    )
    db_session.add(unit)
    db_session.commit()

    chart_response = client.get("/api/organization/chart")
    assert chart_response.status_code == 200
    chart_payload = chart_response.json()
    assert chart_payload["employee_count"] == 1
    unit_payload = next(row for row in chart_payload["units"] if row["code"] == "CURRENT_TEAM")
    assert [row["employee_id"] for row in unit_payload["members"]] == [active_employee.id]

    departments_response = client.get("/api/departments")
    assert departments_response.status_code == 200
    department_payload = next(row for row in departments_response.json() if row["id"] == department.id)
    assert department_payload["manager"] is None
    assert [row["id"] for row in department_payload["employees"]] == [active_employee.id]
