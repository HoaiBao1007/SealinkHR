from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
import unicodedata

from sqlalchemy.orm import Session

from app.models.department import Department
from app.models.employee import Employee
from app.models.organization import OrganizationAssignment, OrganizationUnit


PDF_SOURCE = "PDF_ORG_CHART_2026_07_01"
NOTION_SOURCE = "NOTION_EMPLOYEE_EXPORT_2026_07"
SYSTEM_SOURCE = "SYSTEM_MAPPING"
ORG_EFFECTIVE_DATE = date(2026, 7, 1)

DOC_PARENT_DEPARTMENT = "DOC"
DOC_SCRAP_DEPARTMENT = "DOC - SCRAP COMMODITY OPERATION"
DOC_PRICING_CS_DEPARTMENT = "DOC - PRICING & CUSTOMER SERVICE"
DOC_EXPORT_DEPARTMENT = "DOC - EXPORT OPERATION"
DOC_IMPORT_DEPARTMENT = "DOC - IMPORT OPERATION"
DOC_CUSTOMS_DEPARTMENT = "DOC - CUSTOMS"
DOC_CHILD_UNIT_CODES = frozenset(
    {
        "DOCS_SCRAP",
        "DOCS_PRICING_CS",
        "DOCS_EXPORT",
        "DOCS_IMPORT",
        "DOCS_CUSTOMS",
    }
)


@dataclass(frozen=True)
class UnitDefinition:
    code: str
    name: str
    unit_type: str
    parent_code: str | None
    linked_department_name: str | None
    leader_name: str | None
    color: str
    sort_order: int


@dataclass(frozen=True)
class Placement:
    unit_code: str
    department_name: str
    position_title: str | None
    display_order: int
    source: str = PDF_SOURCE
    confidence: Decimal = Decimal("1.000")


UNIT_DEFINITIONS: tuple[UnitDefinition, ...] = (
    UnitDefinition("COMPANY", "SEALINK INTERNATIONAL", "COMPANY", None, None, None, "#0F172A", 0),
    UnitDefinition(
        "EXECUTIVE",
        "BAN ĐIỀU HÀNH",
        "EXECUTIVE",
        "COMPANY",
        "MANAGEMENT",
        "Tôn Thất Trung Kiên",
        "#F97316",
        10,
    ),
    UnitDefinition(
        "OVERSEAS",
        "OVERSEAS TEAM",
        "DEPARTMENT",
        "COMPANY",
        "SALE OVERSEA",
        "Nguyễn Trần Phương",
        "#17347A",
        20,
    ),
    UnitDefinition(
        "SALES",
        "SALES TEAM",
        "DEPARTMENT",
        "COMPANY",
        "SALE LOCAL",
        "Phạm Đỗ Hạnh Quyên",
        "#2596C8",
        30,
    ),
    UnitDefinition(
        "DOCS",
        "DOCS TEAM",
        "DEPARTMENT",
        "COMPANY",
        "DOC",
        "Đỗ Vương Bằng Lăng",
        "#00B817",
        40,
    ),
    UnitDefinition(
        "DOCS_SCRAP",
        "SCRAP COMMODITY OPERATION",
        "TEAM",
        "DOCS",
        DOC_SCRAP_DEPARTMENT,
        None,
        "#00B817",
        41,
    ),
    UnitDefinition(
        "DOCS_PRICING_CS",
        "PRICING & CUSTOMER SERVICE",
        "TEAM",
        "DOCS",
        DOC_PRICING_CS_DEPARTMENT,
        "Đặng Quế Quyên",
        "#00B817",
        42,
    ),
    UnitDefinition(
        "DOCS_EXPORT",
        "EXPORT OPERATION",
        "TEAM",
        "DOCS",
        DOC_EXPORT_DEPARTMENT,
        "Võ Thị Bích",
        "#00B817",
        43,
    ),
    UnitDefinition(
        "DOCS_IMPORT",
        "IMPORT OPERATION",
        "TEAM",
        "DOCS",
        DOC_IMPORT_DEPARTMENT,
        "Nguyễn Thị Như",
        "#00B817",
        44,
    ),
    UnitDefinition(
        "DOCS_CUSTOMS",
        "CUSTOMS",
        "TEAM",
        "DOCS",
        DOC_CUSTOMS_DEPARTMENT,
        "Nguyễn Thị Xuân Dung",
        "#00B817",
        45,
    ),
    UnitDefinition(
        "ACCOUNTING",
        "ACCOUNTING TEAM",
        "DEPARTMENT",
        "COMPANY",
        "ACCOUNTING",
        "Nguyễn Lý Tưởng",
        "#9333EA",
        50,
    ),
    UnitDefinition(
        "IT_ADMIN",
        "IT & ADMIN TEAM",
        "DEPARTMENT",
        "COMPANY",
        "IT",
        "Nguyễn Thanh Đạt",
        "#FF4D5E",
        60,
    ),
    UnitDefinition(
        "UNASSIGNED",
        "CHƯA PHÂN NHÓM",
        "UNASSIGNED",
        "COMPANY",
        "CHƯA PHÂN NHÓM",
        None,
        "#94A3B8",
        99,
    ),
)


