"""Backup and clear stale commission payout schedules only.

Dry-run by default. ``--apply`` removes payout schedules and their allocation
rows after proving that no immutable wallet-ledger entry references them.
Commission jobs, entitlements, wallet ledger, employees and payroll data are
never modified by this command.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.db.session import SessionLocal
from app.models.commission import (
    CommissionBonusEntitlement,
    CommissionJob,
    CommissionPayoutSchedule,
    CommissionPayoutScheduleAllocation,
    CommissionWalletLedger,
)
from app.models.employee import Employee
from app.models.monthly_salary_input import MonthlySalaryInput


def _json_value(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    return value


def _model_dict(row: Any) -> dict[str, Any]:
    return {
        column.name: _json_value(getattr(row, column.name))
        for column in row.__table__.columns
    }


def _preservation_counts(db: Any) -> dict[str, int]:
    return {
        "employees": db.query(Employee).count(),
        "monthly_salary_inputs": db.query(MonthlySalaryInput).count(),
        "commission_jobs": db.query(CommissionJob).count(),
        "commission_bonus_entitlements": db.query(CommissionBonusEntitlement).count(),
        "commission_wallet_ledger": db.query(CommissionWalletLedger).count(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Clear payout schedule UI rows without touching commission sources.")
    parser.add_argument("--apply", action="store_true", help="Create backup and perform the reset.")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        schedules = db.query(CommissionPayoutSchedule).order_by(CommissionPayoutSchedule.id).all()
        schedule_ids = [row.id for row in schedules]
        allocations = (
            db.query(CommissionPayoutScheduleAllocation)
            .filter(CommissionPayoutScheduleAllocation.schedule_id.in_(schedule_ids))
            .order_by(CommissionPayoutScheduleAllocation.id)
            .all()
            if schedule_ids else []
        )
        ledger_refs = (
            db.query(CommissionWalletLedger)
            .filter(CommissionWalletLedger.schedule_id.in_(schedule_ids))
            .count()
            if schedule_ids else 0
        )
        preservation_before = _preservation_counts(db)

        status_counts: dict[str, int] = {}
        for row in schedules:
            status_counts[row.status] = status_counts.get(row.status, 0) + 1
        periods = sorted({row.payout_period for row in schedules})

        print(f"Payout schedules to clear: {len(schedules)}")
        print(f"Schedule allocations to clear: {len(allocations)}")
        print(f"Statuses: {status_counts}")
        print(f"Payout periods: {', '.join(periods) or '(none)'}")
        print(f"Wallet ledger references: {ledger_refs}")
        print(f"Preserved table counts: {preservation_before}")

        if ledger_refs:
            raise RuntimeError("Reset refused: wallet ledger entries still reference payout schedules.")
        if not args.apply:
            print("DRY RUN ONLY - no database data was changed.")
            return 0

        backup_root = Path(__file__).resolve().parents[2] / "backups"
        backup_root.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = backup_root / f"commission_payout_schedule_reset_{timestamp}.json"
        temporary_path = backup_path.with_suffix(backup_path.suffix + ".tmp")
        payload = {
            "schema_version": 1,
            "operation": "reset_commission_payout_schedules",
            "created_at": datetime.now().astimezone().isoformat(),
            "scope": {
                "deleted_tables": [
                    "commission_payout_schedule_allocations",
                    "commission_payout_schedules",
                ],
                "preserved_tables": list(preservation_before),
            },
            "preservation_counts": preservation_before,
            "commission_payout_schedules": [_model_dict(row) for row in schedules],
            "commission_payout_schedule_allocations": [_model_dict(row) for row in allocations],
        }
        backup_bytes = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")
        temporary_path.write_bytes(backup_bytes)
        os.replace(temporary_path, backup_path)

        if schedule_ids:
            db.query(CommissionPayoutScheduleAllocation).filter(
                CommissionPayoutScheduleAllocation.schedule_id.in_(schedule_ids)
            ).delete(synchronize_session=False)
            db.query(CommissionPayoutSchedule).filter(
                CommissionPayoutSchedule.id.in_(schedule_ids)
            ).delete(synchronize_session=False)

        db.flush()
        remaining_schedules = db.query(CommissionPayoutSchedule).count()
        remaining_allocations = db.query(CommissionPayoutScheduleAllocation).count()
        preservation_after = _preservation_counts(db)
        if remaining_schedules or remaining_allocations:
            raise RuntimeError(
                f"Post-reset verification failed: schedules={remaining_schedules}, allocations={remaining_allocations}"
            )
        if preservation_after != preservation_before:
            raise RuntimeError("A protected table changed; transaction will roll back.")

        db.commit()
        print(f"Backup: {backup_path}")
        print(f"Backup SHA256: {hashlib.sha256(backup_bytes).hexdigest()}")
        print("RESET COMPLETE - only payout schedules and allocations were removed.")
        return 0
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
