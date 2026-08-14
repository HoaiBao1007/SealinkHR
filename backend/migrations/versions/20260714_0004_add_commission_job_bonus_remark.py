"""add bonus remark to commission jobs

Revision ID: 20260714_0004
Revises: 20260713_0003
"""
from alembic import op
import sqlalchemy as sa


revision = "20260714_0004"
down_revision = "20260713_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("commission_jobs", sa.Column("bonus_remark", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("commission_jobs", "bonus_remark")
