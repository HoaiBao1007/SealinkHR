"""Versioned payroll-policy helpers shared by salary APIs and calculations."""

import json
from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from app.models.salary_policy import SalaryPolicy


DEFAULT_PIT_BRACKETS = [
    {"up_to": 10_000_000, "rate": 0.05, "deduction": 0},
    {"up_to": 30_000_000, "rate": 0.10, "deduction": 500_000},
    {"up_to": 60_000_000, "rate": 0.20, "deduction": 3_500_000},
    {"up_to": 100_000_000, "rate": 0.30, "deduction": 9_500_000},
    {"up_to": None, "rate": 0.35, "deduction": 14_500_000},
]


def _period_start(period: str | None) -> date:
    if not period:
        return date.today().replace(day=1)
    try:
        year, month = (int(value) for value in period.split("-", 1))
        return date(year, month, 1)
    except (TypeError, ValueError):
        return date.today().replace(day=1)


def ensure_default_salary_policy(db: Session) -> SalaryPolicy:
    existing = db.query(SalaryPolicy).order_by(SalaryPolicy.effective_from.asc(), SalaryPolicy.id.asc()).first()
    if existing:
        return existing
    default = SalaryPolicy(
        version_code="CS-DEFAULT-2026",
        name="Chính sách lương mặc định 2026",
        effective_from=date(2000, 1, 1),
        legal_basis="Thiết lập ban đầu theo bảng thông số kế toán hiện hành.",
        note="Phiên bản nền. Khi có thay đổi, tạo phiên bản mới thay vì sửa phiên bản này.",
        pit_brackets_json=json.dumps(DEFAULT_PIT_BRACKETS),
    )
    db.add(default)
    db.flush()
    return default


def resolve_salary_policy(db: Session, period: str | None = None) -> SalaryPolicy:
    ensure_default_salary_policy(db)
    target = _period_start(period)
    policy = (
        db.query(SalaryPolicy)
        .filter(SalaryPolicy.is_active.is_(True), SalaryPolicy.effective_from <= target)
        .order_by(SalaryPolicy.effective_from.desc(), SalaryPolicy.id.desc())
        .first()
    )
    return policy or ensure_default_salary_policy(db)


def policy_to_dict(policy: SalaryPolicy) -> dict[str, Any]:
    data = {column.name: getattr(policy, column.name) for column in policy.__table__.columns}
    data["effective_from"] = policy.effective_from.isoformat()
    data["created_at"] = policy.created_at.isoformat() if policy.created_at else None
    try:
        data["pit_brackets"] = json.loads(policy.pit_brackets_json or "[]")
    except json.JSONDecodeError:
        data["pit_brackets"] = DEFAULT_PIT_BRACKETS
    data.pop("pit_brackets_json", None)
    return data


def region_minimum_wage(policy: dict[str, Any]) -> int:
    region = str(policy.get("default_region") or "I").upper()
    return int(policy.get(f"regional_minimum_wage_{region.lower()}") or policy.get("regional_minimum_wage_i") or 0)
