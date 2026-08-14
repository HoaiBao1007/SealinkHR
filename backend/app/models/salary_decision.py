from datetime import datetime, date

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Date, func, Numeric
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

class SalaryDecision(Base):
    __tablename__ = "salary_decisions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id", ondelete="CASCADE"), nullable=False, index=True)
    old_salary: Mapped[int] = mapped_column(Integer, nullable=False)
    new_salary: Mapped[int] = mapped_column(Integer, nullable=False)
    meal_allowance: Mapped[int] = mapped_column(Integer, nullable=False, default=1200000)
    trans_allowance: Mapped[int] = mapped_column(Integer, nullable=False, default=2000000)
    phone_allowance: Mapped[int] = mapped_column(Integer, nullable=False, default=2000000)
    other_allowance: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    bonus_coefficient: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False, default=0.0)
    old_employee_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    new_employee_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    old_meal_allowance: Mapped[int | None] = mapped_column(Integer, nullable=True)
    old_trans_allowance: Mapped[int | None] = mapped_column(Integer, nullable=True)
    old_phone_allowance: Mapped[int | None] = mapped_column(Integer, nullable=True)
    old_other_allowance: Mapped[int | None] = mapped_column(Integer, nullable=True)
    effective_date: Mapped[date] = mapped_column(Date, nullable=False)
    reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="PENDING")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    employee = relationship("Employee", back_populates="salary_decisions")
