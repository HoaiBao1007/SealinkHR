from datetime import datetime, date

from sqlalchemy import Boolean, DateTime, ForeignKey, Numeric, String, func, Date, Text
from sqlalchemy.orm import Mapped, mapped_column, synonym, relationship

from app.db.base import Base


class Employee(Base):
    __tablename__ = "employees"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    machine_employee_id: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    biometric_id: Mapped[str | None] = mapped_column(String(50), unique=True, nullable=True, index=True)
    full_name: Mapped[str] = mapped_column(String(150), nullable=False)
    notion_name: Mapped[str | None] = mapped_column(String(150), unique=True, nullable=True, index=True)
    department_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    department_name: Mapped[str | None] = mapped_column(String(150), nullable=True)
    department_id: Mapped[int | None] = mapped_column(ForeignKey("departments.id", ondelete="SET NULL"), nullable=True)
    
    department = relationship("Department", foreign_keys=[department_id], back_populates="employees")
    annual_leave_quota: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False, default=12)
    annual_leave_used: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False, default=0)
    paid_leave_balance: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False, default=0)
    unpaid_leave_balance: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="ACTIVE")
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    resignation_period: Mapped[str | None] = mapped_column(String(7), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    # Salary fields
    employee_code: Mapped[str | None] = mapped_column(String(50), unique=True, nullable=True, index=True)
    position: Mapped[str | None] = mapped_column(String(150), nullable=True)
    contract_salary: Mapped[int] = mapped_column(nullable=False, default=0)
    meal_allowance: Mapped[int] = mapped_column(nullable=False, default=1200000)
    trans_allowance: Mapped[int] = mapped_column(nullable=False, default=2000000)
    phone_allowance: Mapped[int] = mapped_column(nullable=False, default=2000000)
    other_allowance: Mapped[int] = mapped_column(nullable=False, default=0)
    bonus_coefficient: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False, default=0.0)
    employee_type: Mapped[str] = mapped_column(String(50), nullable=False, default="FULLTIME")
    dependents_count: Mapped[int] = mapped_column(nullable=False, default=0)
    account_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    bank_name: Mapped[str | None] = mapped_column(String(150), nullable=True)
    tax_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    phone_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    company_phone_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    social_insurance_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    pvi_insurance: Mapped[str | None] = mapped_column(String(50), nullable=True)
    health_insurance_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    company_email: Mapped[str | None] = mapped_column(String(150), nullable=True)
    personal_email: Mapped[str | None] = mapped_column(String(150), nullable=True)
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)
    cccd_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    contract_url: Mapped[str | None] = mapped_column(Text, nullable=True)

    fullname: Mapped[str] = synonym("full_name")
    
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    user = relationship("User")
    
    monthly_salary_inputs: Mapped[list["MonthlySalaryInput"]] = relationship(
        "MonthlySalaryInput", back_populates="employee", cascade="all, delete-orphan"
    )
    
    salary_decisions: Mapped[list["SalaryDecision"]] = relationship(
        "SalaryDecision", back_populates="employee", cascade="all, delete-orphan"
    )


