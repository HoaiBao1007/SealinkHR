"""Add request-category fields for the website Time Off workflow.

Revision ID: 20260813_0021
Revises: 20260811_0020
Create Date: 2026-08-13
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260813_0021"
down_revision: Union[str, None] = "20260811_0020"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Only additive/width-safe changes: existing off-request records are kept.
    with op.batch_alter_table("off_requests") as batch_op:
        batch_op.alter_column(
            "request_type",
            existing_type=sa.String(length=20),
            type_=sa.String(length=40),
            existing_nullable=False,
        )
        batch_op.add_column(sa.Column("business_travel_location", sa.String(length=255), nullable=True))
        batch_op.add_column(
            sa.Column(
                "business_travel_policy_acknowledged",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("off_requests") as batch_op:
        batch_op.drop_column("business_travel_policy_acknowledged")
        batch_op.drop_column("business_travel_location")
        batch_op.alter_column(
            "request_type",
            existing_type=sa.String(length=40),
            type_=sa.String(length=20),
            existing_nullable=False,
        )
