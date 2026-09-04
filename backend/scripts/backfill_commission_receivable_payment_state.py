"""Backfill AGEING payment snapshots and exact wallet holds for linked JOBs.

Dry-run by default. ``--apply`` writes a JSON backup before changing only
commission JOB reconciliation fields and additive wallet-ledger rows.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.api.commission_api import _employee_id_for_sales_rep, _wallet_positions
from app.db.session import SessionLocal
from app.models.commission import (
    CommissionJob,
    CommissionJobReceivableAttachment,
    CommissionJobReceivableLink,
    CommissionWalletLedger,
)
from app.services.commission_receivable_parser import normalize_receivable_job_no, parse_receivable_workbook


UPLOAD_DIR = BACKEND_ROOT / "uploads" / "commission_receivables"


def _snapshot(job: CommissionJob, current_hold: float) -> dict[str, Any]:
    return {
        "job_id": job.id,
        "period_id": job.period_id,
        "job_no": job.job_no,
        "sales_rep": job.sales_rep,
        "payment_received": job.payment_received,
        "receivable_amount": job.receivable_amount,
        "balance_amount": job.balance_amount,
        "payment_received_amount": job.payment_received_amount,
        "hold_bonus_percent": job.hold_bonus_percent,
        "hold_bonus_amount": job.hold_bonus_amount,
        "wallet_payment_hold": current_hold,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill payment state from stored AGEING evidence.")
    parser.add_argument("--apply", action="store_true", help="Backup and apply the scoped changes.")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        links = db.query(CommissionJobReceivableLink).order_by(
            CommissionJobReceivableLink.created_at.desc(),
            CommissionJobReceivableLink.id.desc(),
        ).all()
        latest_by_job: dict[int, CommissionJobReceivableLink] = {}
        for link in links:
            latest_by_job.setdefault(link.job_id, link)

        planned: list[dict[str, Any]] = []
        for link in latest_by_job.values():
            job = db.get(CommissionJob, link.job_id)
            attachment = db.get(CommissionJobReceivableAttachment, link.attachment_id)
            if not job or not attachment:
                continue
            source_path = UPLOAD_DIR / attachment.stored_filename
            if not source_path.is_file():
                raise RuntimeError(f"Missing AGEING evidence: {source_path}")
            parsed = parse_receivable_workbook(source_path.read_bytes(), attachment.original_filename)
            report_by_no = {row.job_no: row for row in parsed.jobs}
            report = report_by_no.get(normalize_receivable_job_no(job.job_no))
            if not report:
                continue

            entries = db.query(CommissionWalletLedger).filter(
                CommissionWalletLedger.period_id == job.period_id,
                CommissionWalletLedger.job_id == job.id,
            ).order_by(CommissionWalletLedger.id).all()
            position = _wallet_positions(entries).get((job.sales_rep or "(Unknown)", job.id), {})
            current_hold = round(float(position.get("payment_held", 0.0)), 2)
            hold_amount = round(float(job.hold_bonus_amount or 0.0), 2)
            paid_amount = round(
                report.received_amount
                if report.received_amount > 0
                else max(0.0, report.receivable_amount - report.balance_amount),
                2,
            )
            planned.append({
                "job": job,
                "report": report,
                "entries": entries,
                "position": position,
                "before": _snapshot(job, current_hold),
                "paid_amount": paid_amount,
                "hold_amount": hold_amount,
                "hold_delta": round(hold_amount - current_hold, 2),
                "attachment_id": attachment.id,
            })

        print(f"Linked JOBs eligible for backfill: {len(planned)}")
        for item in planned:
            job = item["job"]
            print(
                f"- #{job.id} {job.job_no}: Payment {job.payment_received or 'NO'} -> YES; "
                f"paid={item['paid_amount']:,.2f}; hold={item['before']['wallet_payment_hold']:,.2f} "
                f"-> {item['hold_amount']:,.2f}"
            )
        if not args.apply:
            print("DRY RUN only. Re-run with --apply to save the scoped changes.")
            return 0

        backup_dir = BACKEND_ROOT / "output"
        backup_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = backup_dir / f"commission_receivable_payment_backup_{stamp}.json"
        backup_path.write_text(
            json.dumps([item["before"] for item in planned], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        actor = "system-backfill-receivable-payment"
        for item in planned:
            job = item["job"]
            report = item["report"]
            job.payment_received = "YES"
            job.receivable_amount = report.receivable_amount
            job.balance_amount = report.balance_amount
            job.payment_received_amount = item["paid_amount"]
            job.hold_bonus_percent = round(float(job.hold_bonus_percent or report.hold_bonus_percent), 4)
            job.hold_bonus_amount = item["hold_amount"]
            delta = item["hold_delta"]
            if abs(delta) >= 0.01 and item["entries"]:
                first_entry = item["entries"][0]
                db.add(CommissionWalletLedger(
                    period_id=job.period_id,
                    job_id=job.id,
                    entitlement_id=first_entry.entitlement_id,
                    sales_rep=job.sales_rep or "(Unknown)",
                    employee_id=_employee_id_for_sales_rep(job.sales_rep or "(Unknown)", db),
                    entry_type="PAYMENT_STATUS_HOLD" if delta > 0 else "RELEASED",
                    amount=abs(delta),
                    reason_code="RECEIVABLE_BACKFILL",
                    note=(
                        f"Backfill AGEING attachment #{item['attachment_id']}: "
                        f"giữ đúng Hold Bonus {item['hold_amount']:,.2f}; "
                        f"khách đã trả {item['paid_amount']:,.2f}."
                    ),
                    created_by=actor,
                ))
        db.commit()
        print(f"Applied {len(planned)} JOB updates. Backup: {backup_path}")
        return 0
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
