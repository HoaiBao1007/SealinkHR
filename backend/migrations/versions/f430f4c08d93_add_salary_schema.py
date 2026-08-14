"""add_salary_schema

Revision ID: f430f4c08d93
Revises: 20260519_0001
Create Date: 2026-06-08 16:11:18.184800

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision: str = 'f430f4c08d93'
down_revision: Union[str, None] = '20260519_0001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def safe_drop_constraint(constraint_name, table_name, type_='foreignkey'):
    from alembic import op
    from alembic.operations import Operations
    try:
        ctx = op.get_context()
        Operations(ctx).drop_constraint(constraint_name, table_name, type_=type_)
    except Exception as e:
        print(f"Ignored error dropping constraint {constraint_name} on {table_name}: {e}")

def safe_drop_index(index_name, table_name=None, **kw):
    from alembic import op
    from alembic.operations import Operations
    try:
        ctx = op.get_context()
        Operations(ctx).drop_index(index_name, table_name=table_name, **kw)
    except Exception as e:
        print(f"Ignored error dropping index {index_name} on {table_name}: {e}")

def safe_drop_column(table_name, column_name, **kw):
    from alembic import op
    from alembic.operations import Operations
    try:
        ctx = op.get_context()
        Operations(ctx).drop_column(table_name, column_name, **kw)
    except Exception as e:
        print(f"Ignored error dropping column {column_name} on {table_name}: {e}")

def safe_create_index(index_name, table_name, columns, **kw):
    from alembic import op
    from alembic.operations import Operations
    try:
        ctx = op.get_context()
        Operations(ctx).create_index(index_name, table_name, columns, **kw)
    except Exception as e:
        print(f"Ignored error creating index {index_name} on {table_name}: {e}")

def safe_create_foreign_key(constraint_name, source_table, referent_table, local_cols, remote_cols, **kw):
    from alembic import op
    from alembic.operations import Operations
    try:
        ctx = op.get_context()
        Operations(ctx).create_foreign_key(constraint_name, source_table, referent_table, local_cols, remote_cols, **kw)
    except Exception as e:
        print(f"Ignored error creating foreign key {constraint_name} on {source_table}: {e}")

def safe_create_unique_constraint(constraint_name, table_name, columns, **kw):
    from alembic import op
    from alembic.operations import Operations
    try:
        ctx = op.get_context()
        Operations(ctx).create_unique_constraint(constraint_name, table_name, columns, **kw)
    except Exception as e:
        print(f"Ignored error creating unique constraint {constraint_name} on {table_name}: {e}")

def upgrade() -> None:

    # Create monthly_salary_inputs table
    try:
        op.create_table(
            'monthly_salary_inputs',
            sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
            sa.Column('employee_id', sa.Integer(), nullable=False),
            sa.Column('salary_period', sa.String(length=7), nullable=False),
            sa.Column('actual_working_days', sa.Float(), nullable=False, server_default='0.0'),
            sa.Column('meal_allowance_free', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('meal_allowance_tax', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('phone_allowance_free', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('trans_allowance_tax', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('perf_allowance_tax', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('other_income', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('bonus', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('advance_payment', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('pit_refund', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('other_deductions', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
            sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
            sa.PrimaryKeyConstraint('id'),
            sa.ForeignKeyConstraint(['employee_id'], ['employees.id'], ondelete='CASCADE'),
            mysql_engine='InnoDB',
            mysql_charset='utf8mb4',
            mysql_collate='utf8mb4_unicode_ci'
        )
        safe_create_index('ix_monthly_salary_inputs_employee_id', 'monthly_salary_inputs', ['employee_id'], unique=False)
        safe_create_index('ix_monthly_salary_inputs_salary_period', 'monthly_salary_inputs', ['salary_period'], unique=False)
        print("Successfully created monthly_salary_inputs table in migration")
    except Exception as e:
        print(f"Ignored error creating monthly_salary_inputs: {e}")

    # Drop constraints first to avoid MySQL NOT NULL errors
    for constraint, table in [
        ('attendance_daily_ibfk_1', 'attendance_daily'),
        ('attendance_logs_ibfk_2', 'attendance_logs'),
        ('attendance_logs_ibfk_1', 'attendance_logs'),
        ('attendance_overrides_audit_ibfk_1', 'attendance_overrides_audit'),
        ('off_requests_ibfk_1', 'off_requests'),
        ('timesheet_entries_ibfk_1', 'timesheet_entries'),
        ('timesheets_ibfk_1', 'timesheets'),
    ]:
        try:
            safe_drop_constraint(constraint, table, type_='foreignkey')
        except Exception:
            pass

    # ### commands auto generated by Alembic - please adjust! ###
    op.alter_column('attendance_daily', 'employee_id',
               existing_type=mysql.INTEGER(display_width=11),
               nullable=False)
    op.alter_column('attendance_daily', 'check_in_time',
               existing_type=mysql.TIME(),
               type_=sa.String(length=8),
               existing_nullable=True)
    op.alter_column('attendance_daily', 'check_out_time',
               existing_type=mysql.TIME(),
               type_=sa.String(length=8),
               existing_nullable=True)
    op.alter_column('attendance_daily', 'attendance_symbol',
               existing_type=mysql.VARCHAR(length=20),
               type_=sa.String(length=10),
               nullable=False)
    safe_drop_index('ix_attendance_daily_id', table_name='attendance_daily')
    safe_drop_index('uq_attendance_daily_emp_date', table_name='attendance_daily')
    safe_create_index('ix_attendance_daily_employee_date', 'attendance_daily', ['employee_id', 'work_date'], unique=False)
    safe_create_index(op.f('ix_attendance_daily_employee_id'), 'attendance_daily', ['employee_id'], unique=False)
    safe_create_unique_constraint('uq_attendance_daily_employee_date', 'attendance_daily', ['employee_id', 'work_date'])

    safe_create_foreign_key(None, 'attendance_daily', 'employees', ['employee_id'], ['id'])
    
    # Add missing columns to attendance_daily
    try:
        op.add_column('attendance_daily', sa.Column('period_start', sa.Date(), nullable=True))
        op.add_column('attendance_daily', sa.Column('period_end', sa.Date(), nullable=True))
        op.add_column('attendance_daily', sa.Column('abnormal_level', sa.String(length=10), nullable=True))
        op.add_column('attendance_daily', sa.Column('source_priority', sa.SmallInteger(), nullable=False, server_default='1'))
        op.add_column('attendance_daily', sa.Column('generated_from_batch_id', sa.Integer(), nullable=True))
        op.add_column('attendance_daily', sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=True))
        op.add_column('attendance_daily', sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=True))
        print("Successfully added missing columns to attendance_daily")
    except Exception as e:
        print(f"Ignored error adding columns to attendance_daily: {e}")

    safe_create_foreign_key(None, 'attendance_daily', 'upload_batches', ['generated_from_batch_id'], ['id'])
    safe_drop_column('attendance_daily', 'machine_employee_id')
    safe_drop_column('attendance_daily', 'is_abnormal')
    safe_drop_column('attendance_daily', 'source')
    safe_drop_column('attendance_daily', 'is_absent')
    op.add_column('attendance_logs', sa.Column('first_check_in', sa.String(length=8), nullable=True))
    op.add_column('attendance_logs', sa.Column('last_check_out', sa.String(length=8), nullable=True))
    op.add_column('attendance_logs', sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False))
    op.alter_column('attendance_logs', 'upload_batch_id',
               existing_type=mysql.INTEGER(display_width=11),
               nullable=False)
    op.alter_column('attendance_logs', 'employee_id',
               existing_type=mysql.INTEGER(display_width=11),
               nullable=False)
    op.alter_column('attendance_logs', 'missing_reason',
               existing_type=mysql.VARCHAR(length=255),
               type_=sa.String(length=100),
               existing_nullable=True)
    op.alter_column('attendance_logs', 'note',
               existing_type=mysql.VARCHAR(length=500),
               type_=sa.Text(),
               existing_nullable=True)
    safe_drop_index('ix_attendance_logs_id', table_name='attendance_logs')
    safe_drop_index('ix_attendance_logs_machine_employee_id', table_name='attendance_logs')
    safe_drop_index('uq_attendance_logs_machine_date', table_name='attendance_logs')
    safe_create_index('ix_attendance_logs_employee_date_batch', 'attendance_logs', ['employee_id', 'work_date', 'upload_batch_id'], unique=False)
    safe_create_index(op.f('ix_attendance_logs_employee_id'), 'attendance_logs', ['employee_id'], unique=False)
    safe_create_index(op.f('ix_attendance_logs_upload_batch_id'), 'attendance_logs', ['upload_batch_id'], unique=False)
    safe_create_unique_constraint('uq_attendance_logs_employee_date_batch', 'attendance_logs', ['employee_id', 'work_date', 'upload_batch_id'])


    safe_create_foreign_key(None, 'attendance_logs', 'upload_batches', ['upload_batch_id'], ['id'])
    safe_create_foreign_key(None, 'attendance_logs', 'employees', ['employee_id'], ['id'])
    safe_drop_column('attendance_logs', 'check_out_time')
    safe_drop_column('attendance_logs', 'period_start')
    safe_drop_column('attendance_logs', 'check_in_time')
    safe_drop_column('attendance_logs', 'employee_not_found')
    safe_drop_column('attendance_logs', 'period_end')
    safe_drop_column('attendance_logs', 'full_name')
    safe_drop_column('attendance_logs', 'department_name')
    safe_drop_column('attendance_logs', 'machine_employee_id')
    op.alter_column('attendance_overrides_audit', 'employee_id',
               existing_type=mysql.INTEGER(display_width=11),
               nullable=False)
    op.alter_column('attendance_overrides_audit', 'old_symbol',
               existing_type=mysql.VARCHAR(length=20),
               type_=sa.String(length=10),
               nullable=False)
    op.alter_column('attendance_overrides_audit', 'new_symbol',
               existing_type=mysql.VARCHAR(length=20),
               type_=sa.String(length=10),
               nullable=False)
    op.alter_column('attendance_overrides_audit', 'old_check_in',
               existing_type=mysql.VARCHAR(length=20),
               type_=sa.String(length=8),
               existing_nullable=True)
    op.alter_column('attendance_overrides_audit', 'new_check_in',
               existing_type=mysql.VARCHAR(length=20),
               type_=sa.String(length=8),
               existing_nullable=True)
    op.alter_column('attendance_overrides_audit', 'old_check_out',
               existing_type=mysql.VARCHAR(length=20),
               type_=sa.String(length=8),
               existing_nullable=True)
    op.alter_column('attendance_overrides_audit', 'new_check_out',
               existing_type=mysql.VARCHAR(length=20),
               type_=sa.String(length=8),
               existing_nullable=True)
    op.alter_column('attendance_overrides_audit', 'reason',
               existing_type=mysql.VARCHAR(length=500),
               type_=sa.String(length=255),
               existing_nullable=False)
    op.alter_column('attendance_overrides_audit', 'changed_by_user_id',
               existing_type=mysql.VARCHAR(length=50),
               type_=sa.Integer(),
               nullable=False)
    safe_drop_index('ix_attendance_overrides_audit_id', table_name='attendance_overrides_audit')
    safe_create_index(op.f('ix_attendance_overrides_audit_employee_id'), 'attendance_overrides_audit', ['employee_id'], unique=False)

    safe_create_foreign_key(None, 'attendance_overrides_audit', 'employees', ['employee_id'], ['id'])
    safe_create_foreign_key(None, 'attendance_overrides_audit', 'employees', ['changed_by_user_id'], ['id'])
    safe_drop_column('attendance_overrides_audit', 'changed_by_name')
    safe_drop_column('attendance_overrides_audit', 'machine_employee_id')
    safe_drop_column('attendance_overrides_audit', 'employee_name')
    op.add_column('employees', sa.Column('employee_code', sa.String(length=50), nullable=True))
    op.add_column('employees', sa.Column('position', sa.String(length=150), nullable=True))
    op.add_column('employees', sa.Column('contract_salary', sa.Integer(), nullable=False))
    op.add_column('employees', sa.Column('employee_type', sa.String(length=50), nullable=False))
    op.add_column('employees', sa.Column('dependents_count', sa.Integer(), nullable=False))
    op.add_column('employees', sa.Column('account_number', sa.String(length=50), nullable=True))
    op.add_column('employees', sa.Column('bank_name', sa.String(length=150), nullable=True))
    op.alter_column('employees', 'annual_leave_quota',
               existing_type=mysql.INTEGER(display_width=11),
               type_=sa.Numeric(precision=5, scale=2),
               existing_nullable=False,
               existing_server_default=sa.text('12'))
    op.alter_column('employees', 'annual_leave_used',
               existing_type=mysql.DECIMAL(precision=4, scale=1),
               type_=sa.Numeric(precision=5, scale=2),
               existing_nullable=False,
               existing_server_default=sa.text('0.0'))
    op.alter_column('employees', 'paid_leave_balance',
               existing_type=mysql.DECIMAL(precision=4, scale=1),
               type_=sa.Numeric(precision=5, scale=2),
               existing_nullable=False,
               existing_server_default=sa.text('0.0'))
    op.alter_column('employees', 'unpaid_leave_balance',
               existing_type=mysql.DECIMAL(precision=4, scale=1),
               type_=sa.Numeric(precision=5, scale=2),
               existing_nullable=False,
               existing_server_default=sa.text('0.0'))
    safe_drop_index('ix_employees_id', table_name='employees')
    safe_drop_index('uq_employees_machine_employee_id', table_name='employees')
    safe_create_index(op.f('ix_employees_employee_code'), 'employees', ['employee_code'], unique=True)
    op.add_column('off_requests', sa.Column('request_type', sa.String(length=20), nullable=False))
    op.add_column('off_requests', sa.Column('start_date', sa.Date(), nullable=False))
    op.add_column('off_requests', sa.Column('end_date', sa.Date(), nullable=False))
    op.add_column('off_requests', sa.Column('total_days', sa.Numeric(precision=5, scale=2), nullable=False))
    op.add_column('off_requests', sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('off_requests', sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False))
    op.alter_column('off_requests', 'employee_id',
               existing_type=mysql.INTEGER(display_width=11),
               nullable=False)
    op.alter_column('off_requests', 'reason',
               existing_type=mysql.VARCHAR(length=500),
               type_=sa.String(length=255),
               existing_nullable=True)
    op.alter_column('off_requests', 'status',
               existing_type=mysql.VARCHAR(length=50),
               type_=sa.String(length=20),
               existing_nullable=False,
               existing_server_default=sa.text("'pending'"))
    safe_drop_index('ix_off_requests_id', table_name='off_requests')
    safe_create_index(op.f('ix_off_requests_employee_id'), 'off_requests', ['employee_id'], unique=False)

    safe_create_foreign_key(None, 'off_requests', 'employees', ['employee_id'], ['id'])
    safe_create_foreign_key(None, 'off_requests', 'employees', ['approved_by_user_id'], ['id'])
    safe_drop_column('off_requests', 'off_type')
    safe_drop_column('off_requests', 'is_paid')
    safe_drop_column('off_requests', 'request_date')
    op.add_column('timesheet_entries', sa.Column('employee_id', sa.Integer(), nullable=False))
    op.add_column('timesheet_entries', sa.Column('override_reason', sa.String(length=255), nullable=True))
    op.add_column('timesheet_entries', sa.Column('overridden_by_user_id', sa.Integer(), nullable=True))
    op.add_column('timesheet_entries', sa.Column('overridden_at', sa.DateTime(timezone=True), nullable=True))
    op.alter_column('timesheet_entries', 'timesheet_id',
               existing_type=mysql.INTEGER(display_width=11),
               nullable=False)
    op.alter_column('timesheet_entries', 'original_symbol',
               existing_type=mysql.VARCHAR(length=20),
               type_=sa.String(length=10),
               nullable=False)
    op.alter_column('timesheet_entries', 'final_symbol',
               existing_type=mysql.VARCHAR(length=20),
               type_=sa.String(length=10),
               nullable=False)
    op.alter_column('timesheet_entries', 'check_in_time',
               existing_type=mysql.TIME(),
               type_=sa.String(length=8),
               existing_nullable=True)
    op.alter_column('timesheet_entries', 'check_out_time',
               existing_type=mysql.TIME(),
               type_=sa.String(length=8),
               existing_nullable=True)
    safe_drop_index('ix_timesheet_entries_id', table_name='timesheet_entries')
    safe_drop_index('uq_timesheet_entries_ts_date', table_name='timesheet_entries')
    safe_create_index('ix_timesheet_entries_employee_date_timesheet', 'timesheet_entries', ['employee_id', 'work_date', 'timesheet_id'], unique=False)
    safe_create_index(op.f('ix_timesheet_entries_employee_id'), 'timesheet_entries', ['employee_id'], unique=False)
    safe_create_index(op.f('ix_timesheet_entries_timesheet_id'), 'timesheet_entries', ['timesheet_id'], unique=False)
    safe_create_index(op.f('ix_timesheet_entries_work_date'), 'timesheet_entries', ['work_date'], unique=False)
    safe_create_unique_constraint('uq_timesheet_entries_employee_date_timesheet', 'timesheet_entries', ['employee_id', 'work_date', 'timesheet_id'])

    safe_create_foreign_key(None, 'timesheet_entries', 'employees', ['employee_id'], ['id'])
    safe_create_foreign_key(None, 'timesheet_entries', 'employees', ['overridden_by_user_id'], ['id'])
    safe_create_foreign_key(None, 'timesheet_entries', 'timesheets', ['timesheet_id'], ['id'])
    op.add_column('timesheets', sa.Column('total_work_days', sa.Numeric(precision=5, scale=2), nullable=False))
    op.add_column('timesheets', sa.Column('total_late_minutes', sa.Integer(), nullable=False))
    op.add_column('timesheets', sa.Column('total_absent_days', sa.Numeric(precision=5, scale=2), nullable=False))
    op.add_column('timesheets', sa.Column('total_paid_leave_days', sa.Numeric(precision=5, scale=2), nullable=False))
    op.add_column('timesheets', sa.Column('total_unpaid_leave_days', sa.Numeric(precision=5, scale=2), nullable=False))
    op.add_column('timesheets', sa.Column('total_business_trip_days', sa.Numeric(precision=5, scale=2), nullable=False))
    op.add_column('timesheets', sa.Column('approval_status', sa.String(length=20), nullable=False))
    op.alter_column('timesheets', 'employee_id',
               existing_type=mysql.INTEGER(display_width=11),
               nullable=False)
    safe_drop_index('ix_timesheets_id', table_name='timesheets')
    safe_drop_index('ix_timesheets_period_start', table_name='timesheets')
    safe_drop_index('uq_timesheets_emp_period', table_name='timesheets')
    safe_create_index(op.f('ix_timesheets_employee_id'), 'timesheets', ['employee_id'], unique=False)
    safe_create_index('ix_timesheets_employee_period', 'timesheets', ['employee_id', 'period_start', 'period_end'], unique=False)
    safe_create_unique_constraint('uq_timesheets_employee_period', 'timesheets', ['employee_id', 'period_start', 'period_end'])

    safe_create_foreign_key(None, 'timesheets', 'employees', ['employee_id'], ['id'])
    safe_create_foreign_key(None, 'timesheets', 'employees', ['approved_by_user_id'], ['id'])
    safe_drop_column('timesheets', 'status')
    op.add_column('upload_batches', sa.Column('source_type', sa.String(length=30), nullable=False))
    op.add_column('upload_batches', sa.Column('file_hash', sa.String(length=128), nullable=False))
    op.add_column('upload_batches', sa.Column('period_start', sa.Date(), nullable=False))
    op.add_column('upload_batches', sa.Column('period_end', sa.Date(), nullable=False))
    op.add_column('upload_batches', sa.Column('error_message', sa.Text(), nullable=True))
    op.alter_column('upload_batches', 'uploaded_by_user_id',
               existing_type=mysql.INTEGER(display_width=11),
               nullable=False)
    op.alter_column('upload_batches', 'file_name',
               existing_type=mysql.VARCHAR(length=255),
               nullable=False)
    op.alter_column('upload_batches', 'status',
               existing_type=mysql.VARCHAR(length=50),
               type_=sa.String(length=20),
               existing_nullable=False,
               existing_server_default=sa.text("'pending'"))
    safe_drop_index('ix_upload_batches_id', table_name='upload_batches')
    safe_create_index(op.f('ix_upload_batches_file_hash'), 'upload_batches', ['file_hash'], unique=False)
    safe_create_index(op.f('ix_upload_batches_uploaded_by_user_id'), 'upload_batches', ['uploaded_by_user_id'], unique=False)
    safe_create_foreign_key(None, 'upload_batches', 'employees', ['uploaded_by_user_id'], ['id'])
    safe_drop_column('upload_batches', 'row_count')
    safe_drop_column('upload_batches', 'import_type')
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('upload_batches', sa.Column('import_type', mysql.VARCHAR(length=50), nullable=False))
    op.add_column('upload_batches', sa.Column('row_count', mysql.INTEGER(display_width=11), server_default=sa.text('0'), autoincrement=False, nullable=False))
    safe_drop_constraint(None, 'upload_batches', type_='foreignkey')
    safe_drop_index(op.f('ix_upload_batches_uploaded_by_user_id'), table_name='upload_batches')
    safe_drop_index(op.f('ix_upload_batches_file_hash'), table_name='upload_batches')
    safe_create_index('ix_upload_batches_id', 'upload_batches', ['id'], unique=False)
    op.alter_column('upload_batches', 'status',
               existing_type=sa.String(length=20),
               type_=mysql.VARCHAR(length=50),
               existing_nullable=False,
               existing_server_default=sa.text("'pending'"))
    op.alter_column('upload_batches', 'file_name',
               existing_type=mysql.VARCHAR(length=255),
               nullable=True)
    op.alter_column('upload_batches', 'uploaded_by_user_id',
               existing_type=mysql.INTEGER(display_width=11),
               nullable=True)
    safe_drop_column('upload_batches', 'error_message')
    safe_drop_column('upload_batches', 'period_end')
    safe_drop_column('upload_batches', 'period_start')
    safe_drop_column('upload_batches', 'file_hash')
    safe_drop_column('upload_batches', 'source_type')
    op.add_column('timesheets', sa.Column('status', mysql.VARCHAR(length=50), server_default=sa.text("'draft'"), nullable=False))
    safe_drop_constraint(None, 'timesheets', type_='foreignkey')
    safe_drop_constraint(None, 'timesheets', type_='foreignkey')
    safe_create_foreign_key('timesheets_ibfk_1', 'timesheets', 'employees', ['employee_id'], ['id'], ondelete='SET NULL')
    safe_drop_constraint('uq_timesheets_employee_period', 'timesheets', type_='unique')
    safe_drop_index('ix_timesheets_employee_period', table_name='timesheets')
    safe_drop_index(op.f('ix_timesheets_employee_id'), table_name='timesheets')
    safe_create_index('uq_timesheets_emp_period', 'timesheets', ['employee_id', 'period_start'], unique=True)
    safe_create_index('ix_timesheets_period_start', 'timesheets', ['period_start'], unique=False)
    safe_create_index('ix_timesheets_id', 'timesheets', ['id'], unique=False)
    op.alter_column('timesheets', 'employee_id',
               existing_type=mysql.INTEGER(display_width=11),
               nullable=True)
    safe_drop_column('timesheets', 'approval_status')
    safe_drop_column('timesheets', 'total_business_trip_days')
    safe_drop_column('timesheets', 'total_unpaid_leave_days')
    safe_drop_column('timesheets', 'total_paid_leave_days')
    safe_drop_column('timesheets', 'total_absent_days')
    safe_drop_column('timesheets', 'total_late_minutes')
    safe_drop_column('timesheets', 'total_work_days')
    safe_drop_constraint(None, 'timesheet_entries', type_='foreignkey')
    safe_drop_constraint(None, 'timesheet_entries', type_='foreignkey')
    safe_drop_constraint(None, 'timesheet_entries', type_='foreignkey')
    safe_create_foreign_key('timesheet_entries_ibfk_1', 'timesheet_entries', 'timesheets', ['timesheet_id'], ['id'], ondelete='CASCADE')
    safe_drop_constraint('uq_timesheet_entries_employee_date_timesheet', 'timesheet_entries', type_='unique')
    safe_drop_index(op.f('ix_timesheet_entries_work_date'), table_name='timesheet_entries')
    safe_drop_index(op.f('ix_timesheet_entries_timesheet_id'), table_name='timesheet_entries')
    safe_drop_index(op.f('ix_timesheet_entries_employee_id'), table_name='timesheet_entries')
    safe_drop_index('ix_timesheet_entries_employee_date_timesheet', table_name='timesheet_entries')
    safe_create_index('uq_timesheet_entries_ts_date', 'timesheet_entries', ['timesheet_id', 'work_date'], unique=True)
    safe_create_index('ix_timesheet_entries_id', 'timesheet_entries', ['id'], unique=False)
    op.alter_column('timesheet_entries', 'check_out_time',
               existing_type=sa.String(length=8),
               type_=mysql.TIME(),
               existing_nullable=True)
    op.alter_column('timesheet_entries', 'check_in_time',
               existing_type=sa.String(length=8),
               type_=mysql.TIME(),
               existing_nullable=True)
    op.alter_column('timesheet_entries', 'final_symbol',
               existing_type=sa.String(length=10),
               type_=mysql.VARCHAR(length=20),
               nullable=True)
    op.alter_column('timesheet_entries', 'original_symbol',
               existing_type=sa.String(length=10),
               type_=mysql.VARCHAR(length=20),
               nullable=True)
    op.alter_column('timesheet_entries', 'timesheet_id',
               existing_type=mysql.INTEGER(display_width=11),
               nullable=True)
    safe_drop_column('timesheet_entries', 'overridden_at')
    safe_drop_column('timesheet_entries', 'overridden_by_user_id')
    safe_drop_column('timesheet_entries', 'override_reason')
    safe_drop_column('timesheet_entries', 'employee_id')
    op.add_column('off_requests', sa.Column('request_date', sa.DATE(), nullable=False))
    op.add_column('off_requests', sa.Column('is_paid', mysql.TINYINT(display_width=1), server_default=sa.text('1'), autoincrement=False, nullable=False))
    op.add_column('off_requests', sa.Column('off_type', mysql.VARCHAR(length=50), nullable=False))
    safe_drop_constraint(None, 'off_requests', type_='foreignkey')
    safe_drop_constraint(None, 'off_requests', type_='foreignkey')
    safe_create_foreign_key('off_requests_ibfk_1', 'off_requests', 'employees', ['employee_id'], ['id'], ondelete='SET NULL')
    safe_drop_index(op.f('ix_off_requests_employee_id'), table_name='off_requests')
    safe_create_index('ix_off_requests_id', 'off_requests', ['id'], unique=False)
    op.alter_column('off_requests', 'status',
               existing_type=sa.String(length=20),
               type_=mysql.VARCHAR(length=50),
               existing_nullable=False,
               existing_server_default=sa.text("'pending'"))
    op.alter_column('off_requests', 'reason',
               existing_type=sa.String(length=255),
               type_=mysql.VARCHAR(length=500),
               existing_nullable=True)
    op.alter_column('off_requests', 'employee_id',
               existing_type=mysql.INTEGER(display_width=11),
               nullable=True)
    safe_drop_column('off_requests', 'updated_at')
    safe_drop_column('off_requests', 'approved_at')
    safe_drop_column('off_requests', 'total_days')
    safe_drop_column('off_requests', 'end_date')
    safe_drop_column('off_requests', 'start_date')
    safe_drop_column('off_requests', 'request_type')
    safe_drop_index(op.f('ix_employees_employee_code'), table_name='employees')
    safe_create_index('uq_employees_machine_employee_id', 'employees', ['machine_employee_id'], unique=True)
    safe_create_index('ix_employees_id', 'employees', ['id'], unique=False)
    op.alter_column('employees', 'unpaid_leave_balance',
               existing_type=sa.Numeric(precision=5, scale=2),
               type_=mysql.DECIMAL(precision=4, scale=1),
               existing_nullable=False,
               existing_server_default=sa.text('0.0'))
    op.alter_column('employees', 'paid_leave_balance',
               existing_type=sa.Numeric(precision=5, scale=2),
               type_=mysql.DECIMAL(precision=4, scale=1),
               existing_nullable=False,
               existing_server_default=sa.text('0.0'))
    op.alter_column('employees', 'annual_leave_used',
               existing_type=sa.Numeric(precision=5, scale=2),
               type_=mysql.DECIMAL(precision=4, scale=1),
               existing_nullable=False,
               existing_server_default=sa.text('0.0'))
    op.alter_column('employees', 'annual_leave_quota',
               existing_type=sa.Numeric(precision=5, scale=2),
               type_=mysql.INTEGER(display_width=11),
               existing_nullable=False,
               existing_server_default=sa.text('12'))
    safe_drop_column('employees', 'bank_name')
    safe_drop_column('employees', 'account_number')
    safe_drop_column('employees', 'dependents_count')
    safe_drop_column('employees', 'employee_type')
    safe_drop_column('employees', 'contract_salary')
    safe_drop_column('employees', 'position')
    safe_drop_column('employees', 'employee_code')
    op.add_column('attendance_overrides_audit', sa.Column('employee_name', mysql.VARCHAR(length=150), nullable=True))
    op.add_column('attendance_overrides_audit', sa.Column('machine_employee_id', mysql.VARCHAR(length=50), nullable=True))
    op.add_column('attendance_overrides_audit', sa.Column('changed_by_name', mysql.VARCHAR(length=150), nullable=True))
    safe_drop_constraint(None, 'attendance_overrides_audit', type_='foreignkey')
    safe_drop_constraint(None, 'attendance_overrides_audit', type_='foreignkey')
    safe_create_foreign_key('attendance_overrides_audit_ibfk_1', 'attendance_overrides_audit', 'employees', ['employee_id'], ['id'], ondelete='SET NULL')
    safe_drop_index(op.f('ix_attendance_overrides_audit_employee_id'), table_name='attendance_overrides_audit')
    safe_create_index('ix_attendance_overrides_audit_id', 'attendance_overrides_audit', ['id'], unique=False)
    op.alter_column('attendance_overrides_audit', 'changed_by_user_id',
               existing_type=sa.Integer(),
               type_=mysql.VARCHAR(length=50),
               nullable=True)
    op.alter_column('attendance_overrides_audit', 'reason',
               existing_type=sa.String(length=255),
               type_=mysql.VARCHAR(length=500),
               existing_nullable=False)
    op.alter_column('attendance_overrides_audit', 'new_check_out',
               existing_type=sa.String(length=8),
               type_=mysql.VARCHAR(length=20),
               existing_nullable=True)
    op.alter_column('attendance_overrides_audit', 'old_check_out',
               existing_type=sa.String(length=8),
               type_=mysql.VARCHAR(length=20),
               existing_nullable=True)
    op.alter_column('attendance_overrides_audit', 'new_check_in',
               existing_type=sa.String(length=8),
               type_=mysql.VARCHAR(length=20),
               existing_nullable=True)
    op.alter_column('attendance_overrides_audit', 'old_check_in',
               existing_type=sa.String(length=8),
               type_=mysql.VARCHAR(length=20),
               existing_nullable=True)
    op.alter_column('attendance_overrides_audit', 'new_symbol',
               existing_type=sa.String(length=10),
               type_=mysql.VARCHAR(length=20),
               nullable=True)
    op.alter_column('attendance_overrides_audit', 'old_symbol',
               existing_type=sa.String(length=10),
               type_=mysql.VARCHAR(length=20),
               nullable=True)
    op.alter_column('attendance_overrides_audit', 'employee_id',
               existing_type=mysql.INTEGER(display_width=11),
               nullable=True)
    op.add_column('attendance_logs', sa.Column('machine_employee_id', mysql.VARCHAR(length=50), nullable=False))
    op.add_column('attendance_logs', sa.Column('department_name', mysql.VARCHAR(length=150), nullable=True))
    op.add_column('attendance_logs', sa.Column('full_name', mysql.VARCHAR(length=150), nullable=True))
    op.add_column('attendance_logs', sa.Column('period_end', sa.DATE(), nullable=True))
    op.add_column('attendance_logs', sa.Column('employee_not_found', mysql.TINYINT(display_width=1), server_default=sa.text('0'), autoincrement=False, nullable=False))
    op.add_column('attendance_logs', sa.Column('check_in_time', mysql.TIME(), nullable=True))
    op.add_column('attendance_logs', sa.Column('period_start', sa.DATE(), nullable=True))
    op.add_column('attendance_logs', sa.Column('check_out_time', mysql.TIME(), nullable=True))
    safe_drop_constraint(None, 'attendance_logs', type_='foreignkey')
    safe_drop_constraint(None, 'attendance_logs', type_='foreignkey')
    safe_create_foreign_key('attendance_logs_ibfk_1', 'attendance_logs', 'employees', ['employee_id'], ['id'], ondelete='SET NULL')
    safe_create_foreign_key('attendance_logs_ibfk_2', 'attendance_logs', 'upload_batches', ['upload_batch_id'], ['id'], ondelete='SET NULL')
    safe_drop_constraint('uq_attendance_logs_employee_date_batch', 'attendance_logs', type_='unique')
    safe_drop_index(op.f('ix_attendance_logs_upload_batch_id'), table_name='attendance_logs')
    safe_drop_index(op.f('ix_attendance_logs_employee_id'), table_name='attendance_logs')
    safe_drop_index('ix_attendance_logs_employee_date_batch', table_name='attendance_logs')
    safe_create_index('uq_attendance_logs_machine_date', 'attendance_logs', ['machine_employee_id', 'work_date'], unique=True)
    safe_create_index('ix_attendance_logs_machine_employee_id', 'attendance_logs', ['machine_employee_id'], unique=False)
    safe_create_index('ix_attendance_logs_id', 'attendance_logs', ['id'], unique=False)
    op.alter_column('attendance_logs', 'note',
               existing_type=sa.Text(),
               type_=mysql.VARCHAR(length=500),
               existing_nullable=True)
    op.alter_column('attendance_logs', 'missing_reason',
               existing_type=sa.String(length=100),
               type_=mysql.VARCHAR(length=255),
               existing_nullable=True)
    op.alter_column('attendance_logs', 'employee_id',
               existing_type=mysql.INTEGER(display_width=11),
               nullable=True)
    op.alter_column('attendance_logs', 'upload_batch_id',
               existing_type=mysql.INTEGER(display_width=11),
               nullable=True)
    safe_drop_column('attendance_logs', 'created_at')
    safe_drop_column('attendance_logs', 'last_check_out')
    safe_drop_column('attendance_logs', 'first_check_in')
    op.add_column('attendance_daily', sa.Column('is_absent', mysql.TINYINT(display_width=1), server_default=sa.text('0'), autoincrement=False, nullable=False))
    op.add_column('attendance_daily', sa.Column('source', mysql.VARCHAR(length=50), nullable=True))
    op.add_column('attendance_daily', sa.Column('is_abnormal', mysql.TINYINT(display_width=1), server_default=sa.text('0'), autoincrement=False, nullable=False))
    op.add_column('attendance_daily', sa.Column('machine_employee_id', mysql.VARCHAR(length=50), nullable=False))
    safe_drop_constraint(None, 'attendance_daily', type_='foreignkey')
    safe_drop_constraint(None, 'attendance_daily', type_='foreignkey')
    safe_create_foreign_key('attendance_daily_ibfk_1', 'attendance_daily', 'employees', ['employee_id'], ['id'], ondelete='SET NULL')
    safe_drop_constraint('uq_attendance_daily_employee_date', 'attendance_daily', type_='unique')
    safe_drop_index(op.f('ix_attendance_daily_employee_id'), table_name='attendance_daily')
    safe_drop_index('ix_attendance_daily_employee_date', table_name='attendance_daily')
    safe_create_index('uq_attendance_daily_emp_date', 'attendance_daily', ['employee_id', 'work_date'], unique=True)
    safe_create_index('ix_attendance_daily_id', 'attendance_daily', ['id'], unique=False)
    op.alter_column('attendance_daily', 'attendance_symbol',
               existing_type=sa.String(length=10),
               type_=mysql.VARCHAR(length=20),
               nullable=True)
    op.alter_column('attendance_daily', 'check_out_time',
               existing_type=sa.String(length=8),
               type_=mysql.TIME(),
               existing_nullable=True)
    op.alter_column('attendance_daily', 'check_in_time',
               existing_type=sa.String(length=8),
               type_=mysql.TIME(),
               existing_nullable=True)
    op.alter_column('attendance_daily', 'employee_id',
               existing_type=mysql.INTEGER(display_width=11),
               nullable=True)
    # ### end Alembic commands ###

