from datetime import datetime, date as date_type

from sqlalchemy import (
    Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, func
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class CommissionPeriod(Base):
    """
    Mỗi bản ghi đại diện cho 1 lần import file Job PnL từ Climax
    cho một kỳ (ví dụ: Q2/2026).
    """
    __tablename__ = "commission_periods"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    period_label: Mapped[str] = mapped_column(String(30), nullable=False)   # e.g. "Q2-2026" hoặc "05.2026"
    from_date: Mapped[date_type | None] = mapped_column(Date, nullable=True)
    till_date: Mapped[date_type | None] = mapped_column(Date, nullable=True)
    source_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    created_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    is_voided: Mapped[bool] = mapped_column(nullable=False, default=False, index=True)
    voided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    voided_by: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Relationship
    jobs: Mapped[list["CommissionJob"]] = relationship(
        "CommissionJob", back_populates="period", cascade="all, delete-orphan"
    )


class CommissionJob(Base):
    """
    Mỗi dòng trong file "Job PnL With Realize/Unrealize Detail" từ Climax.
    """
    __tablename__ = "commission_jobs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    period_id: Mapped[int] = mapped_column(
        ForeignKey("commission_periods.id", ondelete="CASCADE"), nullable=False, index=True
    )

    job_no: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    job_date: Mapped[date_type | None] = mapped_column(Date, nullable=True)
    hbl: Mapped[str | None] = mapped_column(String(100), nullable=True)
    mbl: Mapped[str | None] = mapped_column(String(100), nullable=True)
    customer: Mapped[str | None] = mapped_column(String(255), nullable=True)
    vendor: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sales_rep: Mapped[str | None] = mapped_column(String(150), nullable=True, index=True)
    shipper: Mapped[str | None] = mapped_column(String(255), nullable=True)
    consignee: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sub_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    container_string: Mapped[str | None] = mapped_column(String(100), nullable=True)
    wt: Mapped[float | None] = mapped_column(Float, nullable=True)
    vol: Mapped[float | None] = mapped_column(Float, nullable=True)
    carrier_booking_no: Mapped[str | None] = mapped_column(String(100), nullable=True)
    por: Mapped[str | None] = mapped_column(String(100), nullable=True)
    final_destination: Mapped[str | None] = mapped_column(String(100), nullable=True)
    realized_revenue: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    unrealized_revenue: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    realized_cost: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    unrealized_cost: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    profit_loss: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    container_picked: Mapped[str | None] = mapped_column(String(10), nullable=True)
    payment_received: Mapped[str | None] = mapped_column(String(10), nullable=True)
    bonus_remark: Mapped[str | None] = mapped_column(Text, nullable=True)
    # The accounting team can decide the payout method while this JOB is still
    # being held.  This is only a release plan; it never changes the bonus
    # formula or the ledger amount.
    held_release_mode: Mapped[str | None] = mapped_column(String(32), nullable=True)
    held_release_payout_period: Mapped[str | None] = mapped_column(String(7), nullable=True)

    # Relationship
    period: Mapped["CommissionPeriod"] = relationship("CommissionPeriod", back_populates="jobs")


