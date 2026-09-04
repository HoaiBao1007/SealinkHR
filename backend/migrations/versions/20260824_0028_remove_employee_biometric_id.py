"""remove obsolete employee biometric id

Revision ID: 20260824_0028
Revises: 20260823_0027
Create Date: 2026-08-24
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260824_0028"
down_revision: Union[str, None] = "20260823_0027"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_index("ix_employees_biometric_id", table_name="employees")
    op.drop_column("employees", "biometric_id")


def downgrade() -> None:
    op.add_column(
        "employees",
        sa.Column("biometric_id", sa.String(length=50), nullable=True),
    )
    op.create_index(
        "ix_employees_biometric_id",
        "employees",
        ["biometric_id"],
        unique=True,
    )
