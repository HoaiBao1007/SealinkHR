"""Add the company telephone number to employee profiles.

Revision ID: 20260730_0010
Revises: 20260729_0009
Create Date: 2026-07-30
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260730_0010"
down_revision: Union[str, None] = "20260729_0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "employees",
        sa.Column("company_phone_number", sa.String(length=50), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("employees", "company_phone_number")
