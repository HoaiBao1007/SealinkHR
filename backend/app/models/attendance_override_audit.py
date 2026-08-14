from datetime import date, datetime
from sqlalchemy import Date, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base

class AttendanceOverrideAudit(Base):
    __tablename__ = "attendance_overrides_audit"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), nullable=False, index=True)
    work_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    old_symbol: Mapped[str] = mapped_column(String(10), nullable=False)
    new_symbol: Mapped[str] = mapped_column(String(10), nullable=False)
    old_check_in: Mapped[str | None] = mapped_column(String(8), nullable=True)
    new_check_in: Mapped[str | None] = mapped_column(String(8), nullable=True)
    old_check_out: Mapped[str | None] = mapped_column(String(8), nullable=True)
    new_check_out: Mapped[str | None] = mapped_column(String(8), nullable=True)
    reason: Mapped[str] = mapped_column(String(255), nullable=False)
    changed_by_user_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), nullable=False)
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    source_ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    device_address: Mapped[str | None] = mapped_column(String(100), nullable=True)
