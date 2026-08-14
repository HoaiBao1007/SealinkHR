from datetime import date, datetime
from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, SmallInteger, func
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base


from sqlalchemy import UniqueConstraint, Index

class AttendanceDaily(Base):
    __tablename__ = "attendance_daily"
    __table_args__ = (
        UniqueConstraint("employee_id", "work_date", name="uq_attendance_daily_employee_date"),
        Index("ix_attendance_daily_employee_date", "employee_id", "work_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), nullable=False, index=True)
    work_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    period_start: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    period_end: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    check_in_time: Mapped[str | None] = mapped_column(String(8), nullable=True)
    check_out_time: Mapped[str | None] = mapped_column(String(8), nullable=True)
    late_minutes: Mapped[int] = mapped_column(Integer, default=0)
    early_minutes: Mapped[int] = mapped_column(Integer, default=0)
    attendance_symbol: Mapped[str] = mapped_column(String(10), nullable=False)
    abnormal_level: Mapped[str | None] = mapped_column(String(10), nullable=True)
    source_priority: Mapped[int] = mapped_column(SmallInteger, default=1)
    generated_from_batch_id: Mapped[int] = mapped_column(ForeignKey("upload_batches.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
