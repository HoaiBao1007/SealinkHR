"""Add organization units and employee organization assignments.

Revision ID: 20260729_0008
Revises: 20260728_0007
"""

from alembic import op
import sqlalchemy as sa


revision = "20260729_0008"
down_revision = "20260728_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "organization_units",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("code", sa.String(length=80), nullable=False),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("unit_type", sa.String(length=40), nullable=False, server_default="TEAM"),
        sa.Column("parent_id", sa.Integer(), nullable=True),
        sa.Column("linked_department_id", sa.Integer(), nullable=True),
        sa.Column("leader_employee_id", sa.Integer(), nullable=True),
        sa.Column("color", sa.String(length=20), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["parent_id"], ["organization_units.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["linked_department_id"], ["departments.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["leader_employee_id"], ["employees.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("code", name="uq_organization_units_code"),
    )
    op.create_index("ix_organization_units_code", "organization_units", ["code"], unique=True)
    op.create_index("ix_organization_units_parent_id", "organization_units", ["parent_id"])
    op.create_index(
        "ix_organization_units_linked_department_id",
        "organization_units",
        ["linked_department_id"],
    )
    op.create_index(
        "ix_organization_units_leader_employee_id",
        "organization_units",
        ["leader_employee_id"],
    )

    op.create_table(
        "organization_assignments",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("employee_id", sa.Integer(), nullable=False),
        sa.Column("org_unit_id", sa.Integer(), nullable=False),
        sa.Column("reports_to_employee_id", sa.Integer(), nullable=True),
        sa.Column("position_title", sa.String(length=150), nullable=True),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("source", sa.String(length=80), nullable=False),
        sa.Column("confidence", sa.Numeric(4, 3), nullable=False, server_default="1.000"),
        sa.Column("effective_from", sa.Date(), nullable=True),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["employee_id"], ["employees.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["org_unit_id"], ["organization_units.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["reports_to_employee_id"], ["employees.id"], ondelete="SET NULL"),
    )
    op.create_index(
        "ix_organization_assignments_employee_id",
        "organization_assignments",
        ["employee_id"],
    )
    op.create_index(
        "ix_organization_assignments_org_unit_id",
        "organization_assignments",
        ["org_unit_id"],
    )
    op.create_index(
        "ix_organization_assignments_reports_to_employee_id",
        "organization_assignments",
        ["reports_to_employee_id"],
    )
    op.create_index(
        "ix_org_assignments_employee_effective_to",
        "organization_assignments",
        ["employee_id", "effective_to"],
    )


def downgrade() -> None:
    op.drop_index("ix_org_assignments_employee_effective_to", table_name="organization_assignments")
    op.drop_index(
        "ix_organization_assignments_reports_to_employee_id",
        table_name="organization_assignments",
    )
    op.drop_index("ix_organization_assignments_org_unit_id", table_name="organization_assignments")
    op.drop_index("ix_organization_assignments_employee_id", table_name="organization_assignments")
    op.drop_table("organization_assignments")

    op.drop_index("ix_organization_units_leader_employee_id", table_name="organization_units")
    op.drop_index("ix_organization_units_linked_department_id", table_name="organization_units")
    op.drop_index("ix_organization_units_parent_id", table_name="organization_units")
    op.drop_index("ix_organization_units_code", table_name="organization_units")
    op.drop_table("organization_units")
