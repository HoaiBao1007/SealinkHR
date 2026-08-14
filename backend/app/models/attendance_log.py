from datetime import date, datetime
from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base


from sqlalchemy import UniqueConstraint, Index

class AttendanceLog(Base):
    __tablename__ = "attendance_logs"
    __table_args__ = (
        UniqueConstraint("employee_id", "work_date", "upload_batch_id", name="uq_attendance_logs_employee_date_batch"),
        Index("ix_attendance_logs_employee_date_batch", "employee_id", "work_date", "upload_batch_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    upload_batch_id: Mapped[int] = mapped_column(ForeignKey("upload_batches.id"), nullable=False, index=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), nullable=False, index=True)
    work_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    raw_time_values: Mapped[str | None] = mapped_column(Text, nullable=True)
    first_check_in: Mapped[str | None] = mapped_column(String(8), nullable=True)
    last_check_out: Mapped[str | None] = mapped_column(String(8), nullable=True)
    late_minutes: Mapped[int] = mapped_column(Integer, default=0)
    early_minutes: Mapped[int] = mapped_column(Integer, default=0)
    missing_flag: Mapped[bool] = mapped_column(Boolean, default=False)
    missing_reason: Mapped[str | None] = mapped_column(String(100), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