def _placements(
    unit_code: str,
    department_name: str,
    rows: tuple[tuple[str, str | None], ...],
    *,
    source: str = PDF_SOURCE,
    confidence: str = "1.000",
) -> dict[str, Placement]:
    return {
        name: Placement(
            unit_code=unit_code,
            department_name=department_name,
            position_title=title,
            display_order=(index + 1) * 10,
            source=source,
            confidence=Decimal(confidence),
        )
        for index, (name, title) in enumerate(rows)
    }


EMPLOYEE_PLACEMENTS: dict[str, Placement] = {
    **_placements(
        "EXECUTIVE",
        "MANAGEMENT",
        (
            ("Tôn Thất Trung Kiên", "Owners Representative"),
            ("Tô Tố Vân", "Branch Manager"),
        ),
    ),
    **_placements(
        "OVERSEAS",
        "SALE OVERSEA",
        (
            ("Nguyễn Trần Phương", "Overseas Sales Manager"),
            ("Nguyễn Thị Thanh Hương", "Overseas Sales Supervisor"),
            ("Phạm Thị Thúy Ngân", "Overseas Sales Supervisor"),
            ("Hồ Ngọc Ngàn", "Overseas Sales Executive"),
            ("Phan Minh Quân", "Overseas Sales Executive"),
        ),
    ),
    **_placements(
        "SALES",
        "SALE LOCAL",
        (
            ("Phạm Đỗ Hạnh Quyên", "Sales Manager"),
            ("Nguyễn Thành Trung", "Assistant Sales Manager"),
            ("Nguyễn Tuyết Nga", "Sales Supervisor"),
            ("Phan Quốc Long", "Sales Supervisor"),
            ("Vũ Minh Quang", "Sales Supervisor"),
            ("Nguyễn Trần Gia Bảo", "Sales Executive"),
            ("Trương Gia Tuệ", "Sales Executive"),
            ("Hồ Đăng Nhật", "Sales Executive"),
            ("Nguyễn Quốc Thiện", "Sales Executive"),
        ),
    ),
    **_placements(
        "DOCS",
        DOC_PARENT_DEPARTMENT,
        (("Đỗ Vương Bằng Lăng", "Operation Manager"),),
    ),
    **_placements(
        "DOCS_SCRAP",
        DOC_SCRAP_DEPARTMENT,
        (
            ("Dương Nguyễn Vũ Phong", "Import Operation Executive"),
            ("Trần Đình Quang", "Import Operation Executive"),
        ),
    ),
    **_placements(
        "DOCS_PRICING_CS",
        DOC_PRICING_CS_DEPARTMENT,
        (
            ("Đặng Quế Quyên", "Export Pricing Manager"),
            ("Nguyễn Quốc Thái Dương", "Export Pricing Executive"),
            ("Hoàng Thanh Thảo", "Export Pricing Executive"),
            ("Nguyễn Lê Ngọc Hoa", "Export Pricing Executive"),
            ("Lý Kiến Tường", "Export Pricing Executive - Intern"),
        ),
    ),
    **_placements(
        "DOCS_EXPORT",
        DOC_EXPORT_DEPARTMENT,
        (
            ("Võ Thị Bích", "Export Operation Supervisor"),
            ("Nguyễn Quỳnh Khả Tú", "Export Operation Executive"),
            ("Lê Yến Phương", "Export Operation Executive"),
            ("Lê Nguyễn Thảo Nga", "Export Operation Executive"),
            ("Lê Trần Phương Hạ", "Export Operation Executive"),
            ("Nguyễn Hồng Ngọc", "Export Document Staff"),
        ),
    ),
    **_placements(
        "DOCS_EXPORT",
        DOC_EXPORT_DEPARTMENT,
        (
            ("Trần Thụy Mai Uyên", "Export Documentation Executive"),
            ("Đặng Quốc Thịnh", "Export Operation Executive"),
        ),
        source=NOTION_SOURCE,
        confidence="0.950",
    ),
    **_placements(
        "DOCS_IMPORT",
        DOC_IMPORT_DEPARTMENT,
        (
            ("Nguyễn Thị Như", "Import Documentation Supervisor"),
            ("Lê Thanh Quỳnh Vân", "Senior Import Specialist"),
            ("Nguyễn Trần Khả Nhi", "Import Operation Executive"),
            ("Nguyễn Trúc Vân", "Import Documentation Executive"),
        ),
    ),
    **_placements(
        "DOCS_IMPORT",
        DOC_IMPORT_DEPARTMENT,
        (("Nguyễn Hoàng Diệu", "Import Operation Executive"),),
        source=NOTION_SOURCE,
        confidence="0.950",
    ),
    **_placements(
        "DOCS_CUSTOMS",
        DOC_CUSTOMS_DEPARTMENT,
        (
            ("Nguyễn Thị Xuân Dung", "Customs Supervisor"),
            ("Vũ Đức Bảo", "Customs Supervisor"),
            ("Nguyễn Ngọc Hòa", "Customs Executive"),
            ("Lê Thị Khánh Linh", "Customs Executive"),
            ("Phạm Thành Tâm", "Customs Executive"),
        ),
    ),
    **_placements(
        "DOCS_CUSTOMS",
        DOC_CUSTOMS_DEPARTMENT,
        (
            ("Nguyễn Hồng Hải Thụy", "Customs Intern"),
            ("Nguyễn Thanh Nhã", "Operation Intern"),
        ),
        source=NOTION_SOURCE,
        confidence="0.900",
    ),
    **_placements(
        "ACCOUNTING",
        "ACCOUNTING",
        (
            ("Nguyễn Lý Tưởng", "AC/HR Manager"),
            ("Nguyễn Linh Chi", "Accountant"),
            ("Lê Thị Yến Nhi", "Accountant"),
            ("Lê Đình Thanh Thảo", "Accountant"),
            ("Lê Thị Mai Linh", "Accountant"),
            ("Từ Thị Linh", "Accountant"),
        ),
    ),
    **_placements(
        "IT_ADMIN",
        "IT",
        (
            ("Nguyễn Thanh Đạt", "IT Executive"),
            ("Nguyễn Thùy Loan Thảo", "Admin"),
            ("Đặng Hoài Bảo", "IT Support - Intern"),
        ),
    ),
    "SEALINK Administrator": Placement(
        unit_code="IT_ADMIN",
        department_name="IT",
        position_title="System Administrator",
        display_order=90,
        source=SYSTEM_SOURCE,
        confidence=Decimal("0.800"),
    ),
}


