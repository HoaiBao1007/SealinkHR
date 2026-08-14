"""Baseline schema - create all tables from scratch.

Revision ID: 20260518_0000
Revises:
Create Date: 2026-05-18 00:00:00.000000

Creates the full initial schema supporting SQLite, MySQL/XAMPP, and PostgreSQL.
MySQL tables use InnoDB engine with utf8mb4 charset for Vietnamese text support.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260518_0000"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# MySQL table options — ignored by SQLite and PostgreSQL
_MYSQL_OPTS = {
    "mysql_engine": "InnoDB",
    "mysql_charset": "utf8mb4",
    "mysql_collate": "utf8mb4_unicode_ci",
}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    # ── employees ────────────────────────────────────────────────────
    if "employees" not in existing_tables:
        op.create_table(
            "employees",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("machine_employee_id", sa.String(length=50), nullable=False),
            sa.Column("full_name", sa.String(length=150), nullable=False),
            sa.Column("department_code", sa.String(length=50), nullable=True),
            sa.Column("department_name", sa.String(length=150), nullable=True),
            sa.Column("annual_leave_quota", sa.Integer(), nullable=False, server_default="12"),
            sa.Column("annual_leave_used", sa.Numeric(precision=4, scale=1), nullable=False, server_default="0"),
            sa.Column("paid_leave_balance", sa.Numeric(precision=4, scale=1), nullable=False, server_default="0"),
            sa.Column("unpaid_leave_balance", sa.Numeric(precision=4, scale=1), nullable=False, server_default="0"),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default="1"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("machine_employee_id", name="uq_employees_machine_employee_id"),
            **_MYSQL_OPTS,
        )
        op.create_index("ix_employees_id", "employees", ["id"], unique=False)
        op.create_index("ix_employees_machine_employee_id", "employees", ["machine_employee_id"], unique=True)

    # ── upload_batches ───────────────────────────────────────────────
    if "upload_batches" not in existing_tables:
        op.create_table(
            "upload_batches",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("import_type", sa.String(length=50), nullable=False),
            sa.Column("file_name", sa.String(length=255), nullable=True),
            sa.Column("uploaded_by_user_id", sa.Integer(), nullable=True),
            sa.Column("row_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("status", sa.String(length=50), nullable=False, server_default="pending"),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.PrimaryKeyConstraint("id"),
            **_MYSQL_OPTS,
        )
        op.create_index("ix_upload_batches_id", "upload_batches", ["id"], unique=False)

    # ── attendance_logs ──────────────────────────────────────────────
    if "attendance_logs" not in existing_tables:
        op.create_table(
            "attendance_logs",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("upload_batch_id", sa.Integer(), nullable=True),
            sa.Column("employee_id", sa.Integer(), nullable=True),
            sa.Column("machine_employee_id", sa.String(length=50), nullable=False),
            sa.Column("full_name", sa.String(length=150), nullable=True),
            sa.Column("department_name", sa.String(length=150), nullable=True),
            sa.Column("work_date", sa.Date(), nullable=False),
            sa.Column("raw_time_values", sa.Text(), nullable=True),
            sa.Column("check_in_time", sa.Time(), nullable=True),
            sa.Column("check_out_time", sa.Time(), nullable=True),
            sa.Column("missing_flag", sa.Boolean(), nullable=False, server_default="0"),
            sa.Column("missing_reason", sa.String(length=255), nullable=True),
            sa.Column("late_minutes", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("early_minutes", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("period_start", sa.Date(), nullable=True),
            sa.Column("period_end", sa.Date(), nullable=True),
            sa.Column("note", sa.String(length=500), nullable=True),
            sa.Column("employee_not_found", sa.Boolean(), nullable=False, server_default="0"),
            sa.ForeignKeyConstraint(["employee_id"], ["employees.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["upload_batch_id"], ["upload_batches.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("machine_employee_id", "work_date", name="uq_attendance_logs_machine_date"),
            **_MYSQL_OPTS,
        )
        op.create_index("ix_attendance_logs_id", "attendance_logs", ["id"], unique=False)
        op.create_index("ix_attendance_logs_machine_employee_id", "attendance_logs", ["machine_employee_id"], unique=False)
        op.create_index("ix_attendance_logs_work_date", "attendance_logs", ["work_date"], unique=False)

    # ── attendance_daily ─────────────────────────────────────────────
    if "attendance_daily" not in existing_tables:
        op.create_table(
            "attendance_daily",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("employee_id", sa.Integer(), nullable=True),
            sa.Column("machine_employee_id", sa.String(length=50), nullable=False),
            sa.Column("work_date", sa.Date(), nullable=False),
            sa.Column("attendance_symbol", sa.String(length=20), nullable=True),
            sa.Column("check_in_time", sa.Time(), nullable=True),
            sa.Column("check_out_time", sa.Time(), nullable=True),
            sa.Column("late_minutes", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("early_minutes", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("is_absent", sa.Boolean(), nullable=False, server_default="0"),
            sa.Column("is_abnormal", sa.Boolean(), nullable=False, server_default="0"),
            sa.Column("source", sa.String(length=50), nullable=True),
            sa.ForeignKeyConstraint(["employee_id"], ["employees.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("employee_id", "work_date", name="uq_attendance_daily_emp_date"),
            **_MYSQL_OPTS,
        )
        op.create_index("ix_attendance_daily_id", "attendance_daily", ["id"], unique=False)
        op.create_index("ix_attendance_daily_work_date", "attendance_daily", ["work_date"], unique=False)

    # ── timesheets ───────────────────────────────────────────────────
    if "timesheets" not in existing_tables:
        op.create_table(
            "timesheets",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("employee_id", sa.Integer(), nullable=True),
            sa.Column("period_start", sa.Date(), nullable=False),
            sa.Column("period_end", sa.Date(), nullable=False),
            sa.Column("status", sa.String(length=50), nullable=False, server_default="draft"),
            sa.Column("approved_by_user_id", sa.Integer(), nullable=True),
            sa.Column("approved_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.ForeignKeyConstraint(["employee_id"], ["employees.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("employee_id", "period_start", name="uq_timesheets_emp_period"),
            **_MYSQL_OPTS,
        )
        op.create_index("ix_timesheets_id", "timesheets", ["id"], unique=False)
        op.create_index("ix_timesheets_period_start", "timesheets", ["period_start"], unique=False)

    # ── timesheet_entries ────────────────────────────────────────────
    if "timesheet_entries" not in existing_tables:
        op.create_table(
            "timesheet_entries",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("timesheet_id", sa.Integer(), nullable=True),
            sa.Column("work_date", sa.Date(), nullable=False),
            sa.Column("original_symbol", sa.String(length=20), nullable=True),
            sa.Column("final_symbol", sa.String(length=20), nullable=True),
            sa.Column("check_in_time", sa.Time(), nullable=True),
            sa.Column("check_out_time", sa.Time(), nullable=True),
            sa.Column("late_minutes", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("early_minutes", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("is_overridden", sa.Boolean(), nullable=False, server_default="0"),
            sa.ForeignKeyConstraint(["timesheet_id"], ["timesheets.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("timesheet_id", "work_date", name="uq_timesheet_entries_ts_date"),
            **_MYSQL_OPTS,
        )
        op.create_index("ix_timesheet_entries_id", "timesheet_entries", ["id"], unique=False)

    # ── off_requests ─────────────────────────────────────────────────
    if "off_requests" not in existing_tables:
        op.create_table(
            "off_requests",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("employee_id", sa.Integer(), nullable=True),
            sa.Column("request_date", sa.Date(), nullable=False),
            sa.Column("off_type", sa.String(length=50), nullable=False),
            sa.Column("is_paid", sa.Boolean(), nullable=False, server_default="1"),
            sa.Column("status", sa.String(length=50), nullable=False, server_default="pending"),
            sa.Column("reason", sa.String(length=500), nullable=True),
            sa.Column("approved_by_user_id", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.ForeignKeyConstraint(["employee_id"], ["employees.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
            **_MYSQL_OPTS,
        )
        op.create_index("ix_off_requests_id", "off_requests", ["id"], unique=False)

    # ── attendance_overrides_audit ───────────────────────────────────
    if "attendance_overrides_audit" not in existing_tables:
        op.create_table(
            "attendance_overrides_audit",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("employee_id", sa.Integer(), nullable=True),
            sa.Column("machine_employee_id", sa.String(length=50), nullable=True),
            sa.Column("employee_name", sa.String(length=150), nullable=True),
            sa.Column("work_date", sa.Date(), nullable=False),
            sa.Column("old_symbol", sa.String(length=20), nullable=True),
            sa.Column("new_symbol", sa.String(length=20), nullable=True),
            sa.Column("old_check_in", sa.String(length=20), nullable=True),
            sa.Column("new_check_in", sa.String(length=20), nullable=True),
            sa.Column("old_check_out", sa.String(length=20), nullable=True),
            sa.Column("new_check_out", sa.String(length=20), nullable=True),
            sa.Column("reason", sa.String(length=500), nullable=False),
            sa.Column("changed_by_user_id", sa.String(length=50), nullable=True),
            sa.Column("changed_by_name", sa.String(length=150), nullable=True),
            sa.Column("changed_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.ForeignKeyConstraint(["employee_id"], ["employees.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
            **_MYSQL_OPTS,
        )
        op.create_index("ix_attendance_overrides_audit_id", "attendance_overrides_audit", ["id"], unique=False)
        op.create_index("ix_attendance_overrides_audit_work_date", "attendance_overrides_audit", ["work_date"], unique=False)


def downgrade() -> None:
    op.drop_table("attendance_overrides_audit")
    op.drop_table("off_requests")
    op.drop_table("timesheet_entries")
    op.drop_table("timesheets")
    op.drop_table("attendance_daily")
    op.drop_table("attendance_logs")
    op.drop_table("upload_batches")
    op.drop_table("employees")
