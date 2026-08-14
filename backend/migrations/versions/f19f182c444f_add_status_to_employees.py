"""add status to employees

Revision ID: f19f182c444f
Revises: 01ee345f8ac2
Create Date: 2026-06-19 09:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f19f182c444f'
down_revision: Union[str, None] = '01ee345f8ac2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Safely add column if it does not exist
    try:
        op.add_column('employees', sa.Column('status', sa.String(length=50), nullable=False, server_default='ACTIVE'))
    except Exception as e:
        print(f"Note: Could not add column 'status' to table 'employees' (it may already exist): {e}")


def downgrade() -> None:
    try:
        op.drop_column('employees', 'status')
    except Exception as e:
        print(f"Note: Could not drop column 'status' from table 'employees': {e}")