LEGACY_DEPARTMENT_MANAGERS: dict[str, str | None] = {
    "IT": "Nguyễn Thanh Đạt",
    "SALE LOCAL": "Phạm Đỗ Hạnh Quyên",
    "SALE OVERSEA": "Nguyễn Trần Phương",
    "DOC": "Đỗ Vương Bằng Lăng",
    DOC_SCRAP_DEPARTMENT: None,
    DOC_PRICING_CS_DEPARTMENT: "Đặng Quế Quyên",
    DOC_EXPORT_DEPARTMENT: "Võ Thị Bích",
    DOC_IMPORT_DEPARTMENT: "Nguyễn Thị Như",
    DOC_CUSTOMS_DEPARTMENT: "Nguyễn Thị Xuân Dung",
    "MANAGEMENT": "Tôn Thất Trung Kiên",
    "ACCOUNTING": "Nguyễn Lý Tưởng",
    "CHƯA PHÂN NHÓM": None,
}

DEPARTMENT_HIERARCHY: dict[str, tuple[str, int]] = {
    DOC_SCRAP_DEPARTMENT: (DOC_PARENT_DEPARTMENT, 10),
    DOC_PRICING_CS_DEPARTMENT: (DOC_PARENT_DEPARTMENT, 20),
    DOC_EXPORT_DEPARTMENT: (DOC_PARENT_DEPARTMENT, 30),
    DOC_IMPORT_DEPARTMENT: (DOC_PARENT_DEPARTMENT, 40),
    DOC_CUSTOMS_DEPARTMENT: (DOC_PARENT_DEPARTMENT, 50),
}


