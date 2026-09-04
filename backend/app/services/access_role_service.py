"""Derive operational access roles from the authoritative organization data."""

from __future__ import annotations

import re
import unicodedata

from sqlalchemy.orm import Session

from app.core.roles import ADMIN, DIRECTOR, HR_ADMIN, IT_ADMIN, USER
from app.models.department import Department
from app.models.employee import Employee
from app.models.organization import OrganizationAssignment, OrganizationUnit
from app.models.user import User


SHARED_IT_ADMIN_USERNAME = "admin_sealink"
DIRECTOR_EMPLOYEE_NAMES = frozenset({"ton that trung kien", "to to van"})


def _normalize(value: str | None) -> str:
    plain = unicodedata.normalize("NFKD", value or "")
    plain = "".join(char for char in plain if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", " ", plain.casefold()).strip()


def _current_org_position(
    db: Session,
    employee: Employee,
) -> tuple[str | None, str | None, int | None]:
    row = (
        db.query(OrganizationAssignment, OrganizationUnit)
        .join(OrganizationUnit, OrganizationUnit.id == OrganizationAssignment.org_unit_id)
        .filter(
            OrganizationAssignment.employee_id == employee.id,
            OrganizationAssignment.effective_to.is_(None),
            OrganizationUnit.is_active.is_(True),
        )
        .order_by(OrganizationAssignment.id.desc())
        .first()
    )
    if not row:
        return None, None, None
    assignment, unit = row
    return assignment.position_title, unit.name, unit.linked_department_id


def infer_employee_access_role(db: Session, employee: Employee) -> tuple[str, str]:
    """Return the role and a human-readable reason for an employee.

    The employee's current department is authoritative.  The organization
    assignment supplies the detailed title (for example ``IT Executive`` or
    ``Admin``) only when it still belongs to the same department.
    """

    linked_user = db.get(User, employee.user_id) if employee.user_id else None
    if linked_user and linked_user.username.casefold() == SHARED_IT_ADMIN_USERNAME:
        return IT_ADMIN, "Tài khoản quản trị cao nhất: toàn quyền nghiệp vụ, Backup và Audit"
    if _normalize(employee.full_name) in DIRECTOR_EMPLOYEE_NAMES:
        return DIRECTOR, "Giám đốc: kế thừa toàn bộ quyền nghiệp vụ của Kế toán trưởng"
    if linked_user and linked_user.role == ADMIN:
        return ADMIN, "Tài khoản Kế toán trưởng được chỉ định và bảo vệ"

    department_name = employee.department_name
    if employee.department_id is not None:
        department = db.get(Department, employee.department_id)
        if department:
            department_name = department.name

    org_title, org_unit_name, linked_department_id = _current_org_position(db, employee)
    department_key = _normalize(department_name)
    org_key = _normalize(org_unit_name)
    is_it_admin_department = (
        department_key == "it"
        or "it admin" in department_key
        or (
            employee.department_id is None
            and ("it admin" in org_key or org_key == "it")
        )
    )
    assignment_matches_department = (
        employee.department_id is None
        or linked_department_id is None
        or linked_department_id == employee.department_id
    )
    title = (
        org_title
        if is_it_admin_department and assignment_matches_department and org_title
        else employee.position
    )
    title_key = _normalize(title)

    if is_it_admin_department and (title_key == "admin" or title_key.startswith("admin ")):
        return HR_ADMIN, f"Chức vụ {title or 'Admin'} trong nhánh IT & ADMIN"
    if is_it_admin_department and "it" in title_key.split():
        return USER, "Nhân viên IT sử dụng tài khoản quản trị dùng chung admin_sealink"
    return USER, "Tài khoản nhân viên thông thường"


def sync_employee_access_role(
    db: Session,
    employee: Employee,
) -> tuple[str, str, bool]:
    """Synchronize a linked account using the current access assignment."""

    role, reason = infer_employee_access_role(db, employee)
    if not employee.user_id:
        return role, reason, False
    user = db.get(User, employee.user_id)
    if not user:
        return role, reason, False
    changed = user.role != role
    if changed:
        user.role = role
        db.add(user)
    return role, reason, changed


def sync_all_employee_access_roles(db: Session) -> list[dict]:
    results: list[dict] = []
    employees = db.query(Employee).order_by(Employee.id.asc()).all()
    for employee in employees:
        role, reason, changed = sync_employee_access_role(db, employee)
        results.append(
            {
                "employee_id": employee.id,
                "employee_name": employee.full_name,
                "user_id": employee.user_id,
                "role": role,
                "reason": reason,
                "changed": changed,
            }
        )
    return results
