from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Float, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class MonthlySalaryInput(Base):
    __tablename__ = "monthly_salary_inputs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id", ondelete="CASCADE"), nullable=False, index=True)
    salary_period: Mapped[str] = mapped_column(String(7), nullable=False, index=True)  # e.g. '2026-05'
    actual_working_days: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    meal_allowance_free: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    meal_allowance_tax: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    phone_allowance_free: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    trans_allowance_tax: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    perf_allowance_tax: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    other_income: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Supporting information for the manually entered "Thu nhập khác" amount.
    # The file itself stays in private backend storage and is only served by an
    # authenticated payroll endpoint; never expose this path to the browser.
    other_income_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    other_income_document_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    other_income_document_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    other_income_document_content_type: Mapped[str | None] = mapped_column(String(150), nullable=True)
    other_income_document_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    other_income_document_uploaded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    bonus: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    advance_payment: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    pit_refund: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    other_deductions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    bonus_14: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    
    # Core employee overrides for this specific period
    fullname: Mapped[str | None] = mapped_column(String(150), nullable=True)
    contract_salary: Mapped[int | None] = mapped_column(Integer, nullable=True)
    employee_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    position: Mapped[str | None] = mapped_column(String(150), nullable=True)
    dependents_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    account_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    bank_name: Mapped[str | None] = mapped_column(String(150), nullable=True)
    # Snapshot the policy selected when this payroll input is first saved.
    # It protects an already prepared/published month from later policy changes.
    salary_policy_id: Mapped[int | None] = mapped_column(
        ForeignKey("salary_policies.id", ondelete="SET NULL"), nullable=True, index=True
    )

    is_published: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    
    # Mid-month salary change tracking
    is_mid_month_change: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    prorated_old_salary: Mapped[int | None] = mapped_column(Integer, nullable=True)
    prorated_new_salary: Mapped[int | None] = mapped_column(Integer, nullable=True)
    prorated_days_old: Mapped[float | None] = mapped_column(Float, nullable=True)
    prorated_days_new: Mapped[float | None] = mapped_column(Float, nullable=True)
    mid_month_effective_date: Mapped[str | None] = mapped_column(String(20), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    employee = relationship("Employee", back_populates="monthly_salary_inputs")
