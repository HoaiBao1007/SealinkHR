"""Add notion_name to employees.

Revision ID: 20260519_0001
Revises:
Create Date: 2026-05-19 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260519_0001"
down_revision: Union[str, None] = "20260518_0000"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None



TABLE_NAME = "employees"
COLUMN_NAME = "notion_name"
INDEX_NAME = "ix_employees_notion_name"


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table(TABLE_NAME):
        return

    columns = {column["name"] for column in inspector.get_columns(TABLE_NAME)}
    if COLUMN_NAME not in columns:
        op.add_column(TABLE_NAME, sa.Column(COLUMN_NAME, sa.String(length=150), nullable=True))

    indexes = {index["name"] for index in inspector.get_indexes(TABLE_NAME)}
    unique_constraints = {constraint["name"] for constraint in inspector.get_unique_constraints(TABLE_NAME)}
    if INDEX_NAME not in indexes and INDEX_NAME not in unique_constraints:
        op.create_index(INDEX_NAME, TABLE_NAME, [COLUMN_NAME], unique=True)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table(TABLE_NAME):
        return

    indexes = {index["name"] for index in inspector.get_indexes(TABLE_NAME)}
    unique_constraints = {constraint["name"] for constraint in inspector.get_unique_constraints(TABLE_NAME)}
    if INDEX_NAME in indexes or INDEX_NAME in unique_constraints:
        op.drop_index(INDEX_NAME, table_name=TABLE_NAME)

    columns = {column["name"] for column in inspector.get_columns(TABLE_NAME)}
    if COLUMN_NAME in columns:
        op.drop_column(TABLE_NAME, COLUMN_NAME)
