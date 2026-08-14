"""Merge reviewed duplicate employee profiles without losing operational history.

The canonical profiles contain the approved English name/contact information.
The duplicate profiles were created from alternate biometric IDs and must not
remain as separate employees.

Dry-run:
    python scripts/merge_duplicate_employee_profiles.py

Apply:
    python scripts/merge_duplicate_employee_profiles.py --apply
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from sqlalchemy import inspect, text


BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_DIR = BACKEND_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.db.session import SessionLocal, engine  # noqa: E402
from app.models.attendance_daily import AttendanceDaily  # noqa: E402
from app.models.attendance_log import AttendanceLog  # noqa: E402
from app.models.employee import Employee  # noqa: E402
from app.models.monthly_salary_input import MonthlySalaryInput  # noqa: E402
from app.models.organization import OrganizationAssignment, OrganizationUnit  # noqa: E402
from app.models.timesheet import Timesheet  # noqa: E402
from app.models.timesheet_entry import TimesheetEntry  # noqa: E402


@dataclass(frozen=True)
class MergePair:
    canonical_id: int
    duplicate_id: int
    expected_name: str
    expected_english_name: str


MERGE_PAIRS = (
    MergePair(20, 57, "Phan Quốc Long", "DINO LONG"),
    MergePair(41, 59, "Nguyễn Trần Phương", "MICHAEL PHUONG"),
)


def _json_default(value: object) -> str | float:
    if isinstance(value, Decimal):
        return float(value)
    return str(value)


def _backup_affected_rows(employee_ids: list[int]) -> Path:
    """Create a local JSON backup of every FK row affected by the merge."""

    inspector = inspect(engine)
    payload: dict[str, object] = {
        "created_at": datetime.now().isoformat(),
        "employee_ids": employee_ids,
        "tables": {},
    }
    tables: dict[str, list[dict[str, object]]] = {}
    placeholders = ", ".join(f":id_{index}" for index, _ in enumerate(employee_ids))
    parameters = {f"id_{index}": value for index, value in enumerate(employee_ids)}

    with engine.connect() as connection:
        employee_rows = connection.execute(
            text(f"SELECT * FROM employees WHERE id IN ({placeholders})"),
            parameters,
        ).mappings().all()
        tables["employees"] = [dict(row) for row in employee_rows]

        for table_name in sorted(inspector.get_table_names()):
            if table_name == "employees":
                continue
            employee_columns: set[str] = set()
            for foreign_key in inspector.get_foreign_keys(table_name):
                if foreign_key.get("referred_table") == "employees":
                    employee_columns.update(foreign_key.get("constrained_columns") or [])
            if not employee_columns:
                continue
            predicates = [
                f"`{column}` IN ({placeholders})" for column in sorted(employee_columns)
            ]
            rows = connection.execute(
                text(f"SELECT * FROM `{table_name}` WHERE {' OR '.join(predicates)}"),
                parameters,
            ).mappings().all()
            if rows:
                tables[table_name] = [dict(row) for row in rows]

    payload["tables"] = tables
    backup_dir = PROJECT_DIR / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup_path = backup_dir / (
        f"employee-duplicate-merge-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
    )
    backup_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=_json_default),
        encoding="utf-8",
    )
    return backup_path


def _verify_pair(canonical: Employee | None, duplicate: Employee | None, pair: MergePair) -> None:
    if canonical is None or duplicate is None:
        raise RuntimeError(
            f"Không tìm thấy đủ hồ sơ cho cặp {pair.canonical_id}/{pair.duplicate_id}."
        )
    if canonical.full_name.casefold() != duplicate.full_name.casefold():
        raise RuntimeError(
            f"Hai hồ sơ {canonical.id}/{duplicate.id} không cùng tên; dừng để tránh gộp nhầm."
        )
    if canonical.full_name.casefold() != pair.expected_name.casefold():
        raise RuntimeError(
            f"Hồ sơ chuẩn {canonical.id} không còn là {pair.expected_name}; cần rà soát lại."
        )
    if (canonical.notion_name or "").casefold() != pair.expected_english_name.casefold():
        raise RuntimeError(
            f"Tên tiếng Anh của hồ sơ chuẩn {canonical.id} đã thay đổi; cần rà soát lại."
        )
    if duplicate.notion_name and (
        duplicate.notion_name.casefold() != canonical.notion_name.casefold()
    ):
        raise RuntimeError(
            f"Hồ sơ {duplicate.id} có tên tiếng Anh khác hồ sơ chuẩn; không tự động gộp."
        )
    if canonical.department_id != duplicate.department_id:
        raise RuntimeError(
            f"Hai hồ sơ {canonical.id}/{duplicate.id} đang ở hai phòng ban khác nhau."
        )


def _merge_employee_fields(canonical: Employee, duplicate: Employee) -> None:
    if canonical.biometric_id is None:
        canonical.biometric_id = duplicate.machine_employee_id
    elif canonical.biometric_id != duplicate.machine_employee_id:
        raise RuntimeError(
            f"Hồ sơ {canonical.id} đã có mã sinh trắc học {canonical.biometric_id}; "
            f"không thể tự gán thêm {duplicate.machine_employee_id}."
        )

    optional_fields = (
        "position",
        "start_date",
        "account_number",
        "bank_name",
        "tax_code",
        "social_insurance_number",
        "pvi_insurance",
        "health_insurance_number",
        "personal_email",
        "notes",
        "cccd_url",
        "contract_url",
    )
    for field_name in optional_fields:
        if getattr(canonical, field_name) in (None, "") and getattr(duplicate, field_name) not in (
            None,
            "",
        ):
            setattr(canonical, field_name, getattr(duplicate, field_name))

    if canonical.contract_salary <= 0 < duplicate.contract_salary:
        canonical.contract_salary = duplicate.contract_salary
    canonical.annual_leave_used = max(
        canonical.annual_leave_used or 0, duplicate.annual_leave_used or 0
    )
    canonical.paid_leave_balance = max(
        canonical.paid_leave_balance or 0, duplicate.paid_leave_balance or 0
    )
    canonical.unpaid_leave_balance = max(
        canonical.unpaid_leave_balance or 0, duplicate.unpaid_leave_balance or 0
    )


def _merge_attendance_logs(db, canonical_id: int, duplicate_id: int) -> int:
    merged = 0
    duplicate_rows = (
        db.query(AttendanceLog)
        .filter(AttendanceLog.employee_id == duplicate_id)
        .order_by(AttendanceLog.id)
        .all()
    )
    for row in duplicate_rows:
        existing = (
            db.query(AttendanceLog)
            .filter(
                AttendanceLog.employee_id == canonical_id,
                AttendanceLog.work_date == row.work_date,
                AttendanceLog.upload_batch_id == row.upload_batch_id,
            )
            .first()
        )
        if existing is None:
            row.employee_id = canonical_id
        else:
            for field_name in (
                "raw_time_values",
                "first_check_in",
                "last_check_out",
                "missing_reason",
                "note",
            ):
                if getattr(existing, field_name) in (None, ""):
                    setattr(existing, field_name, getattr(row, field_name))
            existing.late_minutes = max(existing.late_minutes or 0, row.late_minutes or 0)
            existing.early_minutes = max(existing.early_minutes or 0, row.early_minutes or 0)
            existing.missing_flag = bool(existing.missing_flag or row.missing_flag)
            db.delete(row)
        merged += 1
    return merged


def _merge_attendance_daily(db, canonical_id: int, duplicate_id: int) -> int:
    merged = 0
    duplicate_rows = (
        db.query(AttendanceDaily)
        .filter(AttendanceDaily.employee_id == duplicate_id)
        .order_by(AttendanceDaily.work_date)
        .all()
    )
    for row in duplicate_rows:
        existing = (
            db.query(AttendanceDaily)
            .filter(
                AttendanceDaily.employee_id == canonical_id,
                AttendanceDaily.work_date == row.work_date,
            )
            .first()
        )
        if existing is None:
            row.employee_id = canonical_id
            merged += 1
            continue

        duplicate_is_authoritative = (row.source_priority or 0) >= (
            existing.source_priority or 0
        )
        if duplicate_is_authoritative:
            existing.attendance_symbol = row.attendance_symbol
            existing.period_start = row.period_start
            existing.period_end = row.period_end
            existing.late_minutes = row.late_minutes
            existing.early_minutes = row.early_minutes
            existing.abnormal_level = row.abnormal_level
            existing.source_priority = row.source_priority
            if row.generated_from_batch_id is not None:
                existing.generated_from_batch_id = row.generated_from_batch_id
        if row.check_in_time:
            existing.check_in_time = row.check_in_time
        if row.check_out_time:
            existing.check_out_time = row.check_out_time
        db.delete(row)
        merged += 1
    return merged


def _copy_timesheet_totals(target: Timesheet, source: Timesheet) -> None:
    for field_name in (
        "total_work_days",
        "total_late_minutes",
        "total_absent_days",
        "total_paid_leave_days",
        "total_unpaid_leave_days",
        "total_business_trip_days",
        "approval_status",
        "approved_at",
    ):
        setattr(target, field_name, getattr(source, field_name))
    if source.approved_by_user_id is not None:
        target.approved_by_user_id = source.approved_by_user_id


def _merge_timesheets(db, canonical_id: int, duplicate_id: int) -> int:
    merged = 0
    duplicate_sheets = (
        db.query(Timesheet)
        .filter(Timesheet.employee_id == duplicate_id)
        .order_by(Timesheet.period_start, Timesheet.id)
        .all()
    )
    for duplicate_sheet in duplicate_sheets:
        canonical_sheet = (
            db.query(Timesheet)
            .filter(
                Timesheet.employee_id == canonical_id,
                Timesheet.period_start == duplicate_sheet.period_start,
                Timesheet.period_end == duplicate_sheet.period_end,
            )
            .first()
        )
        if canonical_sheet is None:
            duplicate_sheet.employee_id = canonical_id
            db.query(TimesheetEntry).filter(
                TimesheetEntry.timesheet_id == duplicate_sheet.id
            ).update(
                {TimesheetEntry.employee_id: canonical_id},
                synchronize_session=False,
            )
            merged += 1
            continue

        source_is_newer = (duplicate_sheet.updated_at or duplicate_sheet.created_at) >= (
            canonical_sheet.updated_at or canonical_sheet.created_at
        )
        if source_is_newer:
            _copy_timesheet_totals(canonical_sheet, duplicate_sheet)

        duplicate_entries = (
            db.query(TimesheetEntry)
            .filter(TimesheetEntry.timesheet_id == duplicate_sheet.id)
            .order_by(TimesheetEntry.work_date)
            .all()
        )
        for row in duplicate_entries:
            existing = (
                db.query(TimesheetEntry)
                .filter(
                    TimesheetEntry.timesheet_id == canonical_sheet.id,
                    TimesheetEntry.employee_id == canonical_id,
                    TimesheetEntry.work_date == row.work_date,
                )
                .first()
            )
            if existing is None:
                row.timesheet_id = canonical_sheet.id
                row.employee_id = canonical_id
                continue
            if source_is_newer:
                existing.original_symbol = row.original_symbol
                existing.final_symbol = row.final_symbol
                existing.late_minutes = row.late_minutes
                existing.early_minutes = row.early_minutes
                existing.is_overridden = row.is_overridden
                existing.override_reason = row.override_reason
                existing.overridden_by_user_id = row.overridden_by_user_id
                existing.overridden_at = row.overridden_at
            if row.check_in_time:
                existing.check_in_time = row.check_in_time
            if row.check_out_time:
                existing.check_out_time = row.check_out_time
            db.delete(row)
        db.flush()
        db.delete(duplicate_sheet)
        merged += 1
    return merged


def _merge_monthly_salary_inputs(db, canonical_id: int, duplicate_id: int) -> int:
    merged = 0
    duplicate_rows = (
        db.query(MonthlySalaryInput)
        .filter(MonthlySalaryInput.employee_id == duplicate_id)
        .order_by(MonthlySalaryInput.salary_period, MonthlySalaryInput.id)
        .all()
    )
    fill_zero_fields = (
        "actual_working_days",
        "meal_allowance_free",
        "meal_allowance_tax",
        "phone_allowance_free",
        "trans_allowance_tax",
        "perf_allowance_tax",
        "other_income",
        "bonus",
        "advance_payment",
        "pit_refund",
        "other_deductions",
        "bonus_14",
        "contract_salary",
        "dependents_count",
    )
    fill_empty_fields = (
        "fullname",
        "employee_type",
        "position",
        "account_number",
        "bank_name",
        "mid_month_effective_date",
    )
    for row in duplicate_rows:
        existing = (
            db.query(MonthlySalaryInput)
            .filter(
                MonthlySalaryInput.employee_id == canonical_id,
                MonthlySalaryInput.salary_period == row.salary_period,
            )
            .order_by(MonthlySalaryInput.id)
            .first()
        )
        if existing is None:
            row.employee_id = canonical_id
            merged += 1
            continue

        for field_name in fill_zero_fields:
            if getattr(existing, field_name) in (None, 0, 0.0) and getattr(
                row, field_name
            ) not in (None, 0, 0.0):
                setattr(existing, field_name, getattr(row, field_name))
        for field_name in fill_empty_fields:
            if getattr(existing, field_name) in (None, "") and getattr(row, field_name) not in (
                None,
                "",
            ):
                setattr(existing, field_name, getattr(row, field_name))
        existing.is_published = bool(existing.is_published or row.is_published)
        db.delete(row)
        merged += 1
    return merged


def _merge_organization(db, canonical_id: int, duplicate_id: int) -> int:
    merged = 0
    duplicate_assignments = (
        db.query(OrganizationAssignment)
        .filter(OrganizationAssignment.employee_id == duplicate_id)
        .order_by(OrganizationAssignment.id)
        .all()
    )
    for assignment in duplicate_assignments:
        equivalent = (
            db.query(OrganizationAssignment)
            .filter(
                OrganizationAssignment.employee_id == canonical_id,
                OrganizationAssignment.org_unit_id == assignment.org_unit_id,
                OrganizationAssignment.effective_from == assignment.effective_from,
                OrganizationAssignment.effective_to == assignment.effective_to,
            )
            .first()
        )
        if equivalent is None:
            assignment.employee_id = canonical_id
        else:
            if not equivalent.position_title and assignment.position_title:
                equivalent.position_title = assignment.position_title
            equivalent.display_order = min(
                equivalent.display_order, assignment.display_order
            )
            db.delete(assignment)
        merged += 1

    db.query(OrganizationAssignment).filter(
        OrganizationAssignment.reports_to_employee_id == duplicate_id
    ).update(
        {OrganizationAssignment.reports_to_employee_id: canonical_id},
        synchronize_session=False,
    )
    db.query(OrganizationUnit).filter(
        OrganizationUnit.leader_employee_id == duplicate_id
    ).update(
        {OrganizationUnit.leader_employee_id: canonical_id},
        synchronize_session=False,
    )
    return merged


def _repoint_simple_references(db, canonical_id: int, duplicate_id: int) -> None:
    """Repoint non-conflicting employee foreign keys not merged above."""

    statements = (
        ("attendance_override_audit", "employee_id"),
        ("off_requests", "employee_id"),
        ("salary_decisions", "employee_id"),
        ("commission_wallet_ledger", "employee_id"),
        ("commission_bonus_entitlements", "employee_id"),
        ("commission_calculation_snapshots", "employee_id"),
        ("commission_payout_policies", "employee_id"),
        ("commission_payout_schedules", "employee_id"),
    )
    inspector = inspect(engine)
    available_tables = set(inspector.get_table_names())
    for table_name, column_name in statements:
        if table_name not in available_tables:
            continue
        db.execute(
            text(
                f"UPDATE `{table_name}` SET `{column_name}` = :canonical_id "
                f"WHERE `{column_name}` = :duplicate_id"
            ),
            {"canonical_id": canonical_id, "duplicate_id": duplicate_id},
        )

    if "departments" in available_tables:
        db.execute(
            text(
                "UPDATE departments SET manager_id = :canonical_id "
                "WHERE manager_id = :duplicate_id"
            ),
            {"canonical_id": canonical_id, "duplicate_id": duplicate_id},
        )


def merge_pair(db, pair: MergePair) -> dict[str, object]:
    canonical = db.query(Employee).filter(Employee.id == pair.canonical_id).first()
    duplicate = db.query(Employee).filter(Employee.id == pair.duplicate_id).first()
    _verify_pair(canonical, duplicate, pair)
    assert canonical is not None and duplicate is not None

    _merge_employee_fields(canonical, duplicate)
    summary = {
        "canonical_id": canonical.id,
        "duplicate_id": duplicate.id,
        "name": canonical.full_name,
        "alternate_biometric_id": duplicate.machine_employee_id,
        "attendance_logs": _merge_attendance_logs(db, canonical.id, duplicate.id),
        "attendance_daily": _merge_attendance_daily(db, canonical.id, duplicate.id),
        "timesheets": _merge_timesheets(db, canonical.id, duplicate.id),
        "monthly_salary_inputs": _merge_monthly_salary_inputs(
            db, canonical.id, duplicate.id
        ),
        "organization_assignments": _merge_organization(
            db, canonical.id, duplicate.id
        ),
    }
    _repoint_simple_references(db, canonical.id, duplicate.id)
    db.flush()
    db.delete(duplicate)
    db.flush()
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Commit changes. Without this flag the command performs a rollback.",
    )
    args = parser.parse_args()

    affected_ids = [
        employee_id
        for pair in MERGE_PAIRS
        for employee_id in (pair.canonical_id, pair.duplicate_id)
    ]
    backup_path = _backup_affected_rows(affected_ids) if args.apply else None

    with SessionLocal() as db:
        summaries = [merge_pair(db, pair) for pair in MERGE_PAIRS]
        print(json.dumps(summaries, ensure_ascii=False, indent=2, default=_json_default))
        if args.apply:
            db.commit()
            print(f"ĐÃ COMMIT. Backup trước khi gộp: {backup_path}")
        else:
            db.rollback()
            print("DRY-RUN: chưa thay đổi database. Dùng --apply để xác nhận.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
