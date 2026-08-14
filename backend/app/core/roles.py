"""Central role names and role groupings.

`ADMIN` is intentionally kept as the existing chief-accountant role so the
current dashboard and financial workflows remain backward compatible.
"""

ADMIN = "ADMIN"
HR_ADMIN = "HR_ADMIN"
IT_ADMIN = "IT_ADMIN"
USER = "USER"

VALID_ROLES = frozenset({ADMIN, HR_ADMIN, IT_ADMIN, USER})
# IT_ADMIN is the highest role. It inherits every chief-accountant business
# capability and adds the IT-only backup/audit capabilities.
BUSINESS_ADMIN_ROLES = frozenset({ADMIN, IT_ADMIN})
# Every authenticated employee role may access only its own payslip,
# attendance and account profile through the personal portal endpoints.
# This does not grant HR_ADMIN access to payroll/commission administration.
PERSONAL_PORTAL_ROLES = frozenset({ADMIN, HR_ADMIN, USER, IT_ADMIN})
ATTENDANCE_MANAGER_ROLES = frozenset({ADMIN, HR_ADMIN, IT_ADMIN})
HR_MANAGER_ROLES = frozenset({ADMIN, HR_ADMIN, IT_ADMIN})
AUDIT_READER_ROLES = frozenset({IT_ADMIN})
