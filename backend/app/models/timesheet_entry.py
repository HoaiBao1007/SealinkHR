from datetime import date, datetime
from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base


from sqlalchemy import UniqueConstraint, Index

class TimesheetEntry(Base):
    __tablename__ = "timesheet_entries"
    __table_args__ = (
        UniqueConstraint("employee_id", "work_date", "timesheet_id", name="uq_timesheet_entries_employee_date_timesheet"),
        Index("ix_timesheet_entries_employee_date_timesheet", "employee_id", "work_date", "timesheet_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    timesheet_id: Mapped[int] = mapped_column(ForeignKey("timesheets.id"), nullable=False, index=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), nullable=False, index=True)
    work_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    original_symbol: Mapped[str] = mapped_column(String(10), nullable=False)
    final_symbol: Mapped[str] = mapped_column(String(10), nullable=False)
    check_in_time: Mapped[str | None] = mapped_column(String(8), nullable=True)
    check_out_time: Mapped[str | None] = mapped_column(String(8), nullable=True)
    late_minutes: Mapped[int] = mapped_column(Integer, default=0)
    early_minutes: Mapped[int] = mapped_column(Integer, default=0)
    is_overridden: Mapped[bool] = mapped_column(Boolean, default=False)
    override_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    overridden_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id"), nullable=True)
    overridden_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
