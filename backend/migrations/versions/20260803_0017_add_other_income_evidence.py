"""Add note and private evidence metadata for other salary income.

Revision ID: 20260803_0017
Revises: 20260803_0016
Create Date: 2026-08-03
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260803_0017"
down_revision: Union[str, None] = "20260803_0016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("monthly_salary_inputs", sa.Column("other_income_note", sa.Text(), nullable=True))
    op.add_column("monthly_salary_inputs", sa.Column("other_income_document_path", sa.String(length=500), nullable=True))
    op.add_column("monthly_salary_inputs", sa.Column("other_income_document_name", sa.String(length=255), nullable=True))
    op.add_column("monthly_salary_inputs", sa.Column("other_income_document_content_type", sa.String(length=150), nullable=True))
    op.add_column("monthly_salary_inputs", sa.Column("other_income_document_size", sa.Integer(), nullable=True))
    op.add_column("monthly_salary_inputs", sa.Column("other_income_document_uploaded_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("monthly_salary_inputs", "other_income_document_uploaded_at")
    op.drop_column("monthly_salary_inputs", "other_income_document_size")
    op.drop_column("monthly_salary_inputs", "other_income_document_content_type")
    op.drop_column("monthly_salary_inputs", "other_income_document_name")
    op.drop_column("monthly_salary_inputs", "other_income_document_path")
    op.drop_column("monthly_salary_inputs", "other_income_note")
