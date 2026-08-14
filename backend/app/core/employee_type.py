"""Shared employee-type and allowance defaults.

The values in this module are the contract-level defaults.  Monthly salary
inputs are materialised from these values and may still be changed per period.
"""

from typing import Final


FULLTIME: Final = "FULLTIME"
PROBATION: Final = "PROBATION"
INTERN: Final = "INTERN"
VALID_EMPLOYEE_TYPES: Final = {FULLTIME, PROBATION, INTERN}

FULLTIME_ALLOWANCE_DEFAULTS: Final = {
    "meal_allowance": 1_200_000,
    "phone_allowance": 2_000_000,
    "trans_allowance": 2_000_000,
    "other_allowance": 0,
}


def normalize_employee_type(value: str | None) -> str:
    normalized = str(value or FULLTIME).strip().upper()
    if normalized not in VALID_EMPLOYEE_TYPES:
        raise ValueError("employee_type must be FULLTIME, PROBATION, or INTERN")
    return normalized


def allowance_defaults_for_type(employee_type: str | None) -> dict[str, int]:
    """Return the contract allowance set for an employment type."""
    normalized = normalize_employee_type(employee_type)
    if normalized == FULLTIME:
        return dict(FULLTIME_ALLOWANCE_DEFAULTS)
    return {
        "meal_allowance": 0,
        "phone_allowance": 0,
        "trans_allowance": 0,
        "other_allowance": 0,
    }


def apply_contract_allowance_defaults(employee: object, employee_type: str | None) -> None:
    """Apply the type's contract allowance defaults to an Employee model."""
    for field, amount in allowance_defaults_for_type(employee_type).items():
        setattr(employee, field, amount)


def apply_monthly_allowance_defaults(monthly_input: object, employee_type: str | None) -> None:
    """Apply the matching allowance set to one period's salary input."""
    values = allowance_defaults_for_type(employee_type)
    monthly_input.meal_allowance_free = values["meal_allowance"]
    monthly_input.meal_allowance_tax = 0
    monthly_input.phone_allowance_free = values["phone_allowance"]
    monthly_input.trans_allowance_tax = values["trans_allowance"]
    monthly_input.perf_allowance_tax = values["other_allowance"]