def normalize_name(value: str | None) -> str:
    normalized = unicodedata.normalize("NFC", value or "").strip().casefold()
    return " ".join(normalized.split())


def placement_for_employee(full_name: str) -> Placement:
    placement_by_normalized_name = {
        normalize_name(name): placement for name, placement in EMPLOYEE_PLACEMENTS.items()
    }
    placement = placement_by_normalized_name.get(normalize_name(full_name))
    if placement is not None:
        return placement
    return Placement(
        unit_code="UNASSIGNED",
        department_name="CHƯA PHÂN NHÓM",
        position_title=None,
        display_order=999,
        source=SYSTEM_SOURCE,
        confidence=Decimal("0.500"),
    )


def _preferred_employee(employees_by_name: dict[str, list[Employee]], full_name: str | None) -> Employee | None:
    if not full_name:
        return None
    matches = employees_by_name.get(normalize_name(full_name), [])
    if not matches:
        return None
    return sorted(
        matches,
        key=lambda employee: (
            not employee.is_active,
            employee.notion_name is None,
            employee.id,
        ),
    )[0]


def apply_organization_mapping(
    db: Session,
    *,
    include_unit_codes: frozenset[str] | None = None,
) -> dict[str, object]:
    employees = db.query(Employee).order_by(Employee.id).all()
    employees_by_name: dict[str, list[Employee]] = {}
    for employee in employees:
        employees_by_name.setdefault(normalize_name(employee.full_name), []).append(employee)

    departments_by_name = {
        normalize_name(department.name): department
        for department in db.query(Department).order_by(Department.id).all()
    }
    created_departments: list[str] = []
    for department_name in LEGACY_DEPARTMENT_MANAGERS:
        key = normalize_name(department_name)
        if key not in departments_by_name:
            department = Department(name=department_name)
            db.add(department)
            db.flush()
            departments_by_name[key] = department
            created_departments.append(department_name)

    for department_name, manager_name in LEGACY_DEPARTMENT_MANAGERS.items():
        manager = _preferred_employee(employees_by_name, manager_name)
        departments_by_name[normalize_name(department_name)].manager_id = manager.id if manager else None

    for department_name, (parent_name, sort_order) in DEPARTMENT_HIERARCHY.items():
        department = departments_by_name[normalize_name(department_name)]
        parent = departments_by_name[normalize_name(parent_name)]
        department.parent_id = parent.id
        department.sort_order = sort_order

    units_by_code = {
        unit.code: unit for unit in db.query(OrganizationUnit).order_by(OrganizationUnit.id).all()
    }
    created_units: list[str] = []
    for definition in UNIT_DEFINITIONS:
        unit = units_by_code.get(definition.code)
        if unit is None:
            unit = OrganizationUnit(code=definition.code, name=definition.name)
            db.add(unit)
            db.flush()
            units_by_code[definition.code] = unit
            created_units.append(definition.code)

    for definition in UNIT_DEFINITIONS:
        unit = units_by_code[definition.code]
        leader = _preferred_employee(employees_by_name, definition.leader_name)
        linked_department = (
            departments_by_name.get(normalize_name(definition.linked_department_name))
            if definition.linked_department_name
            else None
        )
        unit.name = definition.name
        unit.unit_type = definition.unit_type
        unit.parent_id = units_by_code[definition.parent_code].id if definition.parent_code else None
        unit.linked_department_id = linked_department.id if linked_department else None
        unit.leader_employee_id = leader.id if leader else None
        unit.color = definition.color
        unit.sort_order = definition.sort_order
        unit.is_active = True

    current_assignments = {
        assignment.employee_id: assignment
        for assignment in (
            db.query(OrganizationAssignment)
            .filter(OrganizationAssignment.effective_to.is_(None))
            .order_by(OrganizationAssignment.id)
            .all()
        )
    }

    assignment_counts: dict[str, int] = {}
    changed_department_count = 0
    created_assignment_count = 0
    updated_assignment_count = 0
    unassigned_names: list[str] = []
    processed_employee_count = 0

    for employee in employees:
        placement = placement_for_employee(employee.full_name)
        if include_unit_codes is not None and placement.unit_code not in include_unit_codes:
            continue
        processed_employee_count += 1
        department = departments_by_name[normalize_name(placement.department_name)]
        unit = units_by_code[placement.unit_code]
        if employee.department_id != department.id:
            employee.department_id = department.id
            changed_department_count += 1

        assignment = current_assignments.get(employee.id)
        if assignment is None:
            assignment = OrganizationAssignment(
                employee_id=employee.id,
                org_unit_id=unit.id,
                source=placement.source,
            )
            db.add(assignment)
            current_assignments[employee.id] = assignment
            created_assignment_count += 1
        else:
            updated_assignment_count += 1

        assignment.org_unit_id = unit.id
        assignment.reports_to_employee_id = None
        assignment.position_title = placement.position_title or employee.position
        assignment.display_order = placement.display_order
        assignment.source = placement.source
        assignment.confidence = placement.confidence
        assignment.effective_from = employee.start_date or ORG_EFFECTIVE_DATE
        assignment.notes = (
            "Mapped from the 01-Jul-2026 organization chart."
            if placement.source == PDF_SOURCE
            else "Mapped from supporting employee data; review when the organization chart is updated."
        )

        assignment_counts[placement.unit_code] = assignment_counts.get(placement.unit_code, 0) + 1
        if placement.unit_code == "UNASSIGNED":
            unassigned_names.append(employee.full_name)

    db.flush()
    from app.services.access_role_service import sync_all_employee_access_roles

    sync_all_employee_access_roles(db)
    return {
        "employee_count": len(employees),
        "processed_employee_count": processed_employee_count,
        "created_departments": created_departments,
        "created_units": created_units,
        "changed_department_count": changed_department_count,
        "created_assignment_count": created_assignment_count,
        "updated_assignment_count": updated_assignment_count,
        "assignment_counts": assignment_counts,
        "unassigned_names": sorted(unassigned_names),
    }