class CommissionRepOverride(Base):
    """
    Lưu các giá trị ghi đè (overrides) của Sales Rep trong kỳ commission.
    Khi được sửa ngoài bảng lịch sử, các giá trị này sẽ được ưu tiên hiển thị.
    """
    __tablename__ = "commission_rep_overrides"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    period_id: Mapped[int] = mapped_column(
        ForeignKey("commission_periods.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sales_rep: Mapped[str] = mapped_column(String(150), nullable=False, index=True)

    override_job_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    override_profit_loss: Mapped[float | None] = mapped_column(Float, nullable=True)
    override_target: Mapped[float | None] = mapped_column(Float, nullable=True)
    override_bonus_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    override_total_bonus: Mapped[float | None] = mapped_column(Float, nullable=True)
    override_monthly_bonus: Mapped[float | None] = mapped_column(Float, nullable=True)
    remark: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        UniqueConstraint("period_id", "sales_rep", name="uq_period_sales_rep"),
    )


class CommissionBonusLock(Base):
    """One-way accounting lock for one Sales Rep in one source commission period."""
    __tablename__ = "commission_bonus_locks"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    period_id: Mapped[int] = mapped_column(
        ForeignKey("commission_periods.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sales_rep: Mapped[str] = mapped_column(String(150), nullable=False, index=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    locked_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    locked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint("period_id", "sales_rep", name="uq_commission_bonus_lock_period_rep"),
    )


class CommissionPaymentVerification(Base):
    """Immutable workflow state for a Sales payment report, verified by accounting."""
    __tablename__ = "commission_payment_verifications"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    period_id: Mapped[int] = mapped_column(ForeignKey("commission_periods.id", ondelete="CASCADE"), nullable=False, index=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("commission_jobs.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    sales_rep: Mapped[str] = mapped_column(String(150), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="PENDING", index=True)
    report_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    verification_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    reported_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    reported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    verified_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    command_created_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    command_created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CommissionWalletLedger(Base):
    """Sổ cái bất biến của ví thưởng; mọi lần mở khóa hoặc chi trả là một dòng mới."""
    __tablename__ = "commission_wallet_ledger"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    period_id: Mapped[int] = mapped_column(ForeignKey("commission_periods.id", ondelete="RESTRICT"), nullable=False, index=True)
    job_id: Mapped[int | None] = mapped_column(ForeignKey("commission_jobs.id", ondelete="RESTRICT"), nullable=True, index=True)
    entitlement_id: Mapped[int | None] = mapped_column(ForeignKey("commission_bonus_entitlements.id", ondelete="SET NULL"), nullable=True, index=True)
    schedule_id: Mapped[int | None] = mapped_column(ForeignKey("commission_payout_schedules.id", ondelete="SET NULL"), nullable=True, index=True)
    sales_rep: Mapped[str] = mapped_column(String(150), nullable=False, index=True)
    employee_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id", ondelete="SET NULL"), nullable=True, index=True)
    entry_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    payout_period: Mapped[str | None] = mapped_column(String(7), nullable=True, index=True)
    payout_batch: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    reason_code: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    created_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    approved_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class CommissionPayoutPolicy(Base):
    """Quy tắc chi trả. Việc tạo dòng PAID vẫn cần quản trị viên thực hiện."""
    __tablename__ = "commission_payout_policies"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    sales_rep: Mapped[str] = mapped_column(String(150), nullable=False, unique=True, index=True)
    employee_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id", ondelete="SET NULL"), nullable=True, index=True)
    payout_mode: Mapped[str] = mapped_column(String(24), nullable=False, default="MANUAL")
    minimum_amount: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    is_active: Mapped[bool] = mapped_column(nullable=False, default=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())


class CommissionCalculationSnapshot(Base):
    """Immutable result of the existing commission formula at a point in time."""
    __tablename__ = "commission_calculation_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    period_id: Mapped[int] = mapped_column(ForeignKey("commission_periods.id", ondelete="CASCADE"), nullable=False, index=True)
    sales_rep: Mapped[str] = mapped_column(String(150), nullable=False, index=True)
    employee_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id", ondelete="SET NULL"), nullable=True, index=True)
    monthly_bonus: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    total_bonus_quarter: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    source_payload: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class CommissionBonusEntitlement(Base):
    """A JOB-level claim on bonus, sourced from a calculation snapshot."""
    __tablename__ = "commission_bonus_entitlements"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    snapshot_id: Mapped[int | None] = mapped_column(ForeignKey("commission_calculation_snapshots.id", ondelete="SET NULL"), nullable=True, index=True)
    period_id: Mapped[int] = mapped_column(ForeignKey("commission_periods.id", ondelete="CASCADE"), nullable=False, index=True)
    job_id: Mapped[int | None] = mapped_column(ForeignKey("commission_jobs.id", ondelete="SET NULL"), nullable=True, index=True)
    sales_rep: Mapped[str] = mapped_column(String(150), nullable=False, index=True)
    employee_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id", ondelete="SET NULL"), nullable=True, index=True)
    calculated_amount: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    source_period: Mapped[str | None] = mapped_column(String(30), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="ACTIVE", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class CommissionPayoutSchedule(Base):
    """A planned payout month, independent from the commission source quarter."""
    __tablename__ = "commission_payout_schedules"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    sales_rep: Mapped[str] = mapped_column(String(150), nullable=False, index=True)
    employee_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id", ondelete="SET NULL"), nullable=True, index=True)
    payout_period: Mapped[str] = mapped_column(String(7), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="SCHEDULED", index=True)
    total_amount: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    payment_verification_id: Mapped[int | None] = mapped_column(
        ForeignKey("commission_payment_verifications.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    approved_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class CommissionPayoutScheduleAllocation(Base):
    __tablename__ = "commission_payout_schedule_allocations"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    schedule_id: Mapped[int] = mapped_column(ForeignKey("commission_payout_schedules.id", ondelete="CASCADE"), nullable=False, index=True)
    entitlement_id: Mapped[int | None] = mapped_column(ForeignKey("commission_bonus_entitlements.id", ondelete="SET NULL"), nullable=True, index=True)
    ledger_entry_id: Mapped[int | None] = mapped_column(ForeignKey("commission_wallet_ledger.id", ondelete="SET NULL"), nullable=True, index=True)
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="SCHEDULED", index=True)
