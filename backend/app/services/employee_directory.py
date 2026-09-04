from __future__ import annotations

from app.models.employee import Employee
from app.services.access_role_service import SHARED_IT_ADMIN_USERNAME


SHARED_IT_ADMIN_MACHINE_ID = "ADMIN_SEALINK"


def is_shared_it_admin_profile(employee: Employee) -> bool:
    """Identify the technical audit profile, not a real HR employee."""

    if str(employee.machine_employee_id or "").strip().upper() == SHARED_IT_ADMIN_MACHINE_ID:
        return True
    linked_user = employee.user
    return bool(
        linked_user
        and str(linked_user.username or "").strip().casefold() == SHARED_IT_ADMIN_USERNAME
    )


def machine_identifier_conflict_detail(
    requested_identifier: str,
    owner: Employee,
) -> str:
    """Explain which employee already owns a machine attendance ID."""

    identifier = requested_identifier.strip()
    employee_reference = owner.employee_code or f"hồ sơ #{owner.id}"
    return (
        f"ID máy chấm công '{identifier}' đang thuộc hồ sơ của "
        f"{owner.full_name} (mã máy chính: {owner.machine_employee_id}, "
        f"mã nhân viên: {employee_reference})."
    )
