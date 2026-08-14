"""Open bonus payout notifications in the Commission workspace.

Revision ID: 20260803_0015
Revises: 20260803_0014
Create Date: 2026-08-03
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260803_0015"
down_revision: Union[str, None] = "20260803_0014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    metadata = sa.MetaData()
    notifications = sa.Table("notifications", metadata, autoload_with=bind)
    bind.execute(
        notifications.update()
        .where(notifications.c.event_type == "BONUS_PAYOUT_REQUESTED")
        .values(action_url="/admin/commission")
    )


def downgrade() -> None:
    bind = op.get_bind()
    metadata = sa.MetaData()
    notifications = sa.Table("notifications", metadata, autoload_with=bind)
    bind.execute(
        notifications.update()
        .where(notifications.c.event_type == "BONUS_PAYOUT_REQUESTED")
        .values(action_url="/admin/salary-matrix")
    )
