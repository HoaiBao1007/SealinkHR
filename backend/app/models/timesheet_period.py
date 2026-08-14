from datetime import date, datetime
from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base
from sqlalchemy import UniqueConstraint, Index

class TimesheetPeriod(Base):
    __tablename__ = "timesheet_periods"
    __table_args__ = (
        UniqueConstraint("period_start", "period_end", name="uq_timesheet_periods_start_end"),
        Index("ix_timesheet_periods_start_end", "period_start", "period_end"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    period_start: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    period_end: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    is_locked: Mapped[bool] = mapped_column(Boolean, default=False)
    locked_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id"), nullable=True)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
