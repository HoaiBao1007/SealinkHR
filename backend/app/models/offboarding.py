from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class OffboardingFormVersion(Base):
    __tablename__ = "offboarding_form_versions"
    __table_args__ = (Index("ix_offboarding_form_versions_status_version", "status", "version_number"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="DRAFT", index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    success_message: Mapped[str] = mapped_column(Text, nullable=False, default="")
    fields_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    submissions = relationship("OffboardingRequest", back_populates="form_version")


class OffboardingRequest(Base):
    __tablename__ = "offboarding_requests"
    __table_args__ = (
        Index("ix_offboarding_requests_status_submitted", "status", "submitted_at"),
        Index("ix_offboarding_requests_employee_status", "employee_id", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    public_id: Mapped[str] = mapped_column(String(36), unique=True, nullable=False, index=True)
    form_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("offboarding_form_versions.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    employee_id: Mapped[int | None] = mapped_column(
        ForeignKey("employees.id", ondelete="SET NULL"), nullable=True, index=True
    )
    requester_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    manager_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="PENDING_DEPARTMENT", index=True)
    resume_status: Mapped[str | None] = mapped_column(String(40), nullable=True)

    request_date: Mapped[date] = mapped_column(Date, nullable=False)
    notice_period_days: Mapped[int] = mapped_column(Integer, nullable=False)
    desired_last_working_date: Mapped[date] = mapped_column(Date, nullable=False)
    confirmed_last_working_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    last_pay_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    personal_opinion: Mapped[str] = mapped_column(Text, nullable=False)
    no_grievance_confirmed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    handover_commitment_confirmed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    employee_name_snapshot: Mapped[str] = mapped_column(String(150), nullable=False)
    employee_code_snapshot: Mapped[str | None] = mapped_column(String(50), nullable=True)
    position_snapshot: Mapped[str | None] = mapped_column(String(150), nullable=True)
    department_snapshot: Mapped[str | None] = mapped_column(String(150), nullable=True)
    manager_name_snapshot: Mapped[str | None] = mapped_column(String(150), nullable=True)
    email_snapshot: Mapped[str | None] = mapped_column(String(150), nullable=True, index=True)
    answers_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewer_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    department_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    hr_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    director_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    department_noted_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    hr_noted_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    director_approved_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    department_noted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    hr_noted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    director_approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    employee = relationship("Employee", foreign_keys=[employee_id])
    form_version = relationship("OffboardingFormVersion", back_populates="submissions")
    attachments = relationship(
        "OffboardingAttachment",
        back_populates="submission",
        cascade="all, delete-orphan",
        order_by="OffboardingAttachment.id",
    )


class OffboardingAttachment(Base):
    __tablename__ = "offboarding_attachments"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    submission_id: Mapped[int] = mapped_column(
        ForeignKey("offboarding_requests.id", ondelete="CASCADE"), nullable=False, index=True
    )
    field_key: Mapped[str] = mapped_column(String(80), nullable=False)
    original_name: Mapped[str] = mapped_column(String(255), nullable=False)
    stored_path: Mapped[str] = mapped_column(String(500), nullable=False)
    content_type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    submission = relationship("OffboardingRequest", back_populates="attachments")


class OffboardingAction(Base):
    __tablename__ = "offboarding_actions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    request_id: Mapped[int] = mapped_column(
        ForeignKey("offboarding_requests.id", ondelete="CASCADE"), nullable=False, index=True
    )
    actor_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    action: Mapped[str] = mapped_column(String(40), nullable=False)
    from_status: Mapped[str | None] = mapped_column(String(40), nullable=True)
    to_status: Mapped[str] = mapped_column(String(40), nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
