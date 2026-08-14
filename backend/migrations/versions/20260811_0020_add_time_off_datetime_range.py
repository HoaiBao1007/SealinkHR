"""Add precise date-time ranges to Time Off requests.

Revision ID: 20260811_0020
Revises: 20260811_0019
Create Date: 2026-08-11
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260811_0020"
down_revision: Union[str, None] = "20260811_0019"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Nullable keeps imported and legacy requests valid. The API derives a
    # conventional working-time range from start_date/end_date/day_part when
    # these values are absent.
    with op.batch_alter_table("off_requests") as batch_op:
        batch_op.add_column(sa.Column("start_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("end_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.create_index("ix_off_requests_start_at", ["start_at"])
        batch_op.create_index("ix_off_requests_end_at", ["end_at"])


def downgrade() -> None:
    with op.batch_alter_table("off_requests") as batch_op:
        batch_op.drop_index("ix_off_requests_end_at")
        batch_op.drop_index("ix_off_requests_start_at")
        batch_op.drop_column("end_at")
        batch_op.drop_column("start_at")
