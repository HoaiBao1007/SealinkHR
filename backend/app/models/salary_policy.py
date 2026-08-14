from datetime import datetime, date

from sqlalchemy import Boolean, Date, DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class SalaryPolicy(Base):
    """Versioned statutory payroll policy.

    A row is never edited after it is confirmed.  A later correction creates a
    new version with its own effective date, so earlier payroll periods retain
    the rule set that applied to them.
    """

    __tablename__ = "salary_policies"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    version_code: Mapped[str] = mapped_column(String(40), nullable=False, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    legal_basis: Mapped[str | None] = mapped_column(Text, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # Minimum wages and contribution ceilings.
    common_minimum_wage: Mapped[int] = mapped_column(Integer, nullable=False, default=2_530_000)
    regional_minimum_wage_i: Mapped[int] = mapped_column(Integer, nullable=False, default=5_310_000)
    regional_minimum_wage_ii: Mapped[int] = mapped_column(Integer, nullable=False, default=4_730_000)
    regional_minimum_wage_iii: Mapped[int] = mapped_column(Integer, nullable=False, default=4_140_000)
    regional_minimum_wage_iv: Mapped[int] = mapped_column(Integer, nullable=False, default=3_700_000)
    default_region: Mapped[str] = mapped_column(String(8), nullable=False, default="I")
    social_health_salary_cap: Mapped[int] = mapped_column(Integer, nullable=False, default=50_600_000)
    unemployment_cap_multiplier: Mapped[int] = mapped_column(Integer, nullable=False, default=20)

    # Rates are stored as decimal fractions: 0.08 means 8%.
    social_employee_rate: Mapped[float] = mapped_column(nullable=False, default=0.08)
    health_employee_rate: Mapped[float] = mapped_column(nullable=False, default=0.015)
    unemployment_employee_rate: Mapped[float] = mapped_column(nullable=False, default=0.01)
    social_employer_rate: Mapped[float] = mapped_column(nullable=False, default=0.175)
    health_employer_rate: Mapped[float] = mapped_column(nullable=False, default=0.03)
    unemployment_employer_rate: Mapped[float] = mapped_column(nullable=False, default=0.01)
    union_fund_employer_rate: Mapped[float] = mapped_column(nullable=False, default=0.02)
    union_employee_rate: Mapped[float] = mapped_column(nullable=False, default=0.005)
    union_employee_cap: Mapped[int] = mapped_column(Integer, nullable=False, default=234_000)

    personal_deduction: Mapped[int] = mapped_column(Integer, nullable=False, default=15_500_000)
    dependent_deduction: Mapped[int] = mapped_column(Integer, nullable=False, default=6_200_000)
    probation_withholding_rate: Mapped[float] = mapped_column(nullable=False, default=0.10)
    probation_withholding_threshold: Mapped[int] = mapped_column(Integer, nullable=False, default=2_000_000)
    # [{"up_to": 10000000, "rate": .05, "deduction": 0}, ...]
    pit_brackets_json: Mapped[str] = mapped_column(Text, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    created_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
