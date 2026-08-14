from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session, joinedload

from app.api.deps import get_hr_manager_user, get_db
from app.models.employee import Employee
from app.models.organization import OrganizationAssignment, OrganizationUnit


router = APIRouter(
    tags=["organization"],
    dependencies=[Depends(get_hr_manager_user)],
)


class OrganizationChartMember(BaseModel):
    assignment_id: int | None = None
    employee_id: int
    full_name: str
    notion_name: str | None = None
    employee_code: str | None = None
    position_title: str | None = None
    company_email: str | None = None
    phone_number: str | None = None
    company_phone_number: str | None = None
    department_name: str | None = None
    reports_to_employee_id: int | None = None
    display_order: int = 0
    source: str = "DEPARTMENT"


class OrganizationChartUnit(BaseModel):
    id: int
    code: str
    name: str
    unit_type: str
    parent_id: int | None = None
    linked_department_id: int | None = None
    leader_employee_id: int | None = None
    color: str | None = None
    sort_order: int = 0
    members: list[OrganizationChartMember]


class OrganizationChartResponse(BaseModel):
    generated_at: datetime
    units: list[OrganizationChartUnit]
    employee_count: int


@router.get("/api/organization/chart", response_model=OrganizationChartResponse)
def get_organization_chart(db: Session = Depends(get_db)) -> OrganizationChartResponse:
    """Return the live organization chart.

    The employee's current department is authoritative. The historical
    organization assignment supplies display order, title and reporting data
    when it still points to the same unit. This makes a newly assigned employee
    appear on the chart immediately without rewriting organization history.
    """

    units = (
        db.query(OrganizationUnit)
        .filter(OrganizationUnit.is_active.is_(True))
        .order_by(OrganizationUnit.sort_order, OrganizationUnit.id)
        .all()
    )
    units_by_id = {unit.id: unit for unit in units}
    unit_by_department_id = {
        unit.linked_department_id: unit
        for unit in units
        if unit.linked_department_id is not None
    }

    current_assignments: dict[int, OrganizationAssignment] = {}
    assignments = (
        db.query(OrganizationAssignment)
        .filter(OrganizationAssignment.effective_to.is_(None))
        .order_by(OrganizationAssignment.id)
        .all()
    )
    for assignment in assignments:
        current_assignments[assignment.employee_id] = assignment

    members_by_unit_id: dict[int, list[OrganizationChartMember]] = {
        unit.id: [] for unit in units
    }
    employees = (
        db.query(Employee)
        .options(joinedload(Employee.department))
        .filter(Employee.is_active.is_(True))
        .order_by(Employee.id)
        .all()
    )

    included_employee_count = 0
    for employee in employees:
        assignment = current_assignments.get(employee.id)
        target_unit = unit_by_department_id.get(employee.department_id)
        if target_unit is None and assignment is not None:
            target_unit = units_by_id.get(assignment.org_unit_id)
        if target_unit is None:
            continue

        assignment_matches_unit = (
            assignment is not None and assignment.org_unit_id == target_unit.id
        )
        members_by_unit_id[target_unit.id].append(
            OrganizationChartMember(
                assignment_id=assignment.id if assignment_matches_unit else None,
                employee_id=employee.id,
                full_name=employee.full_name,
                notion_name=employee.notion_name,
                employee_code=employee.employee_code or employee.machine_employee_id,
                position_title=(
                    assignment.position_title
                    if assignment_matches_unit and assignment.position_title
                    else employee.position
                ),
                company_email=employee.company_email,
                phone_number=employee.phone_number,
                company_phone_number=employee.company_phone_number,
                department_name=employee.department.name if employee.department else None,
                reports_to_employee_id=(
                    assignment.reports_to_employee_id if assignment_matches_unit else None
                ),
                display_order=(
                    assignment.display_order if assignment_matches_unit else 10_000 + employee.id
                ),
                source=assignment.source if assignment_matches_unit else "DEPARTMENT",
            )
        )
        included_employee_count += 1

    payload_units: list[OrganizationChartUnit] = []
    for unit in units:
        members = members_by_unit_id[unit.id]
        members.sort(
            key=lambda member: (
                member.employee_id != unit.leader_employee_id,
                member.display_order,
                member.full_name.casefold(),
            )
        )
        payload_units.append(
            OrganizationChartUnit(
                id=unit.id,
                code=unit.code,
                name=unit.name,
                unit_type=unit.unit_type,
                parent_id=unit.parent_id,
                linked_department_id=unit.linked_department_id,
                leader_employee_id=unit.leader_employee_id,
                color=unit.color,
                sort_order=unit.sort_order,
                members=members,
            )
        )

    return OrganizationChartResponse(
        generated_at=datetime.now(timezone.utc),
        units=payload_units,
        employee_count=included_employee_count,
    )
