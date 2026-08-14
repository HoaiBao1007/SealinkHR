"""Add the website-native Time Off approval workflow.

Revision ID: 20260811_0019
Revises: 20260804_0018
Create Date: 2026-08-11
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260811_0019"
down_revision: Union[str, None] = "20260804_0018"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("off_requests") as batch_op:
        batch_op.add_column(sa.Column("requester_user_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("department_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("approver_user_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("approver_employee_id", sa.Integer(), nullable=True))
        batch_op.add_column(
            sa.Column(
                "day_part",
                sa.String(length=20),
                nullable=False,
                server_default=sa.text("'FULL_DAY'"),
            )
        )
        batch_op.add_column(sa.Column("handover_employee_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("handover_notes", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("manager_comment", sa.Text(), nullable=True))
        batch_op.add_column(
            sa.Column(
                "submitted_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            )
        )
        batch_op.create_foreign_key(
            "fk_off_requests_requester_user",
            "users",
            ["requester_user_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_foreign_key(
            "fk_off_requests_department",
            "departments",
            ["department_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_foreign_key(
            "fk_off_requests_approver_user",
            "users",
            ["approver_user_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_foreign_key(
            "fk_off_requests_approver_employee",
            "employees",
            ["approver_employee_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_foreign_key(
            "fk_off_requests_handover_employee",
            "employees",
            ["handover_employee_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index("ix_off_requests_requester_user_id", ["requester_user_id"])
        batch_op.create_index("ix_off_requests_department_id", ["department_id"])
        batch_op.create_index("ix_off_requests_approver_user_id", ["approver_user_id"])
        batch_op.create_index("ix_off_requests_approver_employee_id", ["approver_employee_id"])

    op.create_table(
        "approval_actions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("request_id", sa.Integer(), nullable=False),
        sa.Column("actor_user_id", sa.Integer(), nullable=True),
        sa.Column("actor_employee_id", sa.Integer(), nullable=True),
        sa.Column("action", sa.String(length=30), nullable=False),
        sa.Column("from_status", sa.String(length=30), nullable=False),
        sa.Column("to_status", sa.String(length=30), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(["request_id"], ["off_requests.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["actor_employee_id"], ["employees.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_approval_actions_request_id", "approval_actions", ["request_id"])
    op.create_index("ix_approval_actions_actor_user_id", "approval_actions", ["actor_user_id"])
    op.create_index("ix_approval_actions_action", "approval_actions", ["action"])
    op.create_index("ix_approval_actions_created_at", "approval_actions", ["created_at"])
    op.create_index(
        "ix_approval_actions_request_created",
        "approval_actions",
        ["request_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_approval_actions_request_created", table_name="approval_actions")
    op.drop_index("ix_approval_actions_created_at", table_name="approval_actions")
    op.drop_index("ix_approval_actions_action", table_name="approval_actions")
    op.drop_index("ix_approval_actions_actor_user_id", table_name="approval_actions")
    op.drop_index("ix_approval_actions_request_id", table_name="approval_actions")
    op.drop_table("approval_actions")

    with op.batch_alter_table("off_requests") as batch_op:
        batch_op.drop_index("ix_off_requests_approver_employee_id")
        batch_op.drop_index("ix_off_requests_approver_user_id")
        batch_op.drop_index("ix_off_requests_department_id")
        batch_op.drop_index("ix_off_requests_requester_user_id")
        batch_op.drop_constraint("fk_off_requests_handover_employee", type_="foreignkey")
        batch_op.drop_constraint("fk_off_requests_approver_employee", type_="foreignkey")
        batch_op.drop_constraint("fk_off_requests_approver_user", type_="foreignkey")
        batch_op.drop_constraint("fk_off_requests_department", type_="foreignkey")
        batch_op.drop_constraint("fk_off_requests_requester_user", type_="foreignkey")
        batch_op.drop_column("submitted_at")
        batch_op.drop_column("manager_comment")
        batch_op.drop_column("handover_notes")
        batch_op.drop_column("handover_employee_id")
        batch_op.drop_column("day_part")
        batch_op.drop_column("approver_employee_id")
        batch_op.drop_column("approver_user_id")
        batch_op.drop_column("department_id")
        batch_op.drop_column("requester_user_id")
