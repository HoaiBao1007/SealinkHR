"""Use one named unique index for offboarding public identifiers.

Revision ID: 20260828_0038
Revises: 20260828_0037
Create Date: 2026-08-28
"""

from typing import Sequence, Union

from alembic import op


revision: str = "20260828_0038"
down_revision: Union[str, None] = "20260828_0037"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_index("ix_offboarding_requests_public_id", table_name="offboarding_requests")
    op.drop_constraint("public_id", "offboarding_requests", type_="unique")
    op.create_index(
        "ix_offboarding_requests_public_id",
        "offboarding_requests",
        ["public_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_offboarding_requests_public_id", table_name="offboarding_requests")
    op.create_unique_constraint("public_id", "offboarding_requests", ["public_id"])
    op.create_index(
        "ix_offboarding_requests_public_id",
        "offboarding_requests",
        ["public_id"],
        unique=False,
    )
