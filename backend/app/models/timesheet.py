from datetime import date, datetime
from sqlalchemy import Date, DateTime, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base


from sqlalchemy import UniqueConstraint, Index

class Timesheet(Base):
    __tablename__ = "timesheets"
    __table_args__ = (
        UniqueConstraint("employee_id", "period_start", "period_end", name="uq_timesheets_employee_period"),
        Index("ix_timesheets_employee_period", "employee_id", "period_start", "period_end"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    period_start: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    period_end: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), nullable=False, index=True)
    total_work_days: Mapped[float] = mapped_column(Numeric(5,2), default=0)
    total_late_minutes: Mapped[int] = mapped_column(Integer, default=0)
    total_absent_days: Mapped[float] = mapped_column(Numeric(5,2), default=0)
    total_paid_leave_days: Mapped[float] = mapped_column(Numeric(5,2), default=0)
    total_unpaid_leave_days: Mapped[float] = mapped_column(Numeric(5,2), default=0)
    total_business_trip_days: Mapped[float] = mapped_column(Numeric(5,2), default=0)
    approval_status: Mapped[str] = mapped_column(String(20), default="draft")
    approved_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id"), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
