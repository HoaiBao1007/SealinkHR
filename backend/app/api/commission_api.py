"""
commission_api.py
-----------------
API endpoints để lưu và truy vấn dữ liệu Commission / Job PnL từ Climax.

Endpoints:
  POST /api/commission/import          - Lưu dữ liệu từ frontend sau khi user xác nhận
  GET  /api/commission/periods         - Danh sách các kỳ đã import
  GET  /api/commission/periods/{id}    - Chi tiết 1 kỳ + tất cả jobs
  GET  /api/commission/summary         - Tóm tắt theo Sales Rep (GROUP BY)
  DELETE /api/commission/periods/{id}  - Xóa 1 kỳ (và tất cả jobs)
"""
from datetime import date, datetime, timezone
from pathlib import Path
from typing import List, Optional, Literal
import json
import re
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_admin_user
from app.models.commission import CommissionBonusLock, CommissionJob, CommissionJobReceivableAttachment, CommissionJobReceivableLink, CommissionPeriod, CommissionPayoutPolicy, CommissionRepOverride, CommissionWalletLedger, CommissionCalculationSnapshot, CommissionBonusEntitlement, CommissionPayoutSchedule, CommissionPayoutScheduleAllocation, CommissionPaymentVerification
from app.services.commission_receivable_parser import FIXED_HOLD_BONUS_PERCENT, ReceivableJobBalance, parse_receivable_workbook, normalize_receivable_job_no
from app.services.notification_service import BONUS, actor_id, add_employee_notification

router = APIRouter(
    prefix="/api/commission",
    tags=["commission"],
    dependencies=[Depends(get_admin_user)],
)

COMMISSION_RECEIVABLE_UPLOAD_DIR = Path(__file__).resolve().parents[2] / "uploads" / "commission_receivables"
COMMISSION_RECEIVABLE_MAX_FILE_SIZE = 15 * 1024 * 1024
COMMISSION_RECEIVABLE_MAX_FILES = 10
COMMISSION_RECEIVABLE_ALLOWED_EXTENSIONS = {
    ".pdf", ".xlsx", ".xls", ".csv", ".doc", ".docx", ".png", ".jpg", ".jpeg",
}


# ══════════════════════════════════════════════════════
# Pydantic schemas
# ══════════════════════════════════════════════════════

class JobRowIn(BaseModel):
    job_no: str
    job_date: Optional[str] = None       # "DD/MM/YYYY" hoặc ISO
    hbl: Optional[str] = None
    mbl: Optional[str] = None
    customer: Optional[str] = None
    vendor: Optional[str] = None
    sales_rep: Optional[str] = None
    shipper: Optional[str] = None
    consignee: Optional[str] = None
    sub_type: Optional[str] = None
    container_string: Optional[str] = None
    wt: Optional[float] = None
    vol: Optional[float] = None
    carrier_booking_no: Optional[str] = None
    por: Optional[str] = None
    final_destination: Optional[str] = None
    realized_revenue: float = 0.0
    unrealized_revenue: float = 0.0
    realized_cost: float = 0.0
    unrealized_cost: float = 0.0
    profit_loss: float = 0.0
    container_picked: Optional[str] = None
    payment_received: Optional[str] = None


class CommissionImportIn(BaseModel):
    period_label: str                    # e.g. "Q2-2026" hoặc "05.2026"
    from_date: Optional[str] = None      # ISO date string
    till_date: Optional[str] = None
    source_filename: Optional[str] = None
    note: Optional[str] = None
    jobs: List[JobRowIn]


class CommissionImportBatchIn(BaseModel):
    imports: List[CommissionImportIn]


class CommissionImportMergeIn(BaseModel):
    imports: List[CommissionImportIn]
    overwrite_manual_job_ids: List[int] = Field(default_factory=list)


class CommissionRepOverrideIn(BaseModel):
    override_job_count: Optional[int] = None
    override_profit_loss: Optional[float] = None
    override_target: Optional[float] = None
    override_bonus_rate: Optional[float] = None
    override_total_bonus: Optional[float] = None
    override_monthly_bonus: Optional[float] = None
    remark: Optional[str] = None


class CommissionWalletSyncIn(BaseModel):
    period_id: Optional[int] = None


class CommissionPayoutIn(BaseModel):
    sales_rep: str
    amount: Optional[float] = None
    payout_period: Optional[str] = None
    note: Optional[str] = None
    # When the wallet is opened from a saved commission row, payment must be
    # scoped to that source period instead of consuming another period's JOBs.
    source_period_id: Optional[int] = None


class CommissionPayoutPolicyIn(BaseModel):
    payout_mode: str = "MANUAL"
    minimum_amount: float = 0.0
    is_active: bool = True


class CommissionJobPaymentIn(BaseModel):
    payment_received: str
    remark: Optional[str] = None
    # New payout commands release a previously-held JOB once, in one selected
    # payroll month of the following commission cycle.
    release_mode: Optional[Literal["NEXT_QUARTER_LUMP"]] = None
    release_payout_period: Optional[str] = None


class CommissionJobManualPaymentIn(BaseModel):
    """Administrative correction of the receivable evidence for one JOB."""

    payment_received: Literal["YES", "NO"]
    payment_received_amount: Optional[float] = Field(default=None, ge=0)
    payment_month: Optional[str] = Field(default=None, pattern=r"^\d{4}-\d{2}$")
    payment_date: Optional[date] = None
    payout_months: Optional[list[str]] = None
    remark: Optional[str] = None


class CommissionJobHoldBonusIn(BaseModel):
    hold_bonus_percent: Optional[float] = None
    hold_bonus_amount: Optional[float] = None
    edited_field: Optional[Literal["percent", "amount"]] = None


class CommissionPaymentReportIn(BaseModel):
    note: Optional[str] = None


class CommissionPaymentVerificationIn(BaseModel):
    action: Literal["VERIFY", "REJECT"]
    note: Optional[str] = None


class CommissionPaymentCommandIn(BaseModel):
    release_mode: Literal["NEXT_QUARTER_LUMP"]
    release_payout_period: Optional[str] = None
    note: Optional[str] = None


class CommissionJobReleasePlanIn(BaseModel):
    """Preferred payout plan for the held amount of one JOB."""
    release_mode: Literal["NEXT_QUARTER_LUMP"]
    release_payout_period: Optional[str] = None


class CommissionBonusLockIn(BaseModel):
    period_id: int
    sales_rep: str
    reason: Optional[str] = None


class CommissionWalletAdjustmentIn(BaseModel):
    sales_rep: str
    action: Literal["DECREASE", "CREDIT"]
    amount: float
    period_id: Optional[int] = None
    job_id: Optional[int] = None
    target_payout_period: Optional[str] = None
    reason: str


class CommissionWalletTransferIn(BaseModel):
    sales_rep: str
    amount: float
    source_period_id: Optional[int] = None
    source_job_id: Optional[int] = None
    source_payout_period: Optional[str] = None
    target_payout_period: str
    reason: str


class CommissionJobHoldIn(BaseModel):
    """A manual hold is an operational lock; it never changes the commission formula."""
    sales_rep: str
    job_id: int
    action: Literal["HOLD", "RELEASE"]
    amount: Optional[float] = None
    reason: Optional[str] = None


class CommissionJobManualHoldTargetIn(BaseModel):
    sales_rep: str
    manual_held_amount: float
    remark: Optional[str] = None


class CommissionPayoutScheduleIn(BaseModel):
    sales_rep: str
    payout_period: str
    amount: Optional[float] = None
    note: Optional[str] = None
    source_period_id: Optional[int] = None


class CommissionWalletUndoIn(BaseModel):
    """Undo only the latest reversible wallet operation for one sales rep."""
    sales_rep: str
    source_period_id: Optional[int] = None


class CommissionScheduleActionIn(BaseModel):
    note: Optional[str] = None


class CommissionScheduleCancelIn(BaseModel):
    reason: str


class MonthlyCommissionPayoutOut(BaseModel):
    payout_period: str
    amount: float


class SalesRepSummaryOut(BaseModel):
    sales_rep: str
    job_count: int
    total_realized_revenue: float
    total_realized_cost: float
    total_profit_loss: float
    sales_bonus: float = 0.0
    target: float = 0.0
    bonus_rate: float = 0.0
    total_bonus_quarter: float = 0.0
    payment_received_total: float = 0.0
    hold_bonus_total: float = 0.0
    employee_salary: float = 0.0
    coefficient: float = 0.0
    is_pnl_overridden: bool = False
    is_target_overridden: bool = False
    is_rate_overridden: bool = False
    is_total_bonus_overridden: bool = False
    is_monthly_bonus_overridden: bool = False
    remark: Optional[str] = ""
    bonus_rules: list = []
    uses_progressive_bonus: bool = True
    monthly_payouts: List[MonthlyCommissionPayoutOut] = Field(default_factory=list)


class PeriodSummaryOut(BaseModel):
    id: int
    period_label: str
    from_date: Optional[str]
    till_date: Optional[str]
    source_filename: Optional[str]
    job_count: int
    total_profit_loss: float
    created_at: str
    created_by: Optional[str]
    payout_periods: List[str] = Field(default_factory=list)
    sales_rep_summary: List[SalesRepSummaryOut]


class PeriodListOut(BaseModel):
    id: int
    period_label: str
    from_date: Optional[str]
    till_date: Optional[str]
    source_filename: Optional[str]
    job_count: int
    total_profit_loss: float
    created_at: str
    payout_periods: List[str] = Field(default_factory=list)
    sales_rep_summary: List[SalesRepSummaryOut] = []


# ── Helper: parse date string (flexible) ──────────────
def _parse_date(s: Optional[str]) -> Optional[date]:
    if not s:
        return None
    
    s = s.strip()
    
    # Thay thế tháng tiếng Anh viết tắt sang số để tránh lỗi phụ thuộc locale
    months_map = {
        "jan": "01", "feb": "02", "mar": "03", "apr": "04",
        "may": "05", "jun": "06", "jul": "07", "aug": "08",
        "sep": "09", "oct": "10", "nov": "11", "dec": "12"
    }
    
    s_lower = s.lower()
    has_alpha_month = False
    for m_name, m_num in months_map.items():
        if m_name in s_lower:
            s_lower = s_lower.replace(m_name, m_num)
            has_alpha_month = True
            break
            
    formats = [
        "%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y",
        "%d-%m-%Y", "%m-%d-%Y",
        "%d-%m-%y", "%d/%m/%y",
        "%Y/%m/%d"
    ]
    
    target_str = s_lower if has_alpha_month else s
    
    for fmt in formats:
        try:
            from datetime import datetime as _dt
            return _dt.strptime(target_str, fmt).date()
        except ValueError:
            continue
            
    return None


# ══════════════════════════════════════════════════════
# POST /api/commission/import
# ══════════════════════════════════════════════════════
def _persist_commission_import(db: Session, payload: CommissionImportIn, current_user) -> CommissionPeriod:
    """Stage one validated Climax import without committing the transaction."""
    if not payload.jobs:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Danh sách jobs rỗng. Không có gì để lưu.",
        )

    # A commission period drives the wallet payout months.  Never accept an
    # import without a verified source range; otherwise older clients silently
    # fell back to the current month and created an incorrect wallet.
    source_from_date = _parse_date(payload.from_date)
    source_till_date = _parse_date(payload.till_date)
    if not source_from_date or not source_till_date:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Thiếu khoảng ngày nguồn commission. File phải có tiêu đề Job Date From … Till … hợp lệ.",
        )
    if source_from_date > source_till_date:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Khoảng ngày nguồn commission không hợp lệ: ngày bắt đầu lớn hơn ngày kết thúc.",
        )

    period = CommissionPeriod(
        period_label=payload.period_label,
        from_date=source_from_date,
        till_date=source_till_date,
        source_filename=payload.source_filename,
        note=payload.note,
        created_by=current_user.username if hasattr(current_user, "username") else str(current_user.id),
    )
    db.add(period)
    db.flush()  # lấy period.id

    jobs_to_insert = []
    for j in payload.jobs:
        jobs_to_insert.append(
            CommissionJob(
                period_id=period.id,
                job_no=j.job_no,
                job_date=_parse_date(j.job_date),
                hbl=j.hbl,
                mbl=j.mbl,
                customer=j.customer,
                vendor=j.vendor,
                sales_rep=j.sales_rep,
                shipper=j.shipper,
                consignee=j.consignee,
                sub_type=j.sub_type,
                container_string=j.container_string,
                wt=j.wt,
                vol=j.vol,
                carrier_booking_no=j.carrier_booking_no,
                por=j.por,
                final_destination=j.final_destination,
                realized_revenue=j.realized_revenue,
                unrealized_revenue=j.unrealized_revenue,
                realized_cost=j.realized_cost,
                unrealized_cost=j.unrealized_cost,
                profit_loss=j.profit_loss,
                container_picked=j.container_picked,
                payment_received=j.payment_received,
                hold_bonus_percent=FIXED_HOLD_BONUS_PERCENT,
                hold_bonus_amount=round(
                    max(0.0, float(j.profit_loss or 0.0)) * FIXED_HOLD_BONUS_PERCENT / 100,
                    2,
                ),
            )
        )

    db.add_all(jobs_to_insert)
    return period


_COMMISSION_IMPORT_JOB_FIELDS = (
    "job_no", "job_date", "hbl", "mbl", "customer", "vendor", "sales_rep",
    "shipper", "consignee", "sub_type", "container_string", "wt", "vol",
    "carrier_booking_no", "por", "final_destination", "realized_revenue",
    "unrealized_revenue", "realized_cost", "unrealized_cost", "profit_loss",
    "container_picked", "payment_received",
)


def _exact_import_period(db: Session, payload: CommissionImportIn) -> Optional[CommissionPeriod]:
    source_from_date = _parse_date(payload.from_date)
    source_till_date = _parse_date(payload.till_date)
    if not source_from_date or not source_till_date:
        return None
    return (
        db.query(CommissionPeriod)
        .filter(
            CommissionPeriod.is_voided.is_(False),
            CommissionPeriod.from_date == source_from_date,
            CommissionPeriod.till_date == source_till_date,
        )
        .order_by(CommissionPeriod.created_at.desc(), CommissionPeriod.id.desc())
        .first()
    )


def _manual_job_edit_reasons(db: Session, job: CommissionJob) -> list[str]:
    """Explain why an existing JOB must not be overwritten implicitly.

    Imported P&L columns have no updated-at flag, so protected state is derived
    from the accounting fields and immutable workflow/audit records that are
    only created after a user reviews or edits the JOB.
    """
    reasons: list[str] = []
    if job.bonus_remark:
        reasons.append("Đã có ghi chú thủ công")
    if any(value is not None for value in (
        job.receivable_amount,
        job.balance_amount,
        job.payment_received_amount,
    )) or job.receivable_attachments or job.receivable_links:
        reasons.append("Đã đối chiếu hoặc đính kèm công nợ")

    verification = db.query(CommissionPaymentVerification.id).filter(
        CommissionPaymentVerification.job_id == job.id,
    ).first()
    if verification:
        reasons.append("Đã có quy trình xác minh thanh toán")

    manual_entry_types = {
        "MANUAL_CREDIT", "MANUAL_DECREASE", "MANUAL_HOLD", "MANUAL_RELEASE",
        "MANUAL_CREDIT_REVERSAL", "MANUAL_DECREASE_REVERSAL",
        "MANUAL_HOLD_REVERSAL", "MANUAL_RELEASE_REVERSAL",
        "PAYMENT_REPORTED", "PAYMENT_VERIFIED", "PAYMENT_RELEASE_ALLOCATION",
        "SCHEDULED", "SCHEDULE_RELEASE", "PAID", "TRANSFER_OUT", "TRANSFER_IN",
    }
    manual_ledger = db.query(CommissionWalletLedger.entry_type).filter(
        CommissionWalletLedger.period_id == job.period_id,
        CommissionWalletLedger.job_id == job.id,
        CommissionWalletLedger.entry_type.in_(manual_entry_types),
    ).first()
    if manual_ledger:
        reasons.append("Đã phát sinh điều chỉnh hoặc lịch sử ví thưởng")

    return reasons


def _apply_imported_job_fields(target: CommissionJob, source: JobRowIn) -> None:
    from app.services.commission_wallet_rules import calculate_job_hold

    values = source.model_dump()
    values["job_date"] = _parse_date(source.job_date)
    for field in _COMMISSION_IMPORT_JOB_FIELDS:
        setattr(target, field, values[field])
    hold_percent, hold_amount = calculate_job_hold(
        profit_loss=source.profit_loss,
        balance_amount=target.balance_amount,
        payment_received_amount=target.payment_received_amount,
    )
    target.hold_bonus_percent = hold_percent
    target.hold_bonus_amount = hold_amount


def _append_source_filename(period: CommissionPeriod, source_filename: Optional[str]) -> None:
    name = str(source_filename or "").strip()
    if not name:
        return
    existing = [part.strip() for part in str(period.source_filename or "").split(";") if part.strip()]
    if name not in existing:
        period.source_filename = "; ".join([*existing, name])


@router.post("/import/merge-preview")
def preview_commission_import_merge(
    payload: CommissionImportBatchIn,
    db: Session = Depends(get_db),
    current_user=Depends(get_admin_user),
):
    """Preview exact-period merges without changing database state."""
    del current_user
    previews = []
    for item in payload.imports:
        period = _exact_import_period(db, item)
        if not period:
            previews.append({
                "source_filename": item.source_filename,
                "period_id": None,
                "period_label": item.period_label,
                "new_jobs": len(item.jobs),
                "automatic_updates": 0,
                "manual_jobs": [],
            })
            continue

        existing_by_job_no = {
            normalize_receivable_job_no(job.job_no): job
            for job in period.jobs
            if normalize_receivable_job_no(job.job_no)
        }
        manual_jobs = []
        new_jobs = 0
        automatic_updates = 0
        seen_ids: set[int] = set()
        for incoming in item.jobs:
            existing = existing_by_job_no.get(normalize_receivable_job_no(incoming.job_no))
            if not existing:
                new_jobs += 1
                continue
            reasons = _manual_job_edit_reasons(db, existing)
            if reasons:
                if existing.id not in seen_ids:
                    manual_jobs.append({
                        "job_id": existing.id,
                        "job_no": existing.job_no,
                        "sales_rep": existing.sales_rep,
                        "reasons": reasons,
                    })
                    seen_ids.add(existing.id)
            else:
                automatic_updates += 1

        previews.append({
            "source_filename": item.source_filename,
            "period_id": period.id,
            "period_label": period.period_label,
            "from_date": period.from_date.isoformat() if period.from_date else None,
            "till_date": period.till_date.isoformat() if period.till_date else None,
            "new_jobs": new_jobs,
            "automatic_updates": automatic_updates,
            "manual_jobs": manual_jobs,
        })
    return {"imports": previews}


@router.post("/import/merge", status_code=status.HTTP_200_OK)
def merge_commission_imports(
    payload: CommissionImportMergeIn,
    db: Session = Depends(get_db),
    current_user=Depends(get_admin_user),
):
    """Merge multiple files into their exact existing periods by JOB NO.

    New JOBs are inserted. Existing unmodified JOBs are refreshed from the
    incoming file. Existing manually-reviewed JOBs are refreshed only when the
    caller explicitly selects their immutable database IDs. Accounting fields,
    attachments and wallet history are never deleted by this operation.
    """
    if not payload.imports:
        raise HTTPException(status_code=400, detail="Danh sách file import đang trống.")
    if len(payload.imports) > 50:
        raise HTTPException(status_code=400, detail="Mỗi lần chỉ được import tối đa 50 file.")

    selected_manual_ids = set(payload.overwrite_manual_job_ids)
    period_ids: set[int] = set()
    jobs_added = 0
    jobs_updated = 0
    manual_jobs_skipped = 0
    files_merged = 0
    files_created = 0

    try:
        for item in payload.imports:
            period = _exact_import_period(db, item)
            if not period:
                period = _persist_commission_import(db, item, current_user)
                db.flush()
                period_ids.add(period.id)
                jobs_added += len(item.jobs)
                files_created += 1
                continue

            files_merged += 1
            period_ids.add(period.id)
            existing_by_job_no = {
                normalize_receivable_job_no(job.job_no): job
                for job in period.jobs
                if normalize_receivable_job_no(job.job_no)
            }
            for incoming in item.jobs:
                normalized_job_no = normalize_receivable_job_no(incoming.job_no)
                existing = existing_by_job_no.get(normalized_job_no)
                if not existing:
                    new_job = CommissionJob(period_id=period.id, job_no=incoming.job_no)
                    _apply_imported_job_fields(new_job, incoming)
                    db.add(new_job)
                    db.flush()
                    existing_by_job_no[normalized_job_no] = new_job
                    jobs_added += 1
                    continue

                reasons = _manual_job_edit_reasons(db, existing)
                if reasons and existing.id not in selected_manual_ids:
                    manual_jobs_skipped += 1
                    continue
                _apply_imported_job_fields(existing, incoming)
                jobs_updated += 1

            _append_source_filename(period, item.source_filename)

        db.commit()
    except Exception:
        db.rollback()
        raise

    return {
        "period_ids": sorted(period_ids),
        "files_merged": files_merged,
        "files_created": files_created,
        "jobs_added": jobs_added,
        "jobs_updated": jobs_updated,
        "manual_jobs_skipped": manual_jobs_skipped,
        "message": (
            f"Đã cập nhật {jobs_updated} JOB, thêm mới {jobs_added} JOB; "
            f"giữ nguyên {manual_jobs_skipped} JOB đã sửa thủ công không được chọn."
        ),
    }


@router.post("/import", status_code=status.HTTP_201_CREATED)
def import_commission(
    payload: CommissionImportIn,
    db: Session = Depends(get_db),
    current_user=Depends(get_admin_user),
):
    """Persist one user-confirmed Climax file."""
    period = _persist_commission_import(db, payload, current_user)
    db.commit()

    return {
        "period_id": period.id,
        "period_label": period.period_label,
        "jobs_saved": len(payload.jobs),
        "message": f"✅ Đã lưu {len(payload.jobs)} jobs cho kỳ '{period.period_label}' vào cơ sở dữ liệu.",
    }


@router.post("/import/batch", status_code=status.HTTP_201_CREATED)
def import_commission_batch(
    payload: CommissionImportBatchIn,
    db: Session = Depends(get_db),
    current_user=Depends(get_admin_user),
):
    """Persist several Climax files atomically.

    Every file is validated and staged before the single commit.  A malformed
    file therefore cannot leave a half-imported batch in the database.
    """
    if not payload.imports:
        raise HTTPException(status_code=400, detail="Danh sách file import đang trống.")
    if len(payload.imports) > 50:
        raise HTTPException(status_code=400, detail="Mỗi lần chỉ được import tối đa 50 file.")

    try:
        periods = [
            _persist_commission_import(db, item, current_user)
            for item in payload.imports
        ]
        db.commit()
    except Exception:
        db.rollback()
        raise

    jobs_saved = sum(len(item.jobs) for item in payload.imports)
    return {
        "period_ids": [period.id for period in periods],
        "files_saved": len(periods),
        "jobs_saved": jobs_saved,
        "message": f"✅ Đã lưu {len(periods)} file với tổng {jobs_saved} jobs vào cơ sở dữ liệu.",
    }


# ══════════════════════════════════════════════════════
# GET /api/commission/periods  (danh sách tất cả kỳ)
# ══════════════════════════════════════════════════════
@router.get("/periods", response_model=List[PeriodListOut])
def list_periods(db: Session = Depends(get_db)):
    from collections import defaultdict
    from app.services.salary import calculate_employee_bonus, clean_name_for_match, get_active_department_rules, is_sales_bonus_employee
    from app.models.employee import Employee
    
    employees = db.query(Employee).all()
    emp_map = {}
    for emp in employees:
        clean_name = clean_name_for_match(emp.full_name)
        if clean_name:
            emp_map[clean_name] = {
                "salary": emp.contract_salary,
                "department_id": emp.department_id,
                "uses_progressive_bonus": is_sales_bonus_employee(emp),
            }

    periods = db.query(CommissionPeriod).filter(CommissionPeriod.is_voided.is_(False)).order_by(CommissionPeriod.created_at.desc()).all()
    result = []
    for p in periods:
        period_str = p.from_date.strftime("%Y-%m") if p.from_date else "0000-00"
        payout_periods = _source_payout_periods(p)
        rep_map = defaultdict(lambda: {"job_count": 0, "total_realized_revenue": 0.0, "total_realized_cost": 0.0, "total_profit_loss": 0.0, "payment_received_total": 0.0, "hold_bonus_total": 0.0})
        for j in p.jobs:
            rep = j.sales_rep or "(Unknown)"
            rep_map[rep]["job_count"] += 1
            rep_map[rep]["total_realized_revenue"] += j.realized_revenue
            rep_map[rep]["total_realized_cost"] += j.realized_cost
            rep_map[rep]["total_profit_loss"] += j.profit_loss
            if str(j.payment_received or "NO").strip().upper() == "YES":
                rep_map[rep]["payment_received_total"] += max(0.0, float(j.payment_received_amount or 0.0))
            rep_map[rep]["hold_bonus_total"] += max(0.0, float(j.hold_bonus_amount or 0.0))

        from app.models.commission import CommissionRepOverride
        overrides = db.query(CommissionRepOverride).filter(CommissionRepOverride.period_id == p.id).all()
        override_map = {ov.sales_rep: ov for ov in overrides}

        rep_summary = []
        for rep, data in sorted(rep_map.items(), key=lambda x: -x[1]["total_profit_loss"]):
            clean_rep = clean_name_for_match(rep)
            emp_info = emp_map.get(clean_rep, {
                "salary": 0.0,
                "department_id": None,
                "uses_progressive_bonus": True,
            })
            emp_salary = emp_info["salary"]
            uses_progressive_bonus = emp_info["uses_progressive_bonus"]
            active_rules = get_active_department_rules(db, emp_info["department_id"], period_str)

            ov = override_map.get(rep)
            total_profit_loss = data["total_profit_loss"]
            is_pnl_overridden = False
            if ov and ov.override_profit_loss is not None:
                total_profit_loss = ov.override_profit_loss
                is_pnl_overridden = True
                
            job_count = data["job_count"]
            if ov and ov.override_job_count is not None:
                job_count = ov.override_job_count

            salary = float(emp_salary)
            target_override = ov.override_target if ov and ov.override_target is not None else None
            is_target_overridden = target_override is not None
            bonus_calc = calculate_employee_bonus(
                total_profit_loss,
                salary,
                active_rules,
                uses_progressive_bonus=uses_progressive_bonus,
                target_override=target_override,
            )

            target = bonus_calc["target"]

            is_rate_overridden = False
            if ov and ov.override_bonus_rate is not None:
                bonus_rate = ov.override_bonus_rate
                is_rate_overridden = True
                total_bonus_quarter = bonus_calc["pf_count_bn"] * bonus_rate if bonus_calc["pf_count_bn"] > 0 else 0.0
            else:
                bonus_rate = bonus_calc["bonus_rate"]
                total_bonus_quarter = bonus_calc["total_bonus_quarter"]

            is_total_bonus_overridden = False
            if ov and ov.override_total_bonus is not None:
                total_bonus_quarter = ov.override_total_bonus
                is_total_bonus_overridden = True

            is_monthly_bonus_overridden = False
            if ov and ov.override_monthly_bonus is not None:
                sales_bonus = ov.override_monthly_bonus
                is_monthly_bonus_overridden = True
            else:
                sales_bonus = total_bonus_quarter / 3.0

            # The target gate is absolute: stale/manual override values must
            # never produce commission when Profit/Loss does not exceed Target.
            if bonus_calc["pf_count_bn"] <= 0:
                bonus_rate = 0.0
                total_bonus_quarter = 0.0
                sales_bonus = 0.0

            from app.services.commission_wallet_rules import calculate_company_bonus_wallet
            wallet_rule = calculate_company_bonus_wallet(
                total_profit_loss=total_profit_loss,
                total_bonus_quarter=total_bonus_quarter,
                monthly_bonus=sales_bonus,
                policy_hold_amount=data["hold_bonus_total"],
            )

            rep_summary.append(
                SalesRepSummaryOut(
                    sales_rep=rep,
                    job_count=job_count,
                    total_realized_revenue=data["total_realized_revenue"],
                    total_realized_cost=data["total_realized_cost"],
                    total_profit_loss=total_profit_loss,
                    sales_bonus=sales_bonus,
                    target=target,
                    bonus_rate=bonus_rate,
                    total_bonus_quarter=total_bonus_quarter,
                    payment_received_total=round(data["payment_received_total"], 2),
                    hold_bonus_total=float(wallet_rule["company_held_profit"]),
                    employee_salary=float(emp_salary),
                    coefficient=float(bonus_calc["coefficient"] or 0.0),
                    is_pnl_overridden=is_pnl_overridden,
                    is_target_overridden=is_target_overridden,
                    is_rate_overridden=is_rate_overridden,
                    is_total_bonus_overridden=is_total_bonus_overridden,
                    is_monthly_bonus_overridden=is_monthly_bonus_overridden,
                    remark=ov.remark if ov else "",
                    bonus_rules=active_rules,
                    uses_progressive_bonus=uses_progressive_bonus,
                    monthly_payouts=[
                        MonthlyCommissionPayoutOut(
                            payout_period=payout_period,
                            amount=round(float(wallet_rule["monthly_payout"]), 2),
                        )
                        for payout_period in payout_periods
                    ],
                )
            )

        result.append(
            PeriodListOut(
                id=p.id,
                period_label=p.period_label,
                from_date=str(p.from_date) if p.from_date else None,
                till_date=str(p.till_date) if p.till_date else None,
                source_filename=p.source_filename,
                job_count=len(p.jobs),
                total_profit_loss=sum(j.profit_loss for j in p.jobs),
                created_at=p.created_at.isoformat(),
                payout_periods=payout_periods,
                sales_rep_summary=rep_summary,
            )
        )
    return result


# ══════════════════════════════════════════════════════
# GET /api/commission/periods/{id}  (chi tiết 1 kỳ)
# ══════════════════════════════════════════════════════
@router.get("/periods/{period_id}", response_model=PeriodSummaryOut)
def get_period_detail(period_id: int, db: Session = Depends(get_db)):
    period = db.query(CommissionPeriod).filter(CommissionPeriod.id == period_id, CommissionPeriod.is_voided.is_(False)).first()
    if not period:
        raise HTTPException(status_code=404, detail="Kỳ commission không tồn tại.")
    payout_periods = _source_payout_periods(period)

    # Tổng hợp theo sales_rep
    from collections import defaultdict
    from app.services.salary import calculate_employee_bonus, clean_name_for_match, get_active_department_rules, is_sales_bonus_employee
    from app.models.employee import Employee
    
    employees = db.query(Employee).all()
    emp_map = {}
    for emp in employees:
        clean_name = clean_name_for_match(emp.full_name)
        if clean_name:
            emp_map[clean_name] = {
                "salary": emp.contract_salary,
                "department_id": emp.department_id,
                "uses_progressive_bonus": is_sales_bonus_employee(emp),
            }

    rep_map: dict = defaultdict(lambda: {"job_count": 0, "total_realized_revenue": 0.0, "total_realized_cost": 0.0, "total_profit_loss": 0.0, "payment_received_total": 0.0, "hold_bonus_total": 0.0})
    for j in period.jobs:
        rep = j.sales_rep or "(Unknown)"
        rep_map[rep]["job_count"] += 1
        rep_map[rep]["total_realized_revenue"] += j.realized_revenue
        rep_map[rep]["total_realized_cost"] += j.realized_cost
        rep_map[rep]["total_profit_loss"] += j.profit_loss
        if str(j.payment_received or "NO").strip().upper() == "YES":
            rep_map[rep]["payment_received_total"] += max(0.0, float(j.payment_received_amount or 0.0))
        rep_map[rep]["hold_bonus_total"] += max(0.0, float(j.hold_bonus_amount or 0.0))

    # Load overrides for this period
    from app.models.commission import CommissionRepOverride
    overrides = db.query(CommissionRepOverride).filter(CommissionRepOverride.period_id == period_id).all()
    override_map = {ov.sales_rep: ov for ov in overrides}

    summary = []
    
    # Determine the period string (YYYY-MM) from from_date or default to current month
    period_str = ""
    if period.from_date:
        period_str = period.from_date.strftime("%Y-%m")
    else:
        # Fallback to current month if from_date is not available
        from datetime import datetime
        period_str = datetime.now().strftime("%Y-%m")
        
    for rep, data in sorted(rep_map.items(), key=lambda x: -x[1]["total_profit_loss"]):
        clean_rep = clean_name_for_match(rep)
        emp_info = emp_map.get(clean_rep, {
            "salary": 0.0,
            "department_id": None,
            "uses_progressive_bonus": True,
        })
        emp_salary = emp_info["salary"]
        department_id = emp_info["department_id"]
        uses_progressive_bonus = emp_info["uses_progressive_bonus"]
        
        # Get active rules for this employee's department
        active_rules = get_active_department_rules(db, department_id, period_str)
        
        ov = override_map.get(rep)
        total_profit_loss = data["total_profit_loss"]
        is_pnl_overridden = False
        if ov and ov.override_profit_loss is not None:
            total_profit_loss = ov.override_profit_loss
            is_pnl_overridden = True
            
        job_count = data["job_count"]
        if ov and ov.override_job_count is not None:
            job_count = ov.override_job_count

        # SALE uses progressive tiers; all other employees use the fixed 20%
        # rate. Both branches only reward Profit/Loss above Target.
        salary = float(emp_salary)
        target_override = ov.override_target if ov and ov.override_target is not None else None
        is_target_overridden = target_override is not None
        bonus_calc = calculate_employee_bonus(
            total_profit_loss,
            salary,
            active_rules,
            uses_progressive_bonus=uses_progressive_bonus,
            target_override=target_override,
        )
        
        target = bonus_calc["target"]

        is_rate_overridden = False
        if ov and ov.override_bonus_rate is not None:
            bonus_rate = ov.override_bonus_rate
            is_rate_overridden = True
            total_bonus_quarter = bonus_calc["pf_count_bn"] * bonus_rate if bonus_calc["pf_count_bn"] > 0 else 0.0
        else:
            bonus_rate = bonus_calc["bonus_rate"]
            total_bonus_quarter = bonus_calc["total_bonus_quarter"]

        is_total_bonus_overridden = False
        if ov and ov.override_total_bonus is not None:
            total_bonus_quarter = ov.override_total_bonus
            is_total_bonus_overridden = True

        is_monthly_bonus_overridden = False
        if ov and ov.override_monthly_bonus is not None:
            sales_bonus = ov.override_monthly_bonus
            is_monthly_bonus_overridden = True
        else:
            sales_bonus = total_bonus_quarter / 3.0

        # The target gate is absolute: stale/manual override values must never
        # produce commission when Profit/Loss does not exceed Target.
        if bonus_calc["pf_count_bn"] <= 0:
            bonus_rate = 0.0
            total_bonus_quarter = 0.0
            sales_bonus = 0.0

        from app.services.commission_wallet_rules import calculate_company_bonus_wallet
        wallet_rule = calculate_company_bonus_wallet(
            total_profit_loss=total_profit_loss,
            total_bonus_quarter=total_bonus_quarter,
            monthly_bonus=sales_bonus,
            policy_hold_amount=data["hold_bonus_total"],
        )

        summary.append(
            SalesRepSummaryOut(
                sales_rep=rep,
                job_count=job_count,
                total_realized_revenue=data["total_realized_revenue"],
                total_realized_cost=data["total_realized_cost"],
                total_profit_loss=total_profit_loss,
                sales_bonus=sales_bonus,
                target=target,
                bonus_rate=bonus_rate,
                total_bonus_quarter=total_bonus_quarter,
                payment_received_total=round(data["payment_received_total"], 2),
                hold_bonus_total=float(wallet_rule["company_held_profit"]),
                employee_salary=float(emp_salary),
                coefficient=float(bonus_calc["coefficient"] or 0.0),
                is_pnl_overridden=is_pnl_overridden,
                is_target_overridden=is_target_overridden,
                is_rate_overridden=is_rate_overridden,
                is_total_bonus_overridden=is_total_bonus_overridden,
                is_monthly_bonus_overridden=is_monthly_bonus_overridden,
                remark=ov.remark if ov else "",
                bonus_rules=active_rules,
                uses_progressive_bonus=uses_progressive_bonus,
                monthly_payouts=[
                    MonthlyCommissionPayoutOut(
                        payout_period=payout_period,
                        amount=round(float(wallet_rule["monthly_payout"]), 2),
                    )
                    for payout_period in payout_periods
                ],
            )
        )

    return PeriodSummaryOut(
        id=period.id,
        period_label=period.period_label,
        from_date=str(period.from_date) if period.from_date else None,
        till_date=str(period.till_date) if period.till_date else None,
        source_filename=period.source_filename,
        job_count=len(period.jobs),
        total_profit_loss=sum(j.profit_loss for j in period.jobs),
        created_at=period.created_at.isoformat(),
        created_by=period.created_by,
        payout_periods=payout_periods,
        sales_rep_summary=summary,
    )


class JobRowOut(BaseModel):
    id: int
    jobNo: str
    jobDate: Optional[str] = None
    hbl: Optional[str] = None
    mbl: Optional[str] = None
    customer: Optional[str] = None
    vendor: Optional[str] = None
    salesRep: Optional[str] = None
    shipper: Optional[str] = None
    consignee: Optional[str] = None
    subType: Optional[str] = None
    containerString: Optional[str] = None
    wt: Optional[float] = None
    vol: Optional[float] = None
    carrierBookingNo: Optional[str] = None
    por: Optional[str] = None
    finalDestination: Optional[str] = None
    realizedRevenue: float = 0.0
    unrealizedRevenue: float = 0.0
    realizedCost: float = 0.0
    unrealizedCost: float = 0.0
    profitLoss: float = 0.0
    containerPicked: Optional[str] = None
    paymentReceived: Optional[str] = None
    receivableAmount: Optional[float] = None
    balanceAmount: Optional[float] = None
    paymentReceivedAmount: Optional[float] = None
    bonusRemark: Optional[str] = None
    holdBonusPercent: Optional[float] = None
    holdBonusAmount: Optional[float] = None
    netBonus: float = 0.0
    receivableCount: int = 0


class CommissionReceivableAttachmentOut(BaseModel):
    id: int
    period_id: int
    job_id: int
    job_no: str
    sales_rep: Optional[str] = None
    original_filename: str
    content_type: Optional[str] = None
    size_bytes: int
    note: Optional[str] = None
    uploaded_by: Optional[str] = None
    created_at: str


class CommissionReceivableReconciliationJobOut(BaseModel):
    job_id: int
    job_no: str
    source_rows: int
    receivable_amount: float
    payment_received_amount: float
    balance_amount: float
    paid_percent: float
    hold_bonus_percent: float
    hold_bonus_amount: float
    net_bonus: float


class CommissionReceivableReconciliationOut(BaseModel):
    original_filename: str
    sheet_name: str
    positive_rows: int
    ignored_non_positive_rows: int
    invalid_positive_rows: int
    matched_jobs: int
    unmatched_positive_jobs: int
    unmatched_job_nos: List[str]
    attachment: CommissionReceivableAttachmentOut
    updates: List[CommissionReceivableReconciliationJobOut]


def _reconcile_job_hold_ledger(
    db: Session,
    job: CommissionJob,
    target_hold_amount: float,
    *,
    reason_code: str,
    note: str,
    created_by: Optional[str] = None,
) -> float:
    """Move one JOB's automatic wallet hold to the reviewed Hold Bonus value."""
    entries = db.query(CommissionWalletLedger).filter(
        CommissionWalletLedger.period_id == job.period_id,
        CommissionWalletLedger.job_id == job.id,
    ).order_by(CommissionWalletLedger.id).all()
    position = _wallet_positions(entries).get((job.sales_rep or "(Unknown)", job.id), {})
    current_hold = round(float(position.get("payment_held", 0.0)), 2)
    hold_delta = round(max(0.0, float(target_hold_amount or 0.0)) - current_hold, 2)
    if abs(hold_delta) < 0.01:
        return 0.0

    source = entries[0] if entries else None
    db.add(CommissionWalletLedger(
        period_id=job.period_id,
        job_id=job.id,
        entitlement_id=source.entitlement_id if source else None,
        sales_rep=job.sales_rep or "(Unknown)",
        employee_id=(source.employee_id if source else _employee_id_for_sales_rep(job.sales_rep or "(Unknown)", db)),
        entry_type="PAYMENT_STATUS_HOLD" if hold_delta > 0 else "RELEASED",
        amount=abs(hold_delta),
        reason_code=reason_code,
        note=note,
        created_by=created_by,
    ))
    return hold_delta


def _apply_fixed_job_hold(
    db: Session,
    job: CommissionJob,
    *,
    reason_code: str,
    note: str,
    created_by: Optional[str] = None,
    wallet_hold_amount: Optional[float] = None,
) -> float:
    """Persist the JOB policy hold and align the bonus-wallet hold separately."""
    from app.services.commission_wallet_rules import calculate_job_hold

    hold_percent, fixed_amount = calculate_job_hold(
        profit_loss=job.profit_loss,
        balance_amount=job.balance_amount,
        payment_received_amount=job.payment_received_amount,
    )
    job.hold_bonus_percent = hold_percent
    job.hold_bonus_amount = fixed_amount

    # Once accounting has released a hold into a payment workflow, a later
    # formula sync must not recreate it. The saved JOB fields still retain the
    # original fixed hold for audit and summary display.
    entries = db.query(CommissionWalletLedger).filter(
        CommissionWalletLedger.period_id == job.period_id,
        CommissionWalletLedger.job_id == job.id,
    ).order_by(CommissionWalletLedger.id).all()
    explicit_release_exists = any(
        entry.entry_type == "RELEASED" and entry.reason_code in {
            "PAYMENT_RECEIVED",
            "ACCOUNTING_PAYMENT_COMMAND",
            "PAYMENT_RECEIVED_RECONCILE",
        }
        for entry in entries
    )
    if explicit_release_exists:
        return 0.0
    return _reconcile_job_hold_ledger(
        db,
        job,
        fixed_amount if wallet_hold_amount is None else max(0.0, float(wallet_hold_amount)),
        reason_code=reason_code,
        note=note,
        created_by=created_by,
    )


def _receivable_attachment_out(
    attachment: CommissionJobReceivableAttachment,
    job: CommissionJob,
) -> CommissionReceivableAttachmentOut:
    return CommissionReceivableAttachmentOut(
        id=attachment.id,
        period_id=attachment.period_id,
        job_id=job.id,
        job_no=job.job_no,
        sales_rep=job.sales_rep,
        original_filename=attachment.original_filename,
        content_type=attachment.content_type,
        size_bytes=attachment.size_bytes,
        note=attachment.note,
        uploaded_by=attachment.uploaded_by,
        created_at=attachment.created_at.isoformat(),
    )


def _commission_job_or_404(db: Session, period_id: int, job_id: int) -> CommissionJob:
    job = db.query(CommissionJob).filter(
        CommissionJob.id == job_id,
        CommissionJob.period_id == period_id,
    ).first()
    if not job:
        raise HTTPException(status_code=404, detail="Không tìm thấy JOB trong kỳ commission.")
    return job


def _receivable_file_path(stored_filename: str) -> Path:
    if Path(stored_filename).name != stored_filename:
        raise HTTPException(status_code=404, detail="Tệp công nợ không hợp lệ.")
    candidate = (COMMISSION_RECEIVABLE_UPLOAD_DIR / stored_filename).resolve()
    try:
        if not candidate.is_relative_to(COMMISSION_RECEIVABLE_UPLOAD_DIR.resolve()):
            raise HTTPException(status_code=404, detail="Tệp công nợ không hợp lệ.")
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Tệp công nợ không hợp lệ.") from exc
    if not candidate.is_file():
        raise HTTPException(status_code=404, detail="Không tìm thấy tệp công nợ trên máy chủ.")
    return candidate


@router.get("/periods/{period_id}/jobs", response_model=List[JobRowOut])
def get_period_jobs(
    period_id: int,
    sales_rep: Optional[str] = None,
    db: Session = Depends(get_db),
):
    query = db.query(CommissionJob).filter(CommissionJob.period_id == period_id)
    if sales_rep and sales_rep != "—":
        query = query.filter(CommissionJob.sales_rep == sales_rep)
    
    jobs = query.order_by(CommissionJob.id.asc()).all()
    ledger_entries = db.query(CommissionWalletLedger).filter(
        CommissionWalletLedger.period_id == period_id,
        CommissionWalletLedger.job_id.in_([job.id for job in jobs]),
    ).all() if jobs else []
    positions = _wallet_positions(ledger_entries)
    period = db.query(CommissionPeriod).filter(CommissionPeriod.id == period_id).first()
    fallback_earned_by_job = {
        allocated_job.id: float(amount)
        for allocated_job, _allocation_rep, amount, _is_paid in _period_wallet_allocations(period, db)
        if allocated_job is not None
    } if period else {}
    receivable_counts = {
        int(job_id): int(count)
        for job_id, count in db.query(
            CommissionJobReceivableLink.job_id,
            func.count(CommissionJobReceivableLink.id),
        ).filter(
            CommissionJobReceivableLink.period_id == period_id,
            CommissionJobReceivableLink.job_id.in_([job.id for job in jobs]),
        ).group_by(CommissionJobReceivableLink.job_id).all()
    } if jobs else {}
    result = []
    for j in jobs:
        result.append(
            JobRowOut(
                id=j.id,
                jobNo=j.job_no,
                jobDate=j.job_date.strftime("%d/%m/%Y") if j.job_date else None,
                hbl=j.hbl,
                mbl=j.mbl,
                customer=j.customer,
                vendor=j.vendor,
                salesRep=j.sales_rep,
                shipper=j.shipper,
                consignee=j.consignee,
                subType=j.sub_type,
                containerString=j.container_string,
                wt=j.wt,
                vol=j.vol,
                carrierBookingNo=j.carrier_booking_no,
                por=j.por,
                finalDestination=j.final_destination,
                realizedRevenue=j.realized_revenue,
                unrealizedRevenue=j.unrealized_revenue,
                realizedCost=j.realized_cost,
                unrealizedCost=j.unrealized_cost,
                profitLoss=j.profit_loss,
                containerPicked=j.container_picked,
                paymentReceived=j.payment_received,
                receivableAmount=j.receivable_amount,
                balanceAmount=j.balance_amount,
                paymentReceivedAmount=j.payment_received_amount,
                bonusRemark=j.bonus_remark,
                holdBonusPercent=j.hold_bonus_percent,
                holdBonusAmount=j.hold_bonus_amount,
                netBonus=max(0.0, float(
                    positions.get((j.sales_rep or "(Unknown)", j.id), {}).get(
                        "earned",
                        fallback_earned_by_job.get(j.id, 0.0),
                    )
                )),
                receivableCount=receivable_counts.get(j.id, 0),
            )
        )
    return result


@router.get(
    "/periods/{period_id}/jobs/{job_id}/receivables",
    response_model=List[CommissionReceivableAttachmentOut],
)
def list_job_receivables(
    period_id: int,
    job_id: int,
    db: Session = Depends(get_db),
):
    job = _commission_job_or_404(db, period_id, job_id)
    attachments = db.query(CommissionJobReceivableAttachment).join(
        CommissionJobReceivableLink,
        CommissionJobReceivableLink.attachment_id == CommissionJobReceivableAttachment.id,
    ).filter(
        CommissionJobReceivableLink.period_id == period_id,
        CommissionJobReceivableLink.job_id == job_id,
    ).order_by(CommissionJobReceivableAttachment.created_at.desc(), CommissionJobReceivableAttachment.id.desc()).all()
    return [_receivable_attachment_out(item, job) for item in attachments]


@router.post(
    "/periods/{period_id}/jobs/{job_id}/receivables",
    response_model=List[CommissionReceivableAttachmentOut],
    status_code=status.HTTP_201_CREATED,
)
async def upload_job_receivables(
    period_id: int,
    job_id: int,
    files: List[UploadFile] = File(...),
    note: str = Form(default=""),
    db: Session = Depends(get_db),
    current_user=Depends(get_admin_user),
):
    job = _commission_job_or_404(db, period_id, job_id)
    return await _upload_receivables_for_jobs(files, note, period_id, [job], db, current_user)


@router.post(
    "/periods/{period_id}/receivables/bulk",
    response_model=List[CommissionReceivableAttachmentOut],
    status_code=status.HTTP_201_CREATED,
)
async def upload_bulk_job_receivables(
    period_id: int,
    job_ids: str = Form(...),
    files: List[UploadFile] = File(...),
    note: str = Form(default=""),
    db: Session = Depends(get_db),
    current_user=Depends(get_admin_user),
):
    try:
        parsed_job_ids = json.loads(job_ids)
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=422, detail="Danh sách JOB được chọn không hợp lệ.") from exc
    if not isinstance(parsed_job_ids, list):
        raise HTTPException(status_code=422, detail="Danh sách JOB được chọn không hợp lệ.")
    try:
        unique_job_ids = list(dict.fromkeys(int(value) for value in parsed_job_ids))
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail="Danh sách JOB được chọn không hợp lệ.") from exc
    if not unique_job_ids or len(unique_job_ids) > 500:
        raise HTTPException(status_code=422, detail="Hãy chọn từ 1 đến 500 JOB cho mỗi lần upload.")
    jobs = db.query(CommissionJob).filter(
        CommissionJob.period_id == period_id,
        CommissionJob.id.in_(unique_job_ids),
    ).all()
    jobs_by_id = {job.id: job for job in jobs}
    if len(jobs_by_id) != len(unique_job_ids):
        raise HTTPException(status_code=404, detail="Có JOB được chọn không tồn tại trong kỳ commission.")
    ordered_jobs = [jobs_by_id[job_id] for job_id in unique_job_ids]
    sales_reps = {str(job.sales_rep or "").strip() for job in ordered_jobs}
    if len(sales_reps) > 1:
        raise HTTPException(status_code=422, detail="Các JOB trong một lần upload phải thuộc cùng một SALE.")
    return await _upload_receivables_for_jobs(files, note, period_id, ordered_jobs, db, current_user)


@router.post(
    "/periods/{period_id}/receivables/reconcile",
    response_model=CommissionReceivableReconciliationOut,
    status_code=status.HTTP_201_CREATED,
)
async def reconcile_job_receivables(
    period_id: int,
    job_ids: str = Form(...),
    file: UploadFile = File(...),
    note: str = Form(default=""),
    db: Session = Depends(get_db),
    current_user=Depends(get_admin_user),
):
    """Match an AGEING workbook to one SALE's JOBs and calculate Hold Bonus."""
    try:
        parsed_job_ids = json.loads(job_ids)
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=422, detail="Danh sách JOB dùng để đối chiếu không hợp lệ.") from exc
    if not isinstance(parsed_job_ids, list):
        raise HTTPException(status_code=422, detail="Danh sách JOB dùng để đối chiếu không hợp lệ.")
    try:
        unique_job_ids = list(dict.fromkeys(int(value) for value in parsed_job_ids))
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail="Danh sách JOB dùng để đối chiếu không hợp lệ.") from exc
    if not unique_job_ids or len(unique_job_ids) > 500:
        raise HTTPException(status_code=422, detail="Hãy đối chiếu từ 1 đến 500 JOB trong cùng một lần.")

    jobs = db.query(CommissionJob).filter(
        CommissionJob.period_id == period_id,
        CommissionJob.id.in_(unique_job_ids),
    ).all()
    jobs_by_id = {job.id: job for job in jobs}
    if len(jobs_by_id) != len(unique_job_ids):
        raise HTTPException(status_code=404, detail="Có JOB dùng để đối chiếu không tồn tại trong kỳ commission.")
    ordered_jobs = [jobs_by_id[job_id] for job_id in unique_job_ids]
    sales_reps = {str(job.sales_rep or "").strip() for job in ordered_jobs}
    if len(sales_reps) != 1:
        raise HTTPException(status_code=422, detail="Mỗi file công nợ chỉ được đối chiếu với JOB của cùng một SALE.")
    sales_rep = next(iter(sales_reps))
    _ensure_bonus_editable(db, period_id, sales_rep or "(Unknown)")

    original_name = Path(file.filename or "").name
    if Path(original_name).suffix.lower() != ".xlsx":
        raise HTTPException(status_code=422, detail="File tự động đối chiếu công nợ phải có định dạng .xlsx.")
    contents = await file.read(COMMISSION_RECEIVABLE_MAX_FILE_SIZE + 1)
    if not contents:
        raise HTTPException(status_code=422, detail="File công nợ đang trống.")
    if len(contents) > COMMISSION_RECEIVABLE_MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="File công nợ vượt quá 15 MB.")
    clean_note = note.strip()
    if len(clean_note) > 2000:
        raise HTTPException(status_code=422, detail="Ghi chú công nợ không được vượt quá 2.000 ký tự.")
    try:
        parsed = parse_receivable_workbook(contents, original_name)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    candidates_by_job_no: dict[str, list[CommissionJob]] = {}
    for job in ordered_jobs:
        candidates_by_job_no.setdefault(normalize_receivable_job_no(job.job_no), []).append(job)
    matches: list[tuple[CommissionJob, ReceivableJobBalance]] = []
    unmatched_job_nos: list[str] = []
    for report_job in parsed.jobs:
        candidates = candidates_by_job_no.get(report_job.job_no, [])
        if len(candidates) != 1:
            unmatched_job_nos.append(report_job.job_no)
            continue
        matches.append((candidates[0], report_job))
    if not matches:
        raise HTTPException(
            status_code=422,
            detail="Không có JOB Balance bằng 0 hoặc dương nào trong file khớp với danh sách JOB của SALE đang xem.",
        )

    matched_job_ids = [job.id for job, _report_job in matches]
    ledger_entries = db.query(CommissionWalletLedger).filter(
        CommissionWalletLedger.period_id == period_id,
        CommissionWalletLedger.job_id.in_(matched_job_ids),
    ).all()
    positions = _wallet_positions(ledger_entries)
    period = db.query(CommissionPeriod).filter(CommissionPeriod.id == period_id).first()
    fallback_earned_by_job = {
        allocated_job.id: float(amount)
        for allocated_job, allocation_rep, amount, _is_paid in _period_wallet_allocations(period, db)
        if allocated_job is not None and allocation_rep == sales_rep
    } if period else {}
    uploaded_by = getattr(current_user, "username", None) or str(getattr(current_user, "id", ""))
    paid_amount_by_job: dict[int, float] = {}
    for job, report_job in matches:
        paid_amount = round(
            report_job.received_amount
            if report_job.received_amount > 0
            else max(0.0, report_job.receivable_amount - report_job.balance_amount),
            2,
        )
        job.receivable_amount = report_job.receivable_amount
        job.balance_amount = report_job.balance_amount
        job.payment_received_amount = paid_amount
        job.payment_received = "YES"
        paid_amount_by_job[job.id] = paid_amount
    db.flush()
    wallet_hold_targets = _period_wallet_hold_targets(period, db) if period else {}

    updates: list[CommissionReceivableReconciliationJobOut] = []
    for job, report_job in matches:
        from app.services.commission_wallet_rules import calculate_job_hold

        position = positions.get((job.sales_rep or "(Unknown)", job.id))
        net_bonus = max(0.0, float(
            position.get("earned", 0.0)
            if position is not None
            else fallback_earned_by_job.get(job.id, 0.0)
        ))
        hold_percent, hold_amount = calculate_job_hold(
            profit_loss=job.profit_loss,
            balance_amount=report_job.balance_amount,
            payment_received_amount=paid_amount_by_job[job.id],
        )
        paid_amount = paid_amount_by_job[job.id]
        _apply_fixed_job_hold(
            db,
            job,
            reason_code="RECEIVABLE_RECONCILIATION",
            note=(
                f"Đối chiếu AGEING: Balance = {report_job.balance_amount:,.2f}; "
                f"Hold JOB = {hold_amount:,.2f}; khách đã trả {paid_amount:,.2f}."
            ),
            created_by=uploaded_by or None,
            wallet_hold_amount=wallet_hold_targets.get(job.id, min(net_bonus, hold_amount)),
        )
        updates.append(CommissionReceivableReconciliationJobOut(
            job_id=job.id,
            job_no=job.job_no,
            source_rows=report_job.source_rows,
            receivable_amount=report_job.receivable_amount,
            payment_received_amount=paid_amount,
            balance_amount=report_job.balance_amount,
            paid_percent=round(report_job.paid_percent, 4),
            hold_bonus_percent=hold_percent,
            hold_bonus_amount=hold_amount,
            net_bonus=round(net_bonus, 2),
        ))

    stored_name = f"reconcile_{matches[0][0].id}_{uuid4().hex}.xlsx"
    COMMISSION_RECEIVABLE_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    stored_path = COMMISSION_RECEIVABLE_UPLOAD_DIR / stored_name
    attachment = CommissionJobReceivableAttachment(
        period_id=period_id,
        job_id=matches[0][0].id,
        original_filename=original_name,
        stored_filename=stored_name,
        content_type=file.content_type or "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        size_bytes=len(contents),
        note=clean_note or None,
        uploaded_by=uploaded_by or None,
    )
    try:
        stored_path.write_bytes(contents)
        db.add(attachment)
        db.flush()
        for job, _report_job in matches:
            db.add(CommissionJobReceivableLink(
                period_id=period_id,
                job_id=job.id,
                attachment_id=attachment.id,
            ))
        db.commit()
        db.refresh(attachment)
    except Exception:
        db.rollback()
        stored_path.unlink(missing_ok=True)
        raise

    return CommissionReceivableReconciliationOut(
        original_filename=original_name,
        sheet_name=parsed.sheet_name,
        positive_rows=parsed.positive_rows,
        ignored_non_positive_rows=parsed.ignored_non_positive_rows,
        invalid_positive_rows=parsed.invalid_positive_rows,
        matched_jobs=len(updates),
        unmatched_positive_jobs=len(unmatched_job_nos),
        unmatched_job_nos=unmatched_job_nos[:100],
        attachment=_receivable_attachment_out(attachment, matches[0][0]),
        updates=updates,
    )


async def _upload_receivables_for_jobs(
    files: List[UploadFile],
    note: str,
    period_id: int,
    jobs: list[CommissionJob],
    db: Session,
    current_user,
) -> list[CommissionReceivableAttachmentOut]:
    if not files or len(files) > COMMISSION_RECEIVABLE_MAX_FILES:
        raise HTTPException(
            status_code=422,
            detail=f"Mỗi lần chỉ được tải từ 1 đến {COMMISSION_RECEIVABLE_MAX_FILES} tệp công nợ.",
        )
    clean_note = note.strip()
    if len(clean_note) > 2000:
        raise HTTPException(status_code=422, detail="Ghi chú công nợ không được vượt quá 2.000 ký tự.")

    prepared: list[tuple[str, str, str, bytes]] = []
    for upload in files:
        original_name = Path(upload.filename or "").name
        suffix = Path(original_name).suffix.lower()
        if not original_name or suffix not in COMMISSION_RECEIVABLE_ALLOWED_EXTENSIONS:
            allowed = ", ".join(sorted(COMMISSION_RECEIVABLE_ALLOWED_EXTENSIONS))
            raise HTTPException(status_code=422, detail=f"Định dạng tệp công nợ không được hỗ trợ. Cho phép: {allowed}")
        contents = await upload.read(COMMISSION_RECEIVABLE_MAX_FILE_SIZE + 1)
        if not contents:
            raise HTTPException(status_code=422, detail=f"Tệp {original_name} đang trống.")
        if len(contents) > COMMISSION_RECEIVABLE_MAX_FILE_SIZE:
            raise HTTPException(status_code=413, detail=f"Tệp {original_name} vượt quá 15 MB.")
        stored_name = f"jobs_{jobs[0].id}_{uuid4().hex}{suffix}"
        prepared.append((original_name, stored_name, upload.content_type or "application/octet-stream", contents))

    COMMISSION_RECEIVABLE_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    written_paths: list[Path] = []
    created: list[CommissionJobReceivableAttachment] = []
    uploaded_by = getattr(current_user, "username", None) or str(getattr(current_user, "id", ""))
    try:
        for original_name, stored_name, content_type, contents in prepared:
            path = COMMISSION_RECEIVABLE_UPLOAD_DIR / stored_name
            path.write_bytes(contents)
            written_paths.append(path)
            attachment = CommissionJobReceivableAttachment(
                period_id=period_id,
                job_id=jobs[0].id,
                original_filename=original_name,
                stored_filename=stored_name,
                content_type=content_type,
                size_bytes=len(contents),
                note=clean_note or None,
                uploaded_by=uploaded_by or None,
            )
            db.add(attachment)
            db.flush()
            for job in jobs:
                db.add(CommissionJobReceivableLink(
                    period_id=period_id,
                    job_id=job.id,
                    attachment_id=attachment.id,
                ))
            created.append(attachment)
        db.commit()
        for attachment in created:
            db.refresh(attachment)
    except Exception:
        db.rollback()
        for path in written_paths:
            path.unlink(missing_ok=True)
        raise
    return [_receivable_attachment_out(item, jobs[0]) for item in created]


@router.get("/periods/{period_id}/jobs/{job_id}/receivables/{attachment_id}/file")
def download_job_receivable(
    period_id: int,
    job_id: int,
    attachment_id: int,
    db: Session = Depends(get_db),
):
    _commission_job_or_404(db, period_id, job_id)
    attachment = db.query(CommissionJobReceivableAttachment).join(
        CommissionJobReceivableLink,
        CommissionJobReceivableLink.attachment_id == CommissionJobReceivableAttachment.id,
    ).filter(
        CommissionJobReceivableAttachment.id == attachment_id,
        CommissionJobReceivableLink.period_id == period_id,
        CommissionJobReceivableLink.job_id == job_id,
    ).first()
    if not attachment:
        raise HTTPException(status_code=404, detail="Không tìm thấy hồ sơ công nợ.")
    path = _receivable_file_path(attachment.stored_filename)
    return FileResponse(
        path=path,
        media_type=attachment.content_type or "application/octet-stream",
        filename=attachment.original_filename,
    )


@router.delete(
    "/periods/{period_id}/jobs/{job_id}/receivables/{attachment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_job_receivable(
    period_id: int,
    job_id: int,
    attachment_id: int,
    db: Session = Depends(get_db),
):
    _commission_job_or_404(db, period_id, job_id)
    attachment = db.query(CommissionJobReceivableAttachment).join(
        CommissionJobReceivableLink,
        CommissionJobReceivableLink.attachment_id == CommissionJobReceivableAttachment.id,
    ).filter(
        CommissionJobReceivableAttachment.id == attachment_id,
        CommissionJobReceivableLink.period_id == period_id,
        CommissionJobReceivableLink.job_id == job_id,
    ).first()
    if not attachment:
        raise HTTPException(status_code=404, detail="Không tìm thấy hồ sơ công nợ.")
    try:
        file_path = _receivable_file_path(attachment.stored_filename)
    except HTTPException:
        file_path = None
    link = db.query(CommissionJobReceivableLink).filter(
        CommissionJobReceivableLink.attachment_id == attachment_id,
        CommissionJobReceivableLink.job_id == job_id,
        CommissionJobReceivableLink.period_id == period_id,
    ).first()
    if not link:
        raise HTTPException(status_code=404, detail="Không tìm thấy hồ sơ công nợ.")
    db.delete(link)
    db.flush()
    has_other_links = db.query(CommissionJobReceivableLink.id).filter(
        CommissionJobReceivableLink.attachment_id == attachment_id,
    ).first() is not None
    if not has_other_links:
        db.delete(attachment)
    db.commit()
    if file_path and not has_other_links:
        file_path.unlink(missing_ok=True)
    return None


@router.patch("/periods/{period_id}/jobs/{job_id}/hold-bonus")
def update_job_hold_bonus(
    period_id: int,
    job_id: int,
    payload: CommissionJobHoldBonusIn,
    db: Session = Depends(get_db),
    current_user=Depends(get_admin_user),
):
    """Hold Bonus is policy-derived and cannot be edited manually."""
    _commission_job_or_404(db, period_id, job_id)
    raise HTTPException(
        status_code=409,
        detail="Hold Bonus được cố định ở mức 30% Bonus ròng và không được phép chỉnh sửa thủ công.",
    )


@router.patch("/periods/{period_id}/jobs/{job_id}/manual-payment")
def manually_update_job_payment_received(
    period_id: int,
    job_id: int,
    payload: CommissionJobManualPaymentIn,
    db: Session = Depends(get_db),
    current_user=Depends(get_admin_user),
):
    """Correct Payment Received directly from the administrator JOB editor.

    This is intentionally separate from ``/payment``: the latter is the Sales
    report/accounting-verification workflow.  The administrator editor updates
    the receivable snapshot immediately, then reconciles the fixed JOB hold and
    bonus wallet so every summary can be refreshed without a page reload.
    """
    job = db.query(CommissionJob).filter(
        CommissionJob.id == job_id,
        CommissionJob.period_id == period_id,
    ).first()
    if not job:
        raise HTTPException(status_code=404, detail="Không tìm thấy JOB trong kỳ commission.")
    _ensure_bonus_editable(db, period_id, job.sales_rep or "(Unknown)")

    normalized = payload.payment_received.strip().upper()
    paid_amount = round(float(payload.payment_received_amount or 0.0), 2)
    if normalized == "YES" and paid_amount <= 0:
        raise HTTPException(
            status_code=422,
            detail="Khi chọn YES, vui lòng nhập số tiền khách hàng đã trả lớn hơn 0.",
        )
    if normalized == "NO":
        paid_amount = 0.0

    previous_status = str(job.payment_received or "NO").strip().upper()
    previous_amount = round(float(job.payment_received_amount or 0.0), 2)
    profit_loss = round(float(job.profit_loss or 0.0), 2)
    actor = _actor_name(current_user)
    period = db.get(CommissionPeriod, period_id)
    customer_payment_months = _source_payout_periods(period) if period else []
    normal_payout_months = _next_commission_payout_periods(period) if period else []
    source_entries = db.query(CommissionWalletLedger).filter(
        CommissionWalletLedger.period_id == period_id,
        CommissionWalletLedger.job_id == job.id,
        CommissionWalletLedger.sales_rep == (job.sales_rep or "(Unknown)"),
    ).order_by(CommissionWalletLedger.id.asc()).all()
    position_before = _wallet_positions(source_entries).get((job.sales_rep or "(Unknown)", job.id), {})
    held_before = round(float(position_before.get("payment_held", 0.0)), 2)
    from app.services.commission_wallet_rules import calculate_job_hold

    previous_hold_amount = calculate_job_hold(
        profit_loss=job.profit_loss,
        balance_amount=job.balance_amount,
        payment_received_amount=job.payment_received_amount,
    )[1]
    is_fully_paid = normalized == "YES" and paid_amount >= max(0.0, profit_loss) - 0.005
    status_changed_to_yes = previous_status == "NO" and normalized == "YES"
    unlocks_existing_hold = is_fully_paid and previous_hold_amount > 0.005
    requires_payment_month = status_changed_to_yes or unlocks_existing_hold
    selected_payout_months: list[str] = []
    if requires_payment_month:
        if len(customer_payment_months) != 3 or len(normal_payout_months) != 3:
            raise HTTPException(status_code=422, detail="Không xác định được ba tháng của kỳ Commission và kỳ chi trả.")
        middle_payment_month = customer_payment_months[1]
        if payload.payment_month != middle_payment_month:
            raise HTTPException(
                status_code=422,
                detail=(
                    "Tháng khách hàng thanh toán phải là tháng giữa của kỳ Commission "
                    f"({middle_payment_month})."
                ),
            )
        if not payload.payment_date or payload.payment_date.strftime("%Y-%m") != middle_payment_month:
            raise HTTPException(
                status_code=422,
                detail=f"Hãy chọn ngày khách hàng thanh toán thuộc tháng {middle_payment_month}.",
            )
        if is_fully_paid and payload.payment_month:
            payment_index = customer_payment_months.index(payload.payment_month)
            payout_start_index = (
                max(0, payment_index - 1)
                if payload.payment_date.day <= 25
                else payment_index
            )
            payout_candidates = normal_payout_months[payout_start_index:]
            requested_payout_months = [
                str(month or "").strip()
                for month in (payload.payout_months or [])
                if str(month or "").strip()
            ]
            requested_set = set(requested_payout_months)
            if (
                not requested_payout_months
                or len(requested_set) != len(requested_payout_months)
                or not requested_set.issubset(set(payout_candidates))
            ):
                raise HTTPException(
                    status_code=422,
                    detail=(
                        "Hãy chọn tháng chi hợp lệ: tháng chi đầu tiên chỉ khả dụng khi "
                        "khách thanh toán chậm nhất ngày 25; các tháng còn lại luôn khả dụng."
                    ),
                )
            selected_payout_months = [
                month for month in payout_candidates if month in requested_set
            ]

    job.payment_received = normalized
    job.payment_received_amount = paid_amount
    # A manual correction becomes the current receivable evidence.  Keeping
    # Balance as P/L minus the entered payment preserves the company rule:
    # partial payment remains Hold 30%, full payment removes the hold, and an
    # overpayment produces a negative Balance that is ignored.
    job.receivable_amount = max(0.0, profit_loss)
    job.balance_amount = round(profit_loss - paid_amount, 2) if normalized == "YES" else max(0.0, profit_loss)
    if requires_payment_month and payload.payment_month:
        # Keep the confirmed customer-payment month even for a partial payment.
        # If the administrator later raises the paid amount to fully paid, the
        # editor can reuse this month as the default split point.
        job.held_release_payout_period = payload.payment_month
    default_remark = (
        f"Quản trị viên chỉnh Payment Received {previous_status} → {normalized}; "
        f"đã trả {paid_amount:,.2f}"
        f"{f'; ngày khách thanh toán {payload.payment_date.isoformat()}' if payload.payment_date else ''}."
    )
    job.bonus_remark = payload.remark.strip() if payload.remark and payload.remark.strip() else default_remark
    db.flush()

    # Recalculate formula entitlements and all period-level wallet targets
    # before enforcing this JOB's authoritative manual status.
    sync_result = sync_commission_wallet(CommissionWalletSyncIn(period_id=period_id), db, current_user)
    db.refresh(job)
    period = db.get(CommissionPeriod, period_id)
    wallet_hold_targets = _period_wallet_hold_targets(period, db) if period else {}

    hold_percent, hold_amount = calculate_job_hold(
        profit_loss=job.profit_loss,
        balance_amount=job.balance_amount,
        payment_received_amount=job.payment_received_amount,
    )
    job.hold_bonus_percent = hold_percent
    job.hold_bonus_amount = hold_amount
    wallet_hold_delta = _reconcile_job_hold_ledger(
        db,
        job,
        wallet_hold_targets.get(job.id, 0.0),
        reason_code="MANUAL_PAYMENT_OVERRIDE",
        note=(
            f"Chỉnh tay Payment Received {previous_status} → {normalized}; "
            f"số tiền đã trả {paid_amount:,.2f}; Hold JOB {hold_amount:,.2f}."
        ),
        created_by=actor,
    )
    release_allocations: list[dict] = []
    schedule_ids: list[int] = []
    if is_fully_paid and held_before >= 0.005 and payload.payment_month:
        if not selected_payout_months:
            raise HTTPException(status_code=422, detail="Chưa chọn tháng chi bonus đang giữ.")
        remaining_amount = round(held_before, 2)
        allocation_count = len(selected_payout_months)
        for index, payout_month in enumerate(selected_payout_months):
            allocation_amount = (
                round(remaining_amount, 2)
                if index == allocation_count - 1
                else round(held_before / allocation_count, 2)
            )
            remaining_amount = round(remaining_amount - allocation_amount, 2)
            release_allocations.append({
                "payout_period": payout_month,
                "amount": allocation_amount,
            })

        source = source_entries[0] if source_entries else None
        if not source:
            raise HTTPException(status_code=422, detail="Không tìm thấy sổ cái nguồn của JOB để lập lịch chi trả.")
        allocation_note = (
            f"Khách thanh toán đủ ngày {payload.payment_date.isoformat()}; chia đều bonus đang giữ "
            f"của JOB {job.job_no} vào {', '.join(selected_payout_months)}."
        )
        for allocation in release_allocations:
            schedule = CommissionPayoutSchedule(
                sales_rep=job.sales_rep or "(Unknown)",
                employee_id=source.employee_id,
                payout_period=allocation["payout_period"],
                total_amount=allocation["amount"],
                note=allocation_note,
                created_by=actor,
                approved_by=actor,
            )
            db.add(schedule)
            db.flush()
            ledger = CommissionWalletLedger(
                period_id=period_id,
                job_id=job.id,
                entitlement_id=source.entitlement_id,
                schedule_id=schedule.id,
                sales_rep=job.sales_rep or "(Unknown)",
                employee_id=source.employee_id,
                entry_type="SCHEDULED",
                amount=allocation["amount"],
                payout_period=allocation["payout_period"],
                reason_code="MANUAL_PAYMENT_SELECTED_MONTHS",
                note=allocation_note,
                created_by=actor,
                approved_by=actor,
            )
            db.add(ledger)
            db.flush()
            db.add(CommissionPayoutScheduleAllocation(
                schedule_id=schedule.id,
                entitlement_id=source.entitlement_id,
                ledger_entry_id=ledger.id,
                amount=allocation["amount"],
            ))
            schedule_ids.append(schedule.id)
        job.held_release_mode = (
            "NEXT_QUARTER_LUMP" if len(selected_payout_months) == 1
            else "NEXT_QUARTER_SPLIT"
        )
        job.held_release_payout_period = payload.payment_month

    cancelled_schedule_ids: list[int] = []
    if previous_status == "YES" and normalized == "NO":
        manual_schedule_entries = db.query(CommissionWalletLedger).filter(
            CommissionWalletLedger.period_id == period_id,
            CommissionWalletLedger.job_id == job.id,
            CommissionWalletLedger.entry_type == "SCHEDULED",
            CommissionWalletLedger.reason_code.in_([
                "MANUAL_PAYMENT_SPLIT",
                "MANUAL_PAYMENT_MONTH_RELEASE",
                "MANUAL_PAYMENT_SELECTED_MONTHS",
            ]),
        ).all()
        for scheduled_entry in manual_schedule_entries:
            schedule = db.get(CommissionPayoutSchedule, scheduled_entry.schedule_id) if scheduled_entry.schedule_id else None
            if not schedule or schedule.status != "SCHEDULED":
                continue
            allocations = db.query(CommissionPayoutScheduleAllocation).filter(
                CommissionPayoutScheduleAllocation.schedule_id == schedule.id,
                CommissionPayoutScheduleAllocation.status == "SCHEDULED",
            ).all()
            for allocation in allocations:
                allocation.status = "CANCELLED"
            db.add(CommissionWalletLedger(
                period_id=scheduled_entry.period_id,
                job_id=scheduled_entry.job_id,
                entitlement_id=scheduled_entry.entitlement_id,
                schedule_id=schedule.id,
                sales_rep=scheduled_entry.sales_rep,
                employee_id=scheduled_entry.employee_id,
                entry_type="SCHEDULE_RELEASE",
                amount=-abs(float(scheduled_entry.amount or 0.0)),
                payout_period=scheduled_entry.payout_period,
                reason_code="MANUAL_PAYMENT_REVERSED",
                note="Payment Received chuyển YES → NO; hủy lịch trả bonus đang giữ chưa chi trả.",
                created_by=actor,
                approved_by=actor,
            ))
            schedule.status = "CANCELLED"
            schedule.approved_by = actor
            cancelled_schedule_ids.append(schedule.id)
        job.held_release_payout_period = None

    db.add(CommissionWalletLedger(
        period_id=period_id,
        job_id=job.id,
        sales_rep=job.sales_rep or "(Unknown)",
        employee_id=_employee_id_for_sales_rep(job.sales_rep or "(Unknown)", db),
        entry_type="PAYMENT_MANUAL_OVERRIDE",
        amount=0.0,
        reason_code="MANUAL_PAYMENT_OVERRIDE",
        note=(
            f"Payment Received {previous_status} → {normalized}; "
            f"đã trả {previous_amount:,.2f} → {paid_amount:,.2f}. "
            f"Ngày khách thanh toán: {payload.payment_date.isoformat() if payload.payment_date else 'không áp dụng'}. "
            f"{job.bonus_remark}"
        ),
        created_by=actor,
    ))
    db.commit()

    return {
        **sync_result,
        "message": f"Đã cập nhật Payment Received của JOB {job.job_no} và đồng bộ dữ liệu liên quan.",
        "payment_received": normalized,
        "payment_received_amount": paid_amount,
        "receivable_amount": job.receivable_amount,
        "balance_amount": job.balance_amount,
        "hold_bonus_percent": hold_percent,
        "hold_bonus_amount": hold_amount,
        "wallet_hold_delta": wallet_hold_delta,
        "payment_month": payload.payment_month,
        "payment_date": payload.payment_date.isoformat() if payload.payment_date else None,
        "payout_months": selected_payout_months,
        "release_allocations": release_allocations,
        "schedule_ids": schedule_ids,
        "cancelled_schedule_ids": cancelled_schedule_ids,
        "wallet_synchronized": True,
    }


@router.patch("/periods/{period_id}/jobs/{job_id}/payment")
def update_job_payment_received(
    period_id: int,
    job_id: int,
    payload: CommissionJobPaymentIn,
    db: Session = Depends(get_db),
    current_user=Depends(get_admin_user),
):
    """Update Payment Received and immediately create the corresponding wallet event."""
    normalized = payload.payment_received.strip().upper()
    if normalized not in {"YES", "NO"}:
        raise HTTPException(status_code=422, detail="Payment Received chỉ nhận YES hoặc NO.")
    job = db.query(CommissionJob).filter(CommissionJob.id == job_id, CommissionJob.period_id == period_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Không tìm thấy JOB trong kỳ commission.")
    _ensure_bonus_editable(db, period_id, job.sales_rep or "(Unknown)")
    previous = str(job.payment_received or "NO").strip().upper()
    # This endpoint used to release held bonus immediately.  Keep its URL for
    # backward compatibility, but change NO -> YES into a report for
    # accounting.  Only the payment-command endpoint below may move money.
    if previous == "NO" and normalized == "YES":
        return _report_payment_received(job, payload.remark, db, current_user)
    if previous == "YES" and normalized == "NO":
        raise HTTPException(status_code=409, detail="Payment Received đã được kế toán xác minh. Hãy dùng quy trình kế toán để đảo xác minh; lịch sử không được sửa trực tiếp.")
    if previous == normalized:
        job.bonus_remark = payload.remark.strip() if payload.remark and payload.remark.strip() else job.bonus_remark
        db.commit()
        return {"message": "Trạng thái Payment Received không thay đổi; đã cập nhật ghi chú.", "payment_received": previous, "remark": job.bonus_remark, "wallet_synchronized": False}
    release_mode = payload.release_mode or "NEXT_QUARTER_LUMP"
    release_payout_period = payload.release_payout_period or job.held_release_payout_period
    next_release_months: list[str] = []
    if previous == "NO" and normalized == "YES":
        source_period = db.get(CommissionPeriod, period_id)
        next_release_months = _next_commission_payout_periods(source_period) if source_period else []
        if not next_release_months:
            raise HTTPException(status_code=422, detail="Không xác định được ba tháng chi trả của kỳ commission kế tiếp.")
        if release_mode == "NEXT_QUARTER_LUMP" and release_payout_period and release_payout_period not in next_release_months:
            raise HTTPException(status_code=422, detail="Tháng trả dồn phải thuộc ba tháng của kỳ commission kế tiếp.")

    # A later correction from YES back to NO must cancel any unpaid future
    # release allocations before the normal re-hold transaction is created.
    # The ledger stays immutable: cancellations are negative rows, never edits.
    if previous == "YES" and normalized == "NO":
        prior_releases = db.query(CommissionWalletLedger).filter(
            CommissionWalletLedger.period_id == period_id,
            CommissionWalletLedger.job_id == job_id,
            CommissionWalletLedger.entry_type.in_({"PAYMENT_RELEASE_ALLOCATION", "PAYMENT_RELEASE_REVERSAL"}),
        ).all()
        release_by_month: dict[str, float] = {}
        for entry in prior_releases:
            if entry.payout_period:
                release_by_month[entry.payout_period] = round(
                    release_by_month.get(entry.payout_period, 0.0) + float(entry.amount or 0.0), 2
                )
        for payout_period, amount in release_by_month.items():
            if amount <= 0.004:
                continue
            db.add(CommissionWalletLedger(
                period_id=period_id, job_id=job_id, entitlement_id=prior_releases[0].entitlement_id if prior_releases else None,
                sales_rep=job.sales_rep or "(Unknown)", employee_id=_employee_id_for_sales_rep(job.sales_rep or "(Unknown)", db),
                entry_type="PAYMENT_RELEASE_REVERSAL", amount=-amount, payout_period=payout_period,
                reason_code="PAYMENT_REVERSED",
                note="Payment Received chuyển YES → NO; hủy phân bổ chi trả phần giữ chưa thanh toán.",
                created_by=current_user.username if hasattr(current_user, "username") else str(current_user.id),
            ))
    job.payment_received = normalized
    if previous != normalized:
        default_remark = "Payment Received NO → YES: khách hàng đã thanh toán, mở giữ tự động." if normalized == "YES" else "Payment Received YES → NO: khách hàng chưa thanh toán, chuyển bonus sang giữ tự động."
        job.bonus_remark = payload.remark.strip() if payload.remark and payload.remark.strip() else default_remark
        db.flush()
        sync_result = sync_commission_wallet(CommissionWalletSyncIn(period_id=period_id), db, current_user)
        release_allocations: list[dict] = []
        if previous == "NO" and normalized == "YES":
            source_period = db.get(CommissionPeriod, period_id)
            target_months = _next_commission_payout_periods(source_period) if source_period else []
            if not target_months:
                raise HTTPException(status_code=422, detail="Kỳ commission chưa có ngày kết thúc để xác định ba tháng chi trả kế tiếp.")
            job_entries = db.query(CommissionWalletLedger).filter(
                CommissionWalletLedger.period_id == period_id,
                CommissionWalletLedger.job_id == job_id,
                CommissionWalletLedger.sales_rep == (job.sales_rep or "(Unknown)"),
            ).order_by(CommissionWalletLedger.id.asc()).all()
            position = _wallet_positions(job_entries).get((job.sales_rep or "(Unknown)", job_id), {})
            held_amount = round(float(position.get("payment_held", 0.0)), 2)
            if held_amount >= 0.005:
                source = job_entries[0]
                target_month = release_payout_period or target_months[0]
                if target_month not in target_months:
                    raise HTTPException(status_code=422, detail="Tháng trả một lần phải thuộc ba tháng của kỳ commission kế tiếp.")
                allocations = [(target_month, held_amount)]
                release_note = f"Payment Received NO → YES; trả một lần phần giữ vào tháng {target_month}."
                db.add(CommissionWalletLedger(
                    period_id=source.period_id, job_id=source.job_id, entitlement_id=source.entitlement_id,
                    sales_rep=source.sales_rep, employee_id=source.employee_id,
                    entry_type="RELEASED", amount=held_amount, reason_code="PAYMENT_RECEIVED",
                    note=release_note,
                    created_by=current_user.username if hasattr(current_user, "username") else str(current_user.id),
                ))
                for target_month, amount in allocations:
                    db.add(CommissionWalletLedger(
                        period_id=source.period_id, job_id=source.job_id, entitlement_id=source.entitlement_id,
                        sales_rep=source.sales_rep, employee_id=source.employee_id,
                        entry_type="PAYMENT_RELEASE_ALLOCATION", amount=amount, payout_period=target_month,
                        reason_code=release_mode, note=release_note,
                        created_by=current_user.username if hasattr(current_user, "username") else str(current_user.id),
                    ))
                    release_allocations.append({"payout_period": target_month, "amount": amount})
                db.commit()
        message = "Payment Received NO → YES: đã lập phân bổ chi trả phần giữ cho kỳ tiếp sau." if normalized == "YES" else "Payment Received YES → NO: đã chuyển phần khả dụng sang giữ tự động."
        return {**sync_result, "message": message, "payment_received": normalized, "remark": job.bonus_remark, "wallet_synchronized": True, "release_allocations": release_allocations}
    job.bonus_remark = payload.remark.strip() if payload.remark and payload.remark.strip() else None
    db.commit()
    return {"message": "Đã cập nhật ghi chú JOB; trạng thái Payment Received không thay đổi.", "payment_received": normalized, "remark": job.bonus_remark, "wallet_synchronized": False}


# ────────────────────────────────────────────────────────────────────────────
def _actor_name(current_user) -> str:
    return current_user.username if hasattr(current_user, "username") else str(current_user.id)


def _report_payment_received(job: CommissionJob, note: Optional[str], db: Session, current_user):
    """Record a Sales report without changing payment status or wallet money."""
    actor = _actor_name(current_user)
    verification = db.query(CommissionPaymentVerification).filter(CommissionPaymentVerification.job_id == job.id).first()
    if verification and verification.status in {"PENDING", "VERIFIED", "COMMAND_CREATED"}:
        raise HTTPException(status_code=409, detail="JOB này đã có yêu cầu thanh toán đang được kế toán xử lý.")
    if verification:
        verification.status = "PENDING"
        verification.report_note = note.strip() if note and note.strip() else None
        verification.verification_note = None
        verification.reported_by = actor
        verification.reported_at = datetime.now(timezone.utc)
        verification.verified_by = None
        verification.verified_at = None
        verification.command_created_by = None
        verification.command_created_at = None
    else:
        verification = CommissionPaymentVerification(period_id=job.period_id, job_id=job.id, sales_rep=job.sales_rep or "(Unknown)", status="PENDING", report_note=note.strip() if note and note.strip() else None, reported_by=actor)
        db.add(verification)
    db.add(CommissionWalletLedger(period_id=job.period_id, job_id=job.id, sales_rep=job.sales_rep or "(Unknown)", employee_id=_employee_id_for_sales_rep(job.sales_rep or "(Unknown)", db), entry_type="PAYMENT_REPORTED", amount=0.0, reason_code="SALES_REPORTED_PAID", note=note.strip() if note and note.strip() else "Sales báo khách hàng đã thanh toán; chờ kế toán xác minh.", created_by=actor))
    db.commit()
    return {"message": "Đã ghi nhận Sales báo khách hàng thanh toán. Ví thưởng chưa thay đổi; chờ kế toán xác minh.", "status": "PENDING"}


@router.post("/periods/{period_id}/jobs/{job_id}/payment-report")
def report_commission_payment_received(period_id: int, job_id: int, payload: CommissionPaymentReportIn, db: Session = Depends(get_db), current_user=Depends(get_admin_user)):
    job = db.query(CommissionJob).filter(CommissionJob.id == job_id, CommissionJob.period_id == period_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Không tìm thấy JOB trong kỳ commission.")
    _ensure_bonus_editable(db, period_id, job.sales_rep or "(Unknown)")
    if _is_payment_received(job.payment_received):
        raise HTTPException(status_code=409, detail="JOB này đã được kế toán xác minh thanh toán.")
    return _report_payment_received(job, payload.note, db, current_user)


@router.post("/payment-verifications/{verification_id}/review")
def review_commission_payment_report(verification_id: int, payload: CommissionPaymentVerificationIn, db: Session = Depends(get_db), current_user=Depends(get_admin_user)):
    verification = db.get(CommissionPaymentVerification, verification_id)
    if not verification or verification.status != "PENDING":
        raise HTTPException(status_code=409, detail="Yêu cầu không tồn tại hoặc không còn chờ kế toán xác minh.")
    job = db.get(CommissionJob, verification.job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Không tìm thấy JOB của yêu cầu.")
    _ensure_bonus_editable(db, verification.period_id, verification.sales_rep)
    actor = _actor_name(current_user)
    verification.status = "VERIFIED" if payload.action == "VERIFY" else "REJECTED"
    verification.verification_note = payload.note.strip() if payload.note and payload.note.strip() else None
    verification.verified_by = actor
    verification.verified_at = datetime.now(timezone.utc)
    if payload.action == "VERIFY":
        job.payment_received = "YES"
        job.bonus_remark = "Kế toán đã xác minh khách hàng thanh toán; chờ lập lệnh chi trả theo JOB."
        entry_type, reason, default_note = "PAYMENT_VERIFIED", "ACCOUNTING_VERIFIED", "Kế toán xác minh khách hàng đã thanh toán; tiền vẫn đang giữ cho đến khi lập lệnh chi trả."
    else:
        entry_type, reason, default_note = "PAYMENT_REJECTED", "ACCOUNTING_REJECTED", "Kế toán chưa xác minh được thanh toán; JOB tiếp tục ở trạng thái đang giữ."
    db.add(CommissionWalletLedger(period_id=verification.period_id, job_id=job.id, sales_rep=verification.sales_rep, employee_id=_employee_id_for_sales_rep(verification.sales_rep, db), entry_type=entry_type, amount=0.0, reason_code=reason, note=payload.note.strip() if payload.note and payload.note.strip() else default_note, created_by=actor, approved_by=actor))
    db.commit()
    return {"message": "Đã xác minh thanh toán; ví chưa thay đổi, hãy lập lệnh chi trả theo JOB." if payload.action == "VERIFY" else "Đã từ chối xác minh; tiền tiếp tục được giữ.", "status": verification.status}


@router.post("/payment-verifications/{verification_id}/payout-command")
def create_commission_payment_command(verification_id: int, payload: CommissionPaymentCommandIn, db: Session = Depends(get_db), current_user=Depends(get_admin_user)):
    verification = db.get(CommissionPaymentVerification, verification_id)
    if not verification or verification.status != "VERIFIED":
        raise HTTPException(status_code=409, detail="Chỉ JOB đã được kế toán xác minh mới được lập lệnh chi trả.")
    job, period = db.get(CommissionJob, verification.job_id), db.get(CommissionPeriod, verification.period_id)
    if not job or not period:
        raise HTTPException(status_code=404, detail="Không tìm thấy JOB hoặc kỳ nguồn.")
    _ensure_bonus_editable(db, verification.period_id, verification.sales_rep)
    source_entries = db.query(CommissionWalletLedger).filter(CommissionWalletLedger.period_id == verification.period_id, CommissionWalletLedger.job_id == job.id, CommissionWalletLedger.sales_rep == verification.sales_rep).order_by(CommissionWalletLedger.id).all()
    position = _wallet_positions(source_entries).get((verification.sales_rep, job.id), {})
    held_amount = round(float(position.get("payment_held", 0.0)), 2)
    if held_amount < 0.005:
        raise HTTPException(status_code=422, detail="JOB không còn số bonus giữ tự động để lập lệnh chi trả.")
    target_months = _next_commission_payout_periods(period)
    if len(target_months) != 3:
        raise HTTPException(status_code=422, detail="Không xác định được ba tháng chi trả của kỳ sau.")
    target = payload.release_payout_period
    if not target:
        raise HTTPException(status_code=422, detail="Phải chọn tháng chi trả một lần.")
    if target not in target_months:
        raise HTTPException(status_code=422, detail="Tháng chi trả một lần phải thuộc ba tháng của kỳ sau.")
    allocations = [(target, held_amount)]
    source = source_entries[0] if source_entries else None
    if not source:
        raise HTTPException(status_code=422, detail="Không tìm thấy sổ cái nguồn của JOB.")
    actor = _actor_name(current_user)
    command_note = payload.note.strip() if payload.note and payload.note.strip() else f"Lệnh kế toán: trả một lần bonus JOB đã xác minh vào tháng {target}."
    db.add(CommissionWalletLedger(period_id=source.period_id, job_id=source.job_id, entitlement_id=source.entitlement_id, sales_rep=source.sales_rep, employee_id=source.employee_id, entry_type="RELEASED", amount=held_amount, reason_code="ACCOUNTING_PAYMENT_COMMAND", note=command_note, created_by=actor, approved_by=actor))
    schedule_ids = []
    for payout_period, amount in allocations:
        if amount < 0.005:
            continue
        schedule = CommissionPayoutSchedule(sales_rep=verification.sales_rep, employee_id=source.employee_id, payout_period=payout_period, total_amount=amount, note=command_note, payment_verification_id=verification.id, created_by=actor, approved_by=actor)
        db.add(schedule); db.flush()
        ledger = CommissionWalletLedger(period_id=source.period_id, job_id=source.job_id, entitlement_id=source.entitlement_id, schedule_id=schedule.id, sales_rep=source.sales_rep, employee_id=source.employee_id, entry_type="SCHEDULED", amount=amount, payout_period=payout_period, reason_code="ACCOUNTING_PAYMENT_COMMAND", note=command_note, created_by=actor, approved_by=actor)
        db.add(ledger); db.flush()
        db.add(CommissionPayoutScheduleAllocation(schedule_id=schedule.id, entitlement_id=source.entitlement_id, ledger_entry_id=ledger.id, amount=amount))
        schedule_ids.append(schedule.id)
    verification.status = "COMMAND_CREATED"; verification.command_created_by = actor; verification.command_created_at = datetime.now(timezone.utc)
    job.held_release_mode = "NEXT_QUARTER_LUMP"
    job.held_release_payout_period = target
    if source.employee_id:
        from app.models.employee import Employee

        target_employee = db.get(Employee, source.employee_id)
        if target_employee:
            payout_labels = ", ".join(month.replace("-", "/") for month, amount in allocations if amount >= 0.005)
            add_employee_notification(
                db,
                target_employee,
                category=BONUS,
                event_type="BONUS_PAYOUT_APPROVED",
                title=f"Đã duyệt chi trả bonus JOB {job.job_no}",
                message=f"Kế toán trưởng đã lập lệnh chi trả {held_amount:,.0f} VND cho JOB {job.job_no}; tháng nhận: {payout_labels}.",
                actor_user_id=actor_id(current_user),
                resource_type="COMMISSION_JOB",
                resource_id=job.id,
                action_url="/user/my-held-bonuses",
            )
    db.commit()
    return {"message": "Đã lập lệnh chi trả theo JOB. Số tiền chuyển từ đang giữ sang lịch chi trả.", "schedule_ids": schedule_ids, "amount": held_amount}


@router.post("/periods/{period_id}/jobs/{job_id}/direct-payout-command")
def create_direct_commission_payment_command(
    period_id: int,
    job_id: int,
    payload: CommissionPaymentCommandIn,
    db: Session = Depends(get_db),
    current_user=Depends(get_admin_user),
):
    """Let accounting pay a held JOB without waiting for an employee request.

    The direct action still records an accounting verification before using the
    normal payout-command path, so wallet history and employee notifications
    remain identical to the reviewed-request workflow.
    """
    job = db.query(CommissionJob).filter(
        CommissionJob.id == job_id,
        CommissionJob.period_id == period_id,
    ).first()
    if not job:
        raise HTTPException(status_code=404, detail="Không tìm thấy JOB trong kỳ commission.")
    _ensure_bonus_editable(db, period_id, job.sales_rep or "(Unknown)")

    verification = db.query(CommissionPaymentVerification).filter(
        CommissionPaymentVerification.job_id == job.id,
    ).first()
    if verification and verification.status == "COMMAND_CREATED":
        raise HTTPException(status_code=409, detail="JOB này đã có lệnh chi trả đang hoạt động.")

    actor = _actor_name(current_user)
    now = datetime.now(timezone.utc)
    direct_note = (
        payload.note.strip()
        if payload.note and payload.note.strip()
        else "Kế toán chủ động xác minh và lập lệnh chi trả cho JOB."
    )
    if verification:
        verification.status = "VERIFIED"
        verification.verification_note = direct_note
        verification.verified_by = actor
        verification.verified_at = now
        verification.command_created_by = None
        verification.command_created_at = None
    else:
        verification = CommissionPaymentVerification(
            period_id=job.period_id,
            job_id=job.id,
            sales_rep=job.sales_rep or "(Unknown)",
            status="VERIFIED",
            report_note="Kế toán chủ động chi trả; không có yêu cầu trước từ nhân viên.",
            verification_note=direct_note,
            reported_by=actor,
            reported_at=now,
            verified_by=actor,
            verified_at=now,
        )
        db.add(verification)
    job.payment_received = "YES"
    job.bonus_remark = direct_note
    db.add(CommissionWalletLedger(
        period_id=job.period_id,
        job_id=job.id,
        sales_rep=job.sales_rep or "(Unknown)",
        employee_id=_employee_id_for_sales_rep(job.sales_rep or "(Unknown)", db),
        entry_type="PAYMENT_VERIFIED",
        amount=0.0,
        reason_code="ACCOUNTING_DIRECT_PAYOUT",
        note=direct_note,
        created_by=actor,
        approved_by=actor,
    ))
    db.flush()
    return create_commission_payment_command(verification.id, payload, db, current_user)


# Commission wallet: immutable ledger, allocation uses the existing monthly
# commission result and the confirmed positive Profit/Loss ratio per JOB.
# ────────────────────────────────────────────────────────────────────────────
_EARNED_TYPES = {"ACCRUAL_HELD", "ACCRUAL_AVAILABLE", "ADJUSTMENT_HELD", "ADJUSTMENT_AVAILABLE", "REVERSAL_HELD", "REVERSAL_AVAILABLE", "REVERSAL_PAID", "MANUAL_CREDIT", "MANUAL_DECREASE", "MANUAL_CREDIT_REVERSAL", "MANUAL_DECREASE_REVERSAL"}
_PAYMENT_HELD_TYPES = {"ACCRUAL_HELD", "ADJUSTMENT_HELD", "REVERSAL_HELD", "PAYMENT_STATUS_HOLD"}
_MANUAL_HOLD_TYPES = {"MANUAL_HOLD"}


def _is_payment_received(value: Optional[str]) -> bool:
    return str(value or "").strip().upper() in {"YES", "Y", "PAID", "TRUE", "1"}


def _source_payout_periods(period: CommissionPeriod) -> list[str]:
    """Three payroll months generated by one source commission quarter."""
    if not period.till_date:
        return []
    year, month = period.till_date.year, period.till_date.month
    result: list[str] = []
    for _ in range(3):
        year += 1 if month == 12 else 0
        month = 1 if month == 12 else month + 1
        result.append(f"{year:04d}-{month:02d}")
    return result


def _next_commission_payout_periods(period: CommissionPeriod) -> list[str]:
    """Return the three payroll months of the cycle after a source quarter."""
    source_months = _source_payout_periods(period)
    if len(source_months) != 3:
        return []
    year, month = map(int, source_months[-1].split("-"))
    result: list[str] = []
    for _ in range(3):
        year += 1 if month == 12 else 0
        month = 1 if month == 12 else month + 1
        result.append(f"{year:04d}-{month:02d}")
    return result


def _job_policy_hold_for_monthly_base(job: CommissionJob) -> float:
    """Keep the original three-month base stable after a JOB hold is released."""
    current_hold = max(0.0, float(job.hold_bonus_amount or 0.0))
    if current_hold > 0.005 or not job.held_release_payout_period:
        return current_hold
    return round(max(0.0, float(job.profit_loss or 0.0)) * 0.30, 2)


def _wallet_positions(entries: list[CommissionWalletLedger]) -> dict[tuple[str, Optional[int]], dict]:
    """Derive balances only from ledger rows; no balance is stored or overwritten."""
    positions: dict[tuple[str, Optional[int]], dict] = {}
    for entry in entries:
        key = (entry.sales_rep, entry.job_id)
        data = positions.setdefault(key, {
            "earned": 0.0, "calculation_earned": 0.0, "payment_held": 0.0, "manual_held": 0.0,
            "released": 0.0, "manual_released": 0.0, "scheduled": 0.0,
            "paid": 0.0, "manual_credit": 0.0, "manual_decrease": 0.0,
            "transferred_out": 0.0, "transferred_in": 0.0,
            "entries": [],
        })
        data["entries"].append(entry)
        if entry.entry_type in _EARNED_TYPES:
            data["earned"] += entry.amount
            # Manual credit/decrease is an independent wallet adjustment. It
            # must not be treated as the latest formula result on a later
            # commission sync, otherwise sync would silently cancel it.
            if entry.entry_type not in {"MANUAL_CREDIT", "MANUAL_DECREASE", "MANUAL_CREDIT_REVERSAL", "MANUAL_DECREASE_REVERSAL"}:
                data["calculation_earned"] += entry.amount
            if entry.entry_type == "MANUAL_CREDIT":
                data["manual_credit"] += entry.amount
            elif entry.entry_type == "MANUAL_DECREASE":
                data["manual_decrease"] += abs(entry.amount)
            elif entry.entry_type == "MANUAL_CREDIT_REVERSAL":
                data["manual_credit"] += entry.amount
            elif entry.entry_type == "MANUAL_DECREASE_REVERSAL":
                data["manual_decrease"] -= entry.amount
        if entry.entry_type in _PAYMENT_HELD_TYPES:
            data["payment_held"] += entry.amount
        elif entry.entry_type in _MANUAL_HOLD_TYPES:
            data["manual_held"] += entry.amount
        elif entry.entry_type == "MANUAL_HOLD_REVERSAL":
            data["manual_held"] += entry.amount
        elif entry.entry_type == "RELEASED":
            data["released"] += entry.amount
        elif entry.entry_type == "MANUAL_RELEASE":
            data["manual_released"] += entry.amount
        elif entry.entry_type == "MANUAL_RELEASE_REVERSAL":
            data["manual_released"] += entry.amount
        elif entry.entry_type == "PAID":
            data["paid"] += entry.amount
        elif entry.entry_type in {"SCHEDULED", "SCHEDULE_RELEASE", "PAYMENT_RELEASE_ALLOCATION", "PAYMENT_RELEASE_REVERSAL"}:
            data["scheduled"] += entry.amount
        elif entry.entry_type == "TRANSFER_OUT":
            data["transferred_out"] += abs(entry.amount)
        elif entry.entry_type == "TRANSFER_OUT_REVERSAL":
            data["transferred_out"] -= abs(entry.amount)
        elif entry.entry_type == "TRANSFER_IN":
            data["transferred_in"] += entry.amount
        elif entry.entry_type == "TRANSFER_IN_REVERSAL":
            data["transferred_in"] += entry.amount
    for data in positions.values():
        data["payment_held"] = max(0.0, round(data["payment_held"] - data["released"], 2))
        data["manual_held"] = max(0.0, round(data["manual_held"] - data["manual_released"], 2))
        data["held"] = round(data["payment_held"] + data["manual_held"], 2)
        data["scheduled"] = max(0.0, round(data["scheduled"], 2))
        data["transferred"] = max(0.0, round(data["transferred_in"], 2))
        data["manual_credit"] = round(data["manual_credit"], 2)
        data["manual_decrease"] = round(data["manual_decrease"], 2)
        # "Khả dụng" is the temporary bonus wallet. Automatic hold identifies
        # the bonus that has been retained and may be moved/scheduled later;
        # it is therefore the wallet's source, not a deduction from earned.
        # Manual holds still lock money operationally.
        data["available"] = round(max(0.0,
            data["payment_held"]
            + data["manual_credit"]
            - data["manual_decrease"]
            - data["manual_held"]
            - data["scheduled"]
            - data["paid"]
            - data["transferred_out"]),
            2,
        )
        data["recoverable"] = max(0.0, round(-data["available"], 2))
        data["earned"] = round(data["earned"], 2)
        data["calculation_earned"] = round(data["calculation_earned"], 2)
        data["paid"] = round(data["paid"], 2)
    return positions


def _period_wallet_allocations(period: CommissionPeriod, db: Session) -> list[tuple[CommissionJob | None, str, float, bool]]:
    """Use get_period_detail so the existing commission formula and overrides stay unchanged."""
    detail = get_period_detail(period.id, db)
    quarter_bonus_by_rep = {row.sales_rep: round(float(row.total_bonus_quarter or 0.0), 2) for row in detail.sales_rep_summary}
    jobs_by_rep: dict[str, list[CommissionJob]] = {}
    for job in period.jobs:
        jobs_by_rep.setdefault(job.sales_rep or "(Unknown)", []).append(job)

    allocations: list[tuple[CommissionJob | None, str, float, bool]] = []
    for sales_rep, jobs in jobs_by_rep.items():
        quarter_bonus = quarter_bonus_by_rep.get(sales_rep, 0.0)
        if abs(quarter_bonus) < 0.005:
            continue
        weighted_jobs = [job for job in jobs if float(job.profit_loss or 0.0) > 0]
        total_weight = sum(float(job.profit_loss or 0.0) for job in weighted_jobs)
        if total_weight <= 0:
            # An override can create a bonus even when there is no positive P/L.
            # Keep it as a period adjustment and lock it until every JOB is paid.
            allocations.append((None, sales_rep, quarter_bonus, all(_is_payment_received(job.payment_received) for job in jobs)))
            continue
        allocated = 0.0
        for index, job in enumerate(weighted_jobs):
            amount = round(quarter_bonus - allocated, 2) if index == len(weighted_jobs) - 1 else round(quarter_bonus * float(job.profit_loss or 0.0) / total_weight, 2)
            allocated += amount
            allocations.append((job, sales_rep, amount, _is_payment_received(job.payment_received)))
    return allocations


def _period_wallet_hold_targets(period: CommissionPeriod, db: Session) -> dict[int, float]:
    """Allocate only the temporarily-held bonus across the period's JOBs."""
    from app.services.commission_wallet_rules import calculate_company_bonus_wallet, calculate_job_hold

    detail = get_period_detail(period.id, db)
    summary_by_rep = {row.sales_rep: row for row in detail.sales_rep_summary}
    allocations = _period_wallet_allocations(period, db)
    totals_by_rep: dict[str, float] = {}
    for _job, sales_rep, amount, _paid in allocations:
        totals_by_rep[sales_rep] = round(totals_by_rep.get(sales_rep, 0.0) + amount, 2)

    temporary_by_rep: dict[str, float] = {}
    for sales_rep, summary in summary_by_rep.items():
        policy_hold = sum(
            calculate_job_hold(
                profit_loss=job.profit_loss,
                balance_amount=job.balance_amount,
                payment_received_amount=job.payment_received_amount,
            )[1]
            for job in period.jobs
            if (job.sales_rep or "(Unknown)") == sales_rep
        )
        rule = calculate_company_bonus_wallet(
            total_profit_loss=summary.total_profit_loss,
            total_bonus_quarter=summary.total_bonus_quarter,
            monthly_bonus=summary.sales_bonus,
            policy_hold_amount=policy_hold,
        )
        temporary_by_rep[sales_rep] = float(rule["temporary_bonus_available"])

    targets: dict[int, float] = {}
    allocated_by_rep: dict[str, float] = {}
    jobs_per_rep: dict[str, list[tuple[CommissionJob, float]]] = {}
    for job, sales_rep, amount, _paid in allocations:
        if job is not None and calculate_job_hold(
            profit_loss=job.profit_loss,
            balance_amount=job.balance_amount,
            payment_received_amount=job.payment_received_amount,
        )[1] > 0:
            jobs_per_rep.setdefault(sales_rep, []).append((job, amount))
    for sales_rep, job_allocations in jobs_per_rep.items():
        total_bonus = totals_by_rep.get(sales_rep, 0.0)
        temporary_total = min(total_bonus, temporary_by_rep.get(sales_rep, 0.0))
        eligible_bonus = sum(amount for _job, amount in job_allocations)
        for index, (job, amount) in enumerate(job_allocations):
            target = (
                round(temporary_total - allocated_by_rep.get(sales_rep, 0.0), 2)
                if index == len(job_allocations) - 1
                else round(temporary_total * amount / eligible_bonus, 2) if eligible_bonus > 0 else 0.0
            )
            allocated_by_rep[sales_rep] = round(allocated_by_rep.get(sales_rep, 0.0) + target, 2)
            targets[job.id] = max(0.0, target)
    return targets


def _employee_id_for_sales_rep(sales_rep: str, db: Session) -> Optional[int]:
    from app.models.employee import Employee
    from app.services.salary import clean_name_for_match
    clean_rep = clean_name_for_match(sales_rep)
    for employee in db.query(Employee).all():
        if clean_name_for_match(employee.full_name) == clean_rep:
            return employee.id
    return None


def _bonus_lock_for(db: Session, period_id: int, sales_rep: str) -> Optional[CommissionBonusLock]:
    return db.query(CommissionBonusLock).filter(
        CommissionBonusLock.period_id == period_id,
        CommissionBonusLock.sales_rep == sales_rep,
    ).first()


def _ensure_bonus_editable(db: Session, period_id: int, sales_rep: str) -> None:
    """Protect a closed source table at the API boundary, not only in the UI."""
    lock = _bonus_lock_for(db, period_id, sales_rep)
    if lock:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Bảng bonus của {sales_rep} trong kỳ nguồn #{period_id} đã bị khóa"
                f" từ {lock.locked_at.isoformat() if lock.locked_at else 'trước đó'}"
                ". Không thể chỉnh sửa JOB, số dư, lịch chi trả hoặc hoàn tác."
            ),
        )


def _locked_source_periods_for_positions(
    db: Session,
    sales_rep: str,
    positions: dict[tuple[str, Optional[int]], dict],
) -> list[int]:
    """Return source periods with an available balance that would be changed."""
    period_ids: set[int] = set()
    for (rep, _job_id), position in positions.items():
        if rep != sales_rep or abs(float(position.get("available", 0.0))) < 0.01:
            continue
        source = position.get("entries", [None])[0]
        if source and _bonus_lock_for(db, source.period_id, sales_rep):
            period_ids.add(source.period_id)
    return sorted(period_ids)


@router.post("/wallet/sync")
def sync_commission_wallet(
    payload: CommissionWalletSyncIn,
    db: Session = Depends(get_db),
    current_user=Depends(get_admin_user),
):
    periods_query = db.query(CommissionPeriod).filter(CommissionPeriod.is_voided.is_(False))
    if payload.period_id is not None:
        periods_query = periods_query.filter(CommissionPeriod.id == payload.period_id)
    periods = periods_query.all()
    if not periods:
        raise HTTPException(status_code=404, detail="Không tìm thấy kỳ commission để đồng bộ ví thưởng.")

    created = 0
    released = 0
    skipped_locked: set[str] = set()
    # A sync recalculates only source entitlement. It must not create a
    # release without the administrator's selected future payroll allocation.
    release_on_sync = False
    for period in periods:
        current_entries = db.query(CommissionWalletLedger).filter(CommissionWalletLedger.period_id == period.id).all()
        positions = _wallet_positions(current_entries)
        detail = get_period_detail(period.id, db)
        summary_by_rep = {item.sales_rep: item for item in detail.sales_rep_summary}
        wallet_hold_targets = _period_wallet_hold_targets(period, db)
        snapshots: dict[str, CommissionCalculationSnapshot] = {}
        fixed_hold_job_ids: set[int] = set()
        for job, sales_rep, desired_amount, _payment_received in _period_wallet_allocations(period, db):
            if _bonus_lock_for(db, period.id, sales_rep):
                skipped_locked.add(f"{period.id}:{sales_rep}")
                continue
            job_id = job.id if job else None
            key = (sales_rep, job_id)
            position = positions.get(key)
            current_earned = position["calculation_earned"] if position else 0.0
            delta = round(desired_amount - current_earned, 2)
            employee_id = _employee_id_for_sales_rep(sales_rep, db)
            if sales_rep not in snapshots:
                summary = summary_by_rep.get(sales_rep)
                snapshots[sales_rep] = CommissionCalculationSnapshot(
                    period_id=period.id, sales_rep=sales_rep, employee_id=employee_id,
                    monthly_bonus=float(summary.sales_bonus if summary else 0.0),
                    total_bonus_quarter=float(summary.total_bonus_quarter if summary else 0.0),
                    source_payload=json.dumps({"formula": "existing_commission_formula", "payment_allocation": "positive_profit_loss_ratio"}),
                )
                db.add(snapshots[sales_rep])
                db.flush()
            entitlement = db.query(CommissionBonusEntitlement).filter(
                CommissionBonusEntitlement.period_id == period.id,
                CommissionBonusEntitlement.sales_rep == sales_rep,
                CommissionBonusEntitlement.job_id.is_(job_id) if job_id is None else CommissionBonusEntitlement.job_id == job_id,
                CommissionBonusEntitlement.status == "ACTIVE",
            ).first()
            if not entitlement:
                entitlement = CommissionBonusEntitlement(
                    snapshot_id=snapshots[sales_rep].id, period_id=period.id, job_id=job_id,
                    sales_rep=sales_rep, employee_id=employee_id, calculated_amount=desired_amount,
                    source_period=period.period_label,
                )
                db.add(entitlement)
                db.flush()
            if abs(delta) >= 0.01:
                # Earned bonus and the Profit/Loss-based hold are separate
                # ledger facts. Accrue first, then reconcile the JOB hold.
                event_type = "ACCRUAL_AVAILABLE" if position is None else "ADJUSTMENT_AVAILABLE"
                db.add(CommissionWalletLedger(
                    period_id=period.id, job_id=job_id, entitlement_id=entitlement.id, sales_rep=sales_rep, employee_id=employee_id,
                    entry_type=event_type, amount=delta,
                    note=f"Phân bổ commission kỳ {period.period_label} theo tỷ trọng Profit/Loss dương.", reason_code="CALCULATION",
                ))
                created += 1
            db.flush()
            if job is not None:
                hold_delta = _apply_fixed_job_hold(
                    db,
                    job,
                    reason_code="FIXED_HOLD_BONUS_30",
                    note=f"Hold cố định 30% Profit/Loss dương của JOB {job.job_no}.",
                    wallet_hold_amount=wallet_hold_targets.get(job.id, 0.0),
                )
                fixed_hold_job_ids.add(job.id)
                if abs(hold_delta) >= 0.01:
                    created += 1
        # Zero/negative-P&L JOBs may receive no formula allocation, but their
        # percentage column still follows the same fixed policy. Their hold is
        # zero because only positive JOB Profit/Loss contributes to the hold.
        db.flush()
        for job in period.jobs:
            if job.id in fixed_hold_job_ids or _bonus_lock_for(db, period.id, job.sales_rep or "(Unknown)"):
                continue
            hold_delta = _apply_fixed_job_hold(
                db,
                job,
                reason_code="FIXED_HOLD_BONUS_30",
                note=f"Hold cố định 30% Profit/Loss dương của JOB {job.job_no}.",
                wallet_hold_amount=wallet_hold_targets.get(job.id, 0.0),
            )
            if abs(hold_delta) >= 0.01:
                created += 1
    # Final reconciliation: a paid JOB may have several historical HOLD rows
    # (for example after a formula adjustment). Never leave a rounding residue
    # in automatic hold once its Payment Received status is YES.
    db.flush()
    for period in periods:
        for job in period.jobs:
            if not release_on_sync or not _is_payment_received(job.payment_received):
                continue
            if _bonus_lock_for(db, period.id, job.sales_rep or "(Unknown)"):
                continue
            job_entries = db.query(CommissionWalletLedger).filter(
                CommissionWalletLedger.period_id == period.id,
                CommissionWalletLedger.job_id == job.id,
                CommissionWalletLedger.sales_rep == (job.sales_rep or "(Unknown)"),
            ).order_by(CommissionWalletLedger.id).all()
            if not job_entries:
                continue
            position = _wallet_positions(job_entries).get((job.sales_rep or "(Unknown)", job.id), {})
            remaining_payment_hold = round(float(position.get("payment_held", 0.0)), 2)
            if remaining_payment_hold >= 0.005:
                source = job_entries[0]
                db.add(CommissionWalletLedger(
                    period_id=source.period_id, job_id=source.job_id, entitlement_id=source.entitlement_id,
                    sales_rep=source.sales_rep, employee_id=source.employee_id,
                    entry_type="RELEASED", amount=remaining_payment_hold, reason_code="PAYMENT_RECEIVED_RECONCILE",
                    note="Payment Received là YES; đối soát mở toàn bộ phần giữ tự động còn lại.",
                ))
                released += 1
    db.commit()
    return {
        "message": "Đã đồng bộ ví thưởng.",
        "entries_created": created,
        "entries_released": released,
        "locked_scopes_skipped": sorted(skipped_locked),
    }


@router.get("/wallet")
def get_commission_wallet(
    sales_rep: Optional[str] = None,
    period_id: Optional[int] = None,
    db: Session = Depends(get_db),
):
    query = db.query(CommissionWalletLedger)
    if sales_rep:
        query = query.filter(CommissionWalletLedger.sales_rep == sales_rep)
    if period_id is not None:
        query = query.filter(CommissionWalletLedger.period_id == period_id)
    entries = query.order_by(CommissionWalletLedger.created_at.asc(), CommissionWalletLedger.id.asc()).all()
    positions = _wallet_positions(entries)
    # A wallet row is a source-commission scope, not a lifetime total of one
    # Sales Rep.  This keeps different employees and different source periods
    # auditable down to their individual JOBs.
    summary: dict[tuple[str, int], dict] = {}
    for (rep, _job_id), data in positions.items():
        source_period_id = data["entries"][0].period_id
        item = summary.setdefault((rep, source_period_id), {"sales_rep": rep, "period_id": source_period_id, "total_earned": 0.0, "manual_credit_amount": 0.0, "manual_decrease_amount": 0.0, "held_amount": 0.0, "scheduled_amount": 0.0, "transferred_amount": 0.0, "available_amount": 0.0, "paid_amount": 0.0, "recoverable_amount": 0.0, "jobs": []})
        item["total_earned"] += data["earned"]
        item["manual_credit_amount"] += data["manual_credit"]
        item["manual_decrease_amount"] += data["manual_decrease"]
        item["held_amount"] += data["held"]
        item["scheduled_amount"] += data["scheduled"]
        item["transferred_amount"] += data["transferred"]
        item["available_amount"] += data["available"]
        item["paid_amount"] += data["paid"]
        item["recoverable_amount"] += data["recoverable"]
        job = db.get(CommissionJob, _job_id) if _job_id else None
        item["jobs"].append({"job_id": _job_id, "job_no": job.job_no if job else "Điều chỉnh kỳ", "earned": data["earned"], "held": data["held"], "scheduled": data["scheduled"], "available": data["available"], "paid": data["paid"]})
    for (rep, scoped_period_id), item in summary.items():
        for job_item in item["jobs"]:
            job_position = positions[(rep, job_item["job_id"])]
            job_item["payment_held"] = job_position["payment_held"]
            job_item["manual_held"] = job_position["manual_held"]
            source_entry = job_position["entries"][0]
            source_period = db.get(CommissionPeriod, source_entry.period_id)
            job_item["period_id"] = source_entry.period_id
            job_item["period_label"] = source_period.period_label if source_period else f"Kỳ #{source_entry.period_id}"
        item["period_labels"] = sorted({job_item["period_label"] for job_item in item["jobs"]})

        # Wallet balances are monthly.  Keep the quarter total shown here in
        # sync with the import-history summary without recalculating or
        # changing the commission formula.
        period_summaries = []
        for period_id in [scoped_period_id]:
            period_record = db.get(CommissionPeriod, period_id)
            detail = get_period_detail(period_id, db)
            rep_summary = next((row for row in detail.sales_rep_summary if row.sales_rep == rep), None)
            if rep_summary:
                from app.services.commission_wallet_rules import calculate_company_bonus_wallet
                # “Đang giữ” is the saved 30%-of-Profit/Loss amount on JOB rows,
                # not the legacy full wallet lock that existed while Payment
                # Received was still NO.  This keeps history and JOB detail on
                # one auditable source of truth.
                period_rep_jobs = db.query(CommissionJob).filter(
                    CommissionJob.period_id == period_id,
                    CommissionJob.sales_rep == rep,
                ).all()
                current_source_hold = round(sum(
                    max(0.0, float(job.hold_bonus_amount or 0.0))
                    for job in period_rep_jobs
                ), 2)
                base_policy_hold = round(sum(
                    _job_policy_hold_for_monthly_base(job)
                    for job in period_rep_jobs
                ), 2)
                # Payment Received remains an audit field for receivables and
                # payout eligibility. It must never become an input to the
                # commission formula shown as "Tổng thưởng".
                payment_received_total = round(float(db.query(
                    func.coalesce(func.sum(CommissionJob.payment_received_amount), 0.0)
                ).filter(
                    CommissionJob.period_id == period_id,
                    CommissionJob.sales_rep == rep,
                    func.upper(func.coalesce(CommissionJob.payment_received, "NO")) == "YES",
                    CommissionJob.payment_received_amount > 0,
                ).scalar() or 0.0), 2)
                quarter_total = round(float(rep_summary.total_bonus_quarter or 0.0), 2)
                formula_coefficient = round(float(rep_summary.bonus_rate or 0.0), 4)
                formula_monthly_bonus = round(float(rep_summary.sales_bonus or 0.0), 2)
                wallet_rule = calculate_company_bonus_wallet(
                    total_profit_loss=rep_summary.total_profit_loss,
                    total_bonus_quarter=quarter_total,
                    monthly_bonus=formula_monthly_bonus,
                    policy_hold_amount=base_policy_hold,
                )
                payout_periods = _source_payout_periods(period_record) if period_record else []

                # The base bonus always remains split equally over the three
                # normal payout months. A manual NO -> YES correction divides
                # the released JOB hold only among selected remaining months;
                # every unselected base amount must remain unchanged.
                manual_release_entries = db.query(CommissionWalletLedger).join(
                    CommissionPayoutSchedule,
                    CommissionPayoutSchedule.id == CommissionWalletLedger.schedule_id,
                ).filter(
                    CommissionWalletLedger.period_id == period_id,
                    CommissionWalletLedger.sales_rep == rep,
                    CommissionWalletLedger.reason_code.in_([
                        "MANUAL_PAYMENT_SPLIT",
                        "MANUAL_PAYMENT_MONTH_RELEASE",
                        "MANUAL_PAYMENT_SELECTED_MONTHS",
                    ]),
                    CommissionPayoutSchedule.status.in_(["SCHEDULED", "PAID"]),
                ).all()
                if manual_release_entries and period_record:
                    payout_periods = _next_commission_payout_periods(period_record)
                    split_amount_by_month: dict[str, float] = {}
                    base_monthly_amount = round(float(wallet_rule["monthly_payout"]), 2)
                    for entry in manual_release_entries:
                        if not entry.payout_period:
                            continue
                        split_amount_by_month[entry.payout_period] = round(
                            split_amount_by_month.get(entry.payout_period, 0.0)
                            + float(entry.amount or 0.0),
                            2,
                        )
                    monthly_available_amounts = [
                        {
                            "payout_period": payout_period,
                            "base_amount": base_monthly_amount,
                            "released_amount": round(split_amount_by_month.get(payout_period, 0.0), 2),
                            "amount": round(
                                base_monthly_amount
                                + split_amount_by_month.get(payout_period, 0.0),
                                2,
                            ),
                        }
                        for payout_period in payout_periods
                    ]
                else:
                    monthly_available_amounts = [
                        {
                            "payout_period": payout_period,
                            "base_amount": round(float(wallet_rule["monthly_payout"]), 2),
                            "released_amount": 0.0,
                            "amount": round(float(wallet_rule["monthly_payout"]), 2),
                        }
                        for payout_period in payout_periods
                    ]
                period_summaries.append({
                    "period_id": period_id,
                    "period_label": detail.period_label,
                    "payout_periods": payout_periods,
                    "total_profit_loss": float(rep_summary.total_profit_loss or 0.0),
                    "total_bonus_quarter": quarter_total,
                    "formula_total_bonus_quarter": quarter_total,
                    "formula_effective_coefficient": formula_coefficient,
                    "formula_monthly_bonus": formula_monthly_bonus,
                    "payment_received_total": payment_received_total,
                    "gross_total_bonus_quarter": quarter_total,
                    # Backwards-compatible keys now mirror the formula result;
                    # consumers must not substitute Payment Received for bonus.
                    "hold_adjusted_total_bonus": quarter_total,
                    "cash_basis_coefficient": formula_coefficient,
                    "cash_basis_monthly_bonus": formula_monthly_bonus,
                    "monthly_bonus": float(rep_summary.sales_bonus or 0.0),
                    "policy_hold_amount": current_source_hold,
                    "quarter_hold_amount": float(wallet_rule["company_held_profit"]),
                    "holds_entire_profit": bool(wallet_rule["holds_entire_profit"]),
                    "monthly_payout": float(wallet_rule["monthly_payout"]),
                    "temporary_bonus_opening": float(wallet_rule["temporary_bonus_available"]),
                    "temporary_bonus_available": max(0.0, round(float(item["available_amount"]), 2)),
                    "monthly_available_amounts": monthly_available_amounts,
                })
        item["period_summaries"] = period_summaries
        item["total_bonus_quarter"] = round(sum(row["total_bonus_quarter"] for row in period_summaries), 2)
        policy = db.query(CommissionPayoutPolicy).filter(CommissionPayoutPolicy.sales_rep == rep).first()
        item.update({key: round(value, 2) for key, value in item.items() if key in {"total_earned", "manual_credit_amount", "manual_decrease_amount", "held_amount", "scheduled_amount", "transferred_amount", "available_amount", "paid_amount", "recoverable_amount"}})
        item["policy"] = {"payout_mode": policy.payout_mode, "minimum_amount": policy.minimum_amount, "is_active": policy.is_active} if policy else {"payout_mode": "MANUAL", "minimum_amount": 0.0, "is_active": True}
    return list(summary.values())


@router.get("/wallet/lock")
def get_commission_bonus_lock(
    sales_rep: str,
    period_id: int,
    db: Session = Depends(get_db),
):
    lock = _bonus_lock_for(db, period_id, sales_rep)
    return {
        "locked": bool(lock),
        "period_id": period_id,
        "sales_rep": sales_rep,
        "reason": lock.reason if lock else None,
        "locked_by": lock.locked_by if lock else None,
        "locked_at": lock.locked_at.isoformat() if lock and lock.locked_at else None,
    }


@router.post("/wallet/lock")
def lock_commission_bonus_table(
    payload: CommissionBonusLockIn,
    db: Session = Depends(get_db),
    current_user=Depends(get_admin_user),
):
    period = db.get(CommissionPeriod, payload.period_id)
    if not period:
        raise HTTPException(status_code=404, detail="Không tìm thấy kỳ commission cần khóa.")
    if not db.query(CommissionJob).filter(
        CommissionJob.period_id == payload.period_id,
        CommissionJob.sales_rep == payload.sales_rep,
    ).first():
        raise HTTPException(status_code=404, detail="Không tìm thấy JOB của nhân viên trong kỳ commission đã chọn.")
    existing = _bonus_lock_for(db, payload.period_id, payload.sales_rep)
    if existing:
        return {
            "message": "Bảng bonus đã được khóa trước đó.",
            "locked": True,
            "locked_at": existing.locked_at.isoformat() if existing.locked_at else None,
        }
    actor = current_user.username if hasattr(current_user, "username") else str(current_user.id)
    db.add(CommissionBonusLock(
        period_id=payload.period_id,
        sales_rep=payload.sales_rep,
        reason=payload.reason.strip() if payload.reason and payload.reason.strip() else None,
        locked_by=actor,
    ))
    db.commit()
    return {"message": "Đã khóa bảng bonus. Mọi chỉnh sửa JOB và ví thưởng của kỳ này sẽ bị chặn.", "locked": True}


@router.get("/wallet/ledger")
def get_commission_wallet_ledger(
    sales_rep: Optional[str] = None,
    period_id: Optional[int] = None,
    limit: int = 300,
    db: Session = Depends(get_db),
):
    query = db.query(CommissionWalletLedger)
    if sales_rep:
        query = query.filter(CommissionWalletLedger.sales_rep == sales_rep)
    if period_id is not None:
        query = query.filter(CommissionWalletLedger.period_id == period_id)
    all_entries = query.order_by(CommissionWalletLedger.id.asc()).all()
    positions = _wallet_positions(all_entries)
    entries = list(reversed(all_entries))[:min(max(limit, 1), 1000)]
    jobs_by_id = {
        job.id: job for job in db.query(CommissionJob).filter(
            CommissionJob.id.in_({entry.job_id for entry in entries if entry.job_id is not None})
        ).all()
    } if entries else {}
    return [{
        "id": entry.id, "sales_rep": entry.sales_rep, "period_id": entry.period_id,
        "job_id": entry.job_id,
        "job_no": jobs_by_id[entry.job_id].job_no if entry.job_id in jobs_by_id else None,
        "job_customer": jobs_by_id[entry.job_id].customer if entry.job_id in jobs_by_id else None,
        "job_display_name": (
            f"{jobs_by_id[entry.job_id].job_no} · {jobs_by_id[entry.job_id].customer}"
            if entry.job_id in jobs_by_id and jobs_by_id[entry.job_id].customer
            else (jobs_by_id[entry.job_id].job_no if entry.job_id in jobs_by_id else None)
        ),
        "current_held_amount": positions.get((entry.sales_rep, entry.job_id), {}).get("held", 0.0),
        "current_payment_held_amount": positions.get((entry.sales_rep, entry.job_id), {}).get("payment_held", 0.0),
        "current_manual_held_amount": positions.get((entry.sales_rep, entry.job_id), {}).get("manual_held", 0.0),
        "entry_type": entry.entry_type, "amount": entry.amount, "payout_period": entry.payout_period,
        "schedule_id": entry.schedule_id, "reason_code": entry.reason_code, "note": entry.note,
        "created_by": entry.created_by, "created_at": entry.created_at.isoformat() if entry.created_at else None,
    } for entry in entries]


@router.get("/wallet/jobs")
def get_commission_wallet_jobs(
    sales_rep: Optional[str] = None,
    period_id: Optional[int] = None,
    db: Session = Depends(get_db),
):
    """Full JOB detail for the bonus-hold screen; calculation values remain ledger-derived."""
    entry_query = db.query(CommissionWalletLedger)
    if sales_rep:
        entry_query = entry_query.filter(CommissionWalletLedger.sales_rep == sales_rep)
    if period_id is not None:
        entry_query = entry_query.filter(CommissionWalletLedger.period_id == period_id)
    entries = entry_query.order_by(CommissionWalletLedger.created_at.asc(), CommissionWalletLedger.id.asc()).all()
    positions = _wallet_positions(entries)
    jobs_query = db.query(CommissionJob).join(CommissionPeriod).filter(
        CommissionPeriod.is_voided.is_(False),
    )
    if sales_rep:
        jobs_query = jobs_query.filter(CommissionJob.sales_rep == sales_rep)
    if period_id is not None:
        jobs_query = jobs_query.filter(CommissionJob.period_id == period_id)
    jobs = jobs_query.order_by(CommissionPeriod.from_date.asc(), CommissionJob.id.asc()).all()
    verification_by_job = {
        item.job_id: item for item in db.query(CommissionPaymentVerification).filter(
            CommissionPaymentVerification.job_id.in_([job.id for job in jobs]) if jobs else False
        ).all()
    }
    # The payment command note belongs to its immutable payout schedules.  Put
    # it back on the JOB read model so the accounting screen can show exactly
    # what was recorded after a command has been created.
    command_note_by_verification = {}
    verification_ids = [item.id for item in verification_by_job.values()]
    if verification_ids:
        command_schedules = db.query(CommissionPayoutSchedule).filter(
            CommissionPayoutSchedule.payment_verification_id.in_(verification_ids),
        ).order_by(CommissionPayoutSchedule.id.desc()).all()
        for schedule in command_schedules:
            if schedule.payment_verification_id not in command_note_by_verification and schedule.note:
                command_note_by_verification[schedule.payment_verification_id] = schedule.note
    period_summaries = {}
    for source_period_id in {job.period_id for job in jobs}:
        detail = get_period_detail(source_period_id, db)
        for rep_summary in detail.sales_rep_summary:
            period_summaries[(source_period_id, rep_summary.sales_rep)] = {
                "profit_loss": float(rep_summary.total_profit_loss or 0.0),
                "target": float(rep_summary.target or 0.0),
                "coefficient": float(rep_summary.coefficient or 0.0),
                "total_bonus_quarter": float(rep_summary.total_bonus_quarter or 0.0),
                "monthly_bonus": float(rep_summary.sales_bonus or 0.0),
            }
    result = []
    for job in jobs:
        verification = verification_by_job.get(job.id)
        visible_verification = verification if verification and verification.status != "CANCELLED" else None
        job_sales_rep = job.sales_rep or "(Unknown)"
        position = positions.get((job_sales_rep, job.id), {})
        period = job.period
        period_summary = period_summaries.get((job.period_id, job_sales_rep), {})
        result.append({
            "id": job.id,
            "periodId": job.period_id,
            "customerPaymentPeriods": _source_payout_periods(period) if period else [],
            "nextReleasePayoutPeriods": _next_commission_payout_periods(period) if period else [],
            "periodLabel": period.period_label if period else f"Kỳ #{job.period_id}",
            "periodProfitLoss": period_summary.get("profit_loss", 0.0),
            "periodTarget": period_summary.get("target", 0.0),
            "periodCoefficient": period_summary.get("coefficient", 0.0),
            "periodTotalBonusQuarter": period_summary.get("total_bonus_quarter", 0.0),
            "periodMonthlyBonus": period_summary.get("monthly_bonus", 0.0),
            "jobNo": job.job_no,
            "jobDate": job.job_date.strftime("%d/%m/%Y") if job.job_date else None,
            "hbl": job.hbl,
            "mbl": job.mbl,
            "customer": job.customer,
            "vendor": job.vendor,
            "salesRep": job.sales_rep,
            "shipper": job.shipper,
            "consignee": job.consignee,
            "subType": job.sub_type,
            "containerString": job.container_string,
            "wt": job.wt,
            "vol": job.vol,
            "carrierBookingNo": job.carrier_booking_no,
            "por": job.por,
            "finalDestination": job.final_destination,
            "realizedRevenue": job.realized_revenue,
            "unrealizedRevenue": job.unrealized_revenue,
            "realizedCost": job.realized_cost,
            "unrealizedCost": job.unrealized_cost,
            "profitLoss": job.profit_loss,
            "containerPicked": job.container_picked,
            "paymentReceived": job.payment_received,
            "receivableAmount": job.receivable_amount,
            "balanceAmount": job.balance_amount,
            "paymentReceivedAmount": job.payment_received_amount,
            "holdBonusPercent": job.hold_bonus_percent,
            "holdBonusAmount": job.hold_bonus_amount,
            "remark": job.bonus_remark,
            "heldReleaseMode": job.held_release_mode or "NEXT_QUARTER_LUMP",
            "heldReleasePayoutPeriod": job.held_release_payout_period,
            "paymentVerificationId": visible_verification.id if visible_verification else None,
            "paymentVerificationStatus": visible_verification.status if visible_verification else None,
            "paymentReportNote": visible_verification.report_note if visible_verification else None,
            "paymentVerificationNote": visible_verification.verification_note if visible_verification else None,
            "paymentCommandNote": command_note_by_verification.get(visible_verification.id) if visible_verification else None,
            "paymentReportedAt": visible_verification.reported_at.isoformat() if visible_verification and visible_verification.reported_at else None,
            "earned": position.get("earned", 0.0),
            "calculationEarned": position.get("calculation_earned", 0.0),
            "manualCredit": position.get("manual_credit", 0.0),
            "manualDecrease": position.get("manual_decrease", 0.0),
            "paymentHeld": position.get("payment_held", 0.0),
            "manualHeld": position.get("manual_held", 0.0),
            "held": position.get("held", 0.0),
            "scheduled": position.get("scheduled", 0.0),
            "transferred": position.get("transferred", 0.0),
            "available": position.get("available", 0.0),
            "paid": position.get("paid", 0.0),
            "hasWalletEntry": bool(position),
        })
    return result


@router.put("/periods/{period_id}/jobs/{job_id}/release-plan")
def update_commission_job_release_plan(
    period_id: int,
    job_id: int,
    payload: CommissionJobReleasePlanIn,
    db: Session = Depends(get_db),
):
    """Save the accountant's release plan before the customer payment arrives."""
    job = db.query(CommissionJob).filter(
        CommissionJob.id == job_id,
        CommissionJob.period_id == period_id,
    ).first()
    if not job:
        raise HTTPException(status_code=404, detail="Không tìm thấy JOB trong kỳ commission.")
    _ensure_bonus_editable(db, period_id, job.sales_rep or "(Unknown)")
    period = db.get(CommissionPeriod, period_id)
    target_months = _next_commission_payout_periods(period) if period else []
    if not target_months:
        raise HTTPException(status_code=422, detail="Kỳ nguồn chưa đủ dữ liệu để xác định ba tháng trả kế tiếp.")
    if payload.release_payout_period not in target_months:
        raise HTTPException(status_code=422, detail="Tháng trả một lần phải thuộc ba tháng của kỳ kế tiếp.")
    job.held_release_payout_period = payload.release_payout_period
    job.held_release_mode = "NEXT_QUARTER_LUMP"
    db.commit()
    return {
        "message": "Đã lưu hình thức chi trả cho số bonus đang giữ của JOB.",
        "release_mode": job.held_release_mode,
        "release_payout_period": job.held_release_payout_period,
    }


@router.put("/wallet/policy/{sales_rep}")
def upsert_commission_payout_policy(sales_rep: str, payload: CommissionPayoutPolicyIn, db: Session = Depends(get_db)):
    allowed_modes = {"MANUAL", "NEXT_PAYROLL", "THRESHOLD"}
    if payload.payout_mode not in allowed_modes or payload.minimum_amount < 0:
        raise HTTPException(status_code=422, detail="Quy tắc chi trả không hợp lệ.")
    policy = db.query(CommissionPayoutPolicy).filter(CommissionPayoutPolicy.sales_rep == sales_rep).first()
    if not policy:
        policy = CommissionPayoutPolicy(sales_rep=sales_rep, employee_id=_employee_id_for_sales_rep(sales_rep, db))
        db.add(policy)
    policy.payout_mode = payload.payout_mode
    policy.minimum_amount = payload.minimum_amount
    policy.is_active = payload.is_active
    db.commit()
    return {"message": "Đã lưu quy tắc chi trả."}


@router.post("/wallet/payout")
def payout_commission_wallet(payload: CommissionPayoutIn, db: Session = Depends(get_db)):
    entries_query = db.query(CommissionWalletLedger).filter(CommissionWalletLedger.sales_rep == payload.sales_rep)
    if payload.source_period_id is not None:
        entries_query = entries_query.filter(CommissionWalletLedger.period_id == payload.source_period_id)
    entries = entries_query.order_by(CommissionWalletLedger.created_at, CommissionWalletLedger.id).all()
    positions = _wallet_positions(entries)
    locked_periods = _locked_source_periods_for_positions(db, payload.sales_rep, positions)
    if locked_periods:
        raise HTTPException(status_code=409, detail=f"Không thể chi trả: bảng bonus nguồn đã khóa ở kỳ {locked_periods}.")
    available = round(sum(data["available"] for (rep, _), data in positions.items() if rep == payload.sales_rep), 2)
    amount = round(payload.amount if payload.amount is not None else available, 2)
    if amount <= 0 or amount > available + 0.01:
        raise HTTPException(status_code=422, detail="Số tiền chi trả phải lớn hơn 0 và không vượt số dư khả dụng.")
    policy = db.query(CommissionPayoutPolicy).filter(CommissionPayoutPolicy.sales_rep == payload.sales_rep).first()
    if policy and policy.payout_mode == "THRESHOLD" and amount < policy.minimum_amount:
        raise HTTPException(status_code=422, detail="Chưa đạt ngưỡng chi trả đã cấu hình.")
    remaining = amount
    batch = str(uuid4())
    for (rep, job_id), data in sorted(positions.items(), key=lambda item: min((entry.id for entry in item[1]["entries"]), default=0)):
        if rep != payload.sales_rep or remaining < 0.01 or data["available"] < 0.01:
            continue
        paid = min(remaining, data["available"])
        source = data["entries"][0]
        db.add(CommissionWalletLedger(period_id=source.period_id, job_id=job_id, sales_rep=rep, employee_id=source.employee_id, entry_type="PAID", amount=round(paid, 2), payout_period=payload.payout_period, payout_batch=batch, note=payload.note or "Chi trả commission từ ví thưởng."))
        remaining = round(remaining - paid, 2)
    db.commit()
    return {"message": "Đã tạo đợt chi trả commission.", "paid_amount": amount, "payout_batch": batch}


def _wallet_source_for_action(db: Session, sales_rep: str, period_id: Optional[int], job_id: Optional[int]) -> CommissionWalletLedger:
    query = db.query(CommissionWalletLedger).filter(CommissionWalletLedger.sales_rep == sales_rep)
    if period_id is not None:
        query = query.filter(CommissionWalletLedger.period_id == period_id)
    if job_id is not None:
        query = query.filter(CommissionWalletLedger.job_id == job_id)
    source = query.order_by(CommissionWalletLedger.id.asc()).first()
    if not source:
        raise HTTPException(status_code=404, detail="Không tìm thấy khoản thưởng nguồn để điều chỉnh.")
    return source


@router.post("/wallet/adjustments")
def adjust_commission_wallet(payload: CommissionWalletAdjustmentIn, db: Session = Depends(get_db), current_user=Depends(get_admin_user)):
    if payload.amount <= 0 or not payload.reason.strip():
        raise HTTPException(status_code=422, detail="Số tiền và lý do điều chỉnh là bắt buộc.")
    source = _wallet_source_for_action(db, payload.sales_rep, payload.period_id, payload.job_id)
    _ensure_bonus_editable(db, source.period_id, source.sales_rep)
    entry_type = "MANUAL_DECREASE" if payload.action == "DECREASE" else "MANUAL_CREDIT"
    amount = -round(payload.amount, 2) if payload.action == "DECREASE" else round(payload.amount, 2)
    db.add(CommissionWalletLedger(
        period_id=source.period_id, job_id=source.job_id, entitlement_id=source.entitlement_id,
        sales_rep=source.sales_rep, employee_id=source.employee_id, entry_type=entry_type, amount=amount,
        payout_period=payload.target_payout_period, note=payload.reason.strip(), reason_code=payload.action,
        created_by=current_user.username if hasattr(current_user, "username") else str(current_user.id),
    ))
    db.commit()
    return {"message": "Đã ghi nhận điều chỉnh bonus vào sổ cái.", "entry_type": entry_type, "amount": amount}


def _undo_target_ids(entries: list[CommissionWalletLedger]) -> set[int]:
    """Return original ledger ids that already have an immutable undo entry."""
    targets: set[int] = set()
    for entry in entries:
        match = re.search(r"\[UNDO_OF:([0-9,]+)\]", entry.note or "")
        if not match:
            continue
        targets.update(int(value) for value in match.group(1).split(",") if value.isdigit())
    return targets


def _undo_note(entry_ids: list[int], description: str) -> str:
    return f"[UNDO_OF:{','.join(str(entry_id) for entry_id in entry_ids)}] Hoàn tác: {description}"


@router.post("/wallet/undo-last")
def undo_last_commission_wallet_operation(
    payload: CommissionWalletUndoIn,
    db: Session = Depends(get_db),
    current_user=Depends(get_admin_user),
):
    """Append a compensating ledger entry for the latest reversible user action.

    Commission remains audit-safe: this endpoint never deletes ledger history and
    never reverses an actual payment. A paid payout must be handled by a separate
    recovery/accounting process.
    """
    entries_query = db.query(CommissionWalletLedger).filter(
        CommissionWalletLedger.sales_rep == payload.sales_rep,
    )
    if payload.source_period_id is not None:
        entries_query = entries_query.filter(CommissionWalletLedger.period_id == payload.source_period_id)
    entries = entries_query.order_by(CommissionWalletLedger.id.asc()).all()
    if not entries:
        raise HTTPException(status_code=404, detail="Chưa có sổ cái ví thưởng để hoàn tác.")

    undone_ids = _undo_target_ids(entries)
    reversible_types = {
        "MANUAL_CREDIT", "MANUAL_DECREASE", "MANUAL_HOLD", "MANUAL_RELEASE",
        "TRANSFER_OUT", "TRANSFER_IN", "SCHEDULED",
    }
    candidate = next((entry for entry in reversed(entries) if entry.id not in undone_ids and entry.entry_type in reversible_types), None)
    if not candidate:
        raise HTTPException(
            status_code=409,
            detail="Không có thao tác ví gần nhất có thể hoàn tác. Các đợt đã chi trả không được hoàn tác tại đây.",
        )

    _ensure_bonus_editable(db, candidate.period_id, candidate.sales_rep)
    actor = current_user.username if hasattr(current_user, "username") else str(current_user.id)

    def append_inverse(entry: CommissionWalletLedger, entry_type: str, amount: float, targets: list[int], description: str) -> None:
        db.add(CommissionWalletLedger(
            period_id=entry.period_id,
            job_id=entry.job_id,
            entitlement_id=entry.entitlement_id,
            schedule_id=entry.schedule_id,
            sales_rep=entry.sales_rep,
            employee_id=entry.employee_id,
            entry_type=entry_type,
            amount=round(amount, 2),
            payout_period=entry.payout_period,
            note=_undo_note(targets, description),
            reason_code="UNDO",
            created_by=actor,
        ))

    if candidate.entry_type == "MANUAL_CREDIT":
        append_inverse(candidate, "MANUAL_CREDIT_REVERSAL", -abs(candidate.amount), [candidate.id], "cộng thủ công bonus")
        action_label = "cộng thủ công bonus"
    elif candidate.entry_type == "MANUAL_DECREASE":
        append_inverse(candidate, "MANUAL_DECREASE_REVERSAL", abs(candidate.amount), [candidate.id], "giảm/khấu trừ bonus")
        action_label = "giảm/khấu trừ bonus"
    elif candidate.entry_type == "MANUAL_HOLD":
        append_inverse(candidate, "MANUAL_HOLD_REVERSAL", -abs(candidate.amount), [candidate.id], "giữ thủ công JOB")
        action_label = "giữ thủ công JOB"
    elif candidate.entry_type == "MANUAL_RELEASE":
        append_inverse(candidate, "MANUAL_RELEASE_REVERSAL", -abs(candidate.amount), [candidate.id], "mở khóa thủ công JOB")
        action_label = "mở khóa thủ công JOB"
    elif candidate.entry_type in {"TRANSFER_OUT", "TRANSFER_IN"}:
        # A transfer is written as an adjacent OUT/IN pair. Reverse both rows
        # together so available balance and the transferred display reconcile.
        pair = next((entry for entry in reversed(entries) if entry.id not in undone_ids and entry.id != candidate.id
                     and entry.entry_type in {"TRANSFER_OUT", "TRANSFER_IN"}
                     and entry.entry_type != candidate.entry_type
                     and entry.job_id == candidate.job_id
                     and entry.period_id == candidate.period_id
                     and round(abs(entry.amount), 2) == round(abs(candidate.amount), 2)
                     and entry.reason_code == "TRANSFER"
                     and entry.note == candidate.note), None)
        if not pair:
            raise HTTPException(status_code=409, detail="Không tìm thấy cặp bút toán chuyển kỳ để hoàn tác an toàn.")
        transfer_out = candidate if candidate.entry_type == "TRANSFER_OUT" else pair
        transfer_in = candidate if candidate.entry_type == "TRANSFER_IN" else pair
        target_ids = [transfer_out.id, transfer_in.id]
        append_inverse(transfer_out, "TRANSFER_OUT_REVERSAL", abs(transfer_out.amount), target_ids, "chuyển bonus sang kỳ sau")
        append_inverse(transfer_in, "TRANSFER_IN_REVERSAL", -abs(transfer_in.amount), target_ids, "chuyển bonus sang kỳ sau")
        action_label = "chuyển bonus sang kỳ sau"
    else:  # SCHEDULED
        schedule = db.get(CommissionPayoutSchedule, candidate.schedule_id) if candidate.schedule_id else None
        if not schedule or schedule.status != "SCHEDULED":
            raise HTTPException(status_code=409, detail="Lịch chi trả này đã được xử lý nên không thể hoàn tác tại đây.")
        allocations = db.query(CommissionPayoutScheduleAllocation).filter(
            CommissionPayoutScheduleAllocation.schedule_id == schedule.id,
            CommissionPayoutScheduleAllocation.status == "SCHEDULED",
        ).all()
        target_ids = [allocation.ledger_entry_id for allocation in allocations if allocation.ledger_entry_id]
        if not target_ids:
            raise HTTPException(status_code=409, detail="Không tìm thấy phân bổ của lịch chi trả để hoàn tác.")
        for allocation in allocations:
            reserved = db.get(CommissionWalletLedger, allocation.ledger_entry_id)
            if not reserved:
                continue
            append_inverse(reserved, "SCHEDULE_RELEASE", -abs(allocation.amount), target_ids, "lập lịch chi trả bonus")
            allocation.status = "CANCELLED"
        schedule.status = "CANCELLED"
        schedule.approved_by = actor
        action_label = "lập lịch chi trả bonus"

    db.commit()
    return {"message": f"Đã hoàn tác {action_label}. Sổ cái vẫn lưu bút toán đảo chiều để đối soát.", "undone_entry_id": candidate.id}


@router.post("/wallet/job-holds")
def set_commission_job_hold(payload: CommissionJobHoldIn, db: Session = Depends(get_db), current_user=Depends(get_admin_user)):
    """Lock or release the available bonus of exactly one JOB without changing formulas."""
    job = db.query(CommissionJob).filter(
        CommissionJob.id == payload.job_id,
        CommissionJob.sales_rep == payload.sales_rep,
    ).first()
    if not job:
        raise HTTPException(status_code=404, detail="KhÃ´ng tÃ¬m tháº¥y JOB thuá»™c nhÃ¢n viÃªn Ä‘Ã£ chá»n.")

    _ensure_bonus_editable(db, job.period_id, job.sales_rep or "(Unknown)")
    entries = db.query(CommissionWalletLedger).filter(
        CommissionWalletLedger.sales_rep == payload.sales_rep,
        CommissionWalletLedger.job_id == payload.job_id,
    ).order_by(CommissionWalletLedger.id).all()
    if not entries:
        raise HTTPException(status_code=409, detail="JOB chÆ°a cÃ³ bonus Ä‘á»ƒ giá»¯. HÃ£y Ä‘á»“ng bá»™ vÃ­ thÆ°á»Ÿng trÆ°á»›c.")

    position = _wallet_positions(entries).get((payload.sales_rep, payload.job_id), {})
    source = entries[0]
    if payload.action == "HOLD":
        maximum = float(position.get("available", 0.0))
        entry_type = "MANUAL_HOLD"
        action_label = "giá»¯"
    else:
        maximum = float(position.get("manual_held", 0.0))
        entry_type = "MANUAL_RELEASE"
        action_label = "má»Ÿ khÃ³a"
    amount = round(float(payload.amount if payload.amount is not None else maximum), 2)
    if amount <= 0 or amount > maximum + 0.01:
        raise HTTPException(status_code=422, detail=f"Sá»‘ tiá»n {action_label} pháº£i náº±m trong sá»‘ dÆ° cá»§a JOB Ä‘Ã£ chá»n.")

    actor = current_user.username if hasattr(current_user, "username") else str(current_user.id)
    db.add(CommissionWalletLedger(
        period_id=source.period_id,
        job_id=source.job_id,
        entitlement_id=source.entitlement_id,
        sales_rep=source.sales_rep,
        employee_id=source.employee_id,
        entry_type=entry_type,
        amount=amount,
        note=(payload.reason or f"{action_label.capitalize()} bonus thá»§ cÃ´ng cho JOB {job.job_no}.").strip(),
        reason_code="JOB_HOLD" if payload.action == "HOLD" else "JOB_RELEASE",
        created_by=actor,
    ))
    db.commit()
    return {"message": f"ÄÃ£ {action_label} {amount:,.2f} bonus cá»§a JOB {job.job_no}.", "entry_type": entry_type, "amount": amount}


@router.put("/wallet/jobs/{job_id}/manual-hold")
def set_commission_job_manual_hold_target(
    job_id: int,
    payload: CommissionJobManualHoldTargetIn,
    db: Session = Depends(get_db),
    current_user=Depends(get_admin_user),
):
    """Set a JOB's manual hold to a requested total by appending only the delta."""
    if payload.manual_held_amount < 0:
        raise HTTPException(status_code=422, detail="Giá»¯ thá»§ cÃ´ng khÃ´ng Ä‘Æ°á»£c nhá» hÆ¡n 0.")
    job = db.query(CommissionJob).filter(
        CommissionJob.id == job_id,
        CommissionJob.sales_rep == payload.sales_rep,
    ).first()
    if not job:
        raise HTTPException(status_code=404, detail="KhÃ´ng tÃ¬m tháº¥y JOB thuá»™c nhÃ¢n viÃªn Ä‘Ã£ chá»n.")
    _ensure_bonus_editable(db, job.period_id, job.sales_rep or "(Unknown)")
    entries = db.query(CommissionWalletLedger).filter(
        CommissionWalletLedger.sales_rep == payload.sales_rep,
        CommissionWalletLedger.job_id == job_id,
    ).order_by(CommissionWalletLedger.id).all()
    if not entries:
        raise HTTPException(status_code=409, detail="JOB chÆ°a cÃ³ bonus Ä‘á»ƒ Ä‘iá»u chá»‰nh giá»¯ thá»§ cÃ´ng.")

    position = _wallet_positions(entries).get((payload.sales_rep, job_id), {})
    current = round(float(position.get("manual_held", 0.0)), 2)
    target = round(float(payload.manual_held_amount), 2)
    delta = round(target - current, 2)
    if abs(delta) < 0.01:
        return {"message": "Sá»‘ giá»¯ thá»§ cÃ´ng khÃ´ng thay Ä‘á»•i.", "manual_held_amount": current}
    if delta > float(position.get("available", 0.0)) + 0.01:
        raise HTTPException(status_code=422, detail="Sá»‘ giá»¯ thá»§ cÃ´ng má»›i vÆ°á»£t quÃ¡ sá»‘ dÆ° kháº£ dá»¥ng cá»§a JOB.")

    source = entries[0]
    actor = current_user.username if hasattr(current_user, "username") else str(current_user.id)
    entry_type = "MANUAL_HOLD" if delta > 0 else "MANUAL_RELEASE"
    db.add(CommissionWalletLedger(
        period_id=source.period_id, job_id=source.job_id, entitlement_id=source.entitlement_id,
        sales_rep=source.sales_rep, employee_id=source.employee_id, entry_type=entry_type,
        amount=abs(delta), reason_code="JOB_HOLD_EDIT", created_by=actor,
        note=(payload.remark or f"Äiá»u chá»‰nh giá»¯ thá»§ cÃ´ng JOB {job.job_no}: {current:,.2f} -> {target:,.2f}.").strip(),
    ))
    job.bonus_remark = payload.remark.strip() if payload.remark and payload.remark.strip() else job.bonus_remark
    db.commit()
    return {"message": "ÄÃ£ cáº­p nháº­t giá»¯ thá»§ cÃ´ng theo JOB.", "manual_held_amount": target, "entry_type": entry_type}


@router.post("/wallet/transfers")
def transfer_commission_wallet(payload: CommissionWalletTransferIn, db: Session = Depends(get_db), current_user=Depends(get_admin_user)):
    if payload.amount <= 0 or len(payload.target_payout_period) != 7 or not payload.reason.strip():
        raise HTTPException(status_code=422, detail="Số tiền, kỳ đích (YYYY-MM) và lý do chuyển là bắt buộc.")
    source = _wallet_source_for_action(db, payload.sales_rep, payload.source_period_id, payload.source_job_id)
    _ensure_bonus_editable(db, source.period_id, source.sales_rep)
    positions = _wallet_positions(db.query(CommissionWalletLedger).filter(CommissionWalletLedger.sales_rep == payload.sales_rep).all())
    available = positions.get((payload.sales_rep, source.job_id), {}).get("available", 0.0)
    if payload.amount > available + 0.01:
        raise HTTPException(status_code=422, detail="Số tiền chuyển vượt quá số khả dụng của khoản thưởng nguồn.")
    actor = current_user.username if hasattr(current_user, "username") else str(current_user.id)
    common = dict(period_id=source.period_id, job_id=source.job_id, entitlement_id=source.entitlement_id, sales_rep=source.sales_rep, employee_id=source.employee_id, note=payload.reason.strip(), reason_code="TRANSFER", created_by=actor)
    db.add(CommissionWalletLedger(
        **common,
        entry_type="TRANSFER_OUT",
        amount=-round(payload.amount, 2),
        # Explicitly preserve the salary month the money leaves. Older rows
        # without this value are interpreted as the first payout month.
        payout_period=payload.source_payout_period,
    ))
    db.add(CommissionWalletLedger(**common, entry_type="TRANSFER_IN", amount=round(payload.amount, 2), payout_period=payload.target_payout_period))
    db.commit()
    amount = round(payload.amount, 2)
    return {
        "message": f"Đã chuyển bonus {amount:,.2f} sang kỳ chi trả đích.",
        "amount": amount,
        "target_payout_period": payload.target_payout_period,
    }


@router.post("/wallet/schedules")
def schedule_commission_payout(payload: CommissionPayoutScheduleIn, db: Session = Depends(get_db), current_user=Depends(get_admin_user)):
    if len(payload.payout_period) != 7:
        raise HTTPException(status_code=422, detail="Kỳ chi trả phải theo định dạng YYYY-MM.")
    entries_query = db.query(CommissionWalletLedger).filter(CommissionWalletLedger.sales_rep == payload.sales_rep)
    if payload.source_period_id is not None:
        entries_query = entries_query.filter(CommissionWalletLedger.period_id == payload.source_period_id)
    entries = entries_query.order_by(CommissionWalletLedger.id).all()
    positions = _wallet_positions(entries)
    locked_periods = _locked_source_periods_for_positions(db, payload.sales_rep, positions)
    if locked_periods:
        raise HTTPException(status_code=409, detail=f"Không thể lập lịch: bảng bonus nguồn đã khóa ở kỳ {locked_periods}.")
    available = round(sum(item["available"] for (rep, _), item in positions.items() if rep == payload.sales_rep), 2)
    amount = round(payload.amount if payload.amount is not None else available, 2)
    if amount <= 0 or amount > available + 0.01:
        raise HTTPException(status_code=422, detail="Số tiền lập lịch phải nằm trong số dư khả dụng.")
    actor = current_user.username if hasattr(current_user, "username") else str(current_user.id)
    schedule = CommissionPayoutSchedule(sales_rep=payload.sales_rep, employee_id=_employee_id_for_sales_rep(payload.sales_rep, db), payout_period=payload.payout_period, total_amount=amount, note=payload.note, created_by=actor)
    db.add(schedule)
    db.flush()
    remaining = amount
    for (rep, job_id), position in sorted(positions.items(), key=lambda item: min((entry.id for entry in item[1]["entries"]), default=0)):
        if rep != payload.sales_rep or remaining < 0.01 or position["available"] < 0.01:
            continue
        reserved = min(remaining, position["available"])
        source = position["entries"][0]
        ledger = CommissionWalletLedger(period_id=source.period_id, job_id=job_id, entitlement_id=source.entitlement_id, schedule_id=schedule.id, sales_rep=rep, employee_id=source.employee_id, entry_type="SCHEDULED", amount=round(reserved, 2), payout_period=payload.payout_period, note=payload.note or "Lập lịch chi trả bonus.", reason_code="SCHEDULE", created_by=actor)
        db.add(ledger)
        db.flush()
        db.add(CommissionPayoutScheduleAllocation(schedule_id=schedule.id, entitlement_id=source.entitlement_id, ledger_entry_id=ledger.id, amount=round(reserved, 2)))
        remaining = round(remaining - reserved, 2)
    db.commit()
    return {"message": "Đã lập lịch chi trả bonus.", "schedule_id": schedule.id, "payout_period": schedule.payout_period, "amount": amount}


@router.get("/wallet/schedules")
def list_commission_payout_schedules(
    sales_rep: Optional[str] = None,
    period_id: Optional[int] = None,
    db: Session = Depends(get_db),
):
    query = db.query(CommissionPayoutSchedule)
    if sales_rep:
        query = query.filter(CommissionPayoutSchedule.sales_rep == sales_rep)
    schedules = query.order_by(CommissionPayoutSchedule.payout_period, CommissionPayoutSchedule.id).all()
    result = []
    for item in schedules:
        allocations = db.query(CommissionPayoutScheduleAllocation).filter(
            CommissionPayoutScheduleAllocation.schedule_id == item.id,
        ).all()
        entries_by_allocation_id = {
            allocation.id: db.get(CommissionWalletLedger, allocation.ledger_entry_id) if allocation.ledger_entry_id else None
            for allocation in allocations
        }
        source_period_ids = sorted({entry.period_id for entry in entries_by_allocation_id.values() if entry})
        matching_allocations = [
            allocation for allocation in allocations
            if (entry := entries_by_allocation_id.get(allocation.id))
            and (period_id is None or entry.period_id == period_id)
        ]
        if period_id is not None and not matching_allocations:
            continue
        matching_entries = [
            entries_by_allocation_id[allocation.id]
            for allocation in matching_allocations
            if entries_by_allocation_id.get(allocation.id)
        ]
        job_ids = {entry.job_id for entry in matching_entries if entry.job_id is not None}
        period_ids = {entry.period_id for entry in matching_entries if entry.period_id is not None}
        jobs_by_id = {
            job.id: job
            for job in db.query(CommissionJob).filter(CommissionJob.id.in_(job_ids)).all()
        } if job_ids else {}
        periods_by_id = {
            period.id: period
            for period in db.query(CommissionPeriod).filter(CommissionPeriod.id.in_(period_ids)).all()
        } if period_ids else {}
        schedule_jobs = []
        seen_job_ids = set()
        for allocation in matching_allocations:
            entry = entries_by_allocation_id.get(allocation.id)
            if not entry or entry.job_id is None or entry.job_id in seen_job_ids:
                continue
            seen_job_ids.add(entry.job_id)
            job = jobs_by_id.get(entry.job_id)
            period = periods_by_id.get(entry.period_id)
            schedule_jobs.append({
                "job_id": entry.job_id,
                "job_no": job.job_no if job else f"JOB #{entry.job_id}",
                "period_id": entry.period_id,
                "period_label": period.period_label if period else f"Kỳ #{entry.period_id}",
                "amount": round(sum(
                    candidate.amount
                    for candidate in matching_allocations
                    if (candidate_entry := entries_by_allocation_id.get(candidate.id))
                    and candidate_entry.job_id == entry.job_id
                ), 2),
            })
        result.append({
            "id": item.id,
            "sales_rep": item.sales_rep,
            "payout_period": item.payout_period,
            "status": item.status,
            "total_amount": round(sum(allocation.amount for allocation in matching_allocations), 2) if period_id is not None else item.total_amount,
            "job_count": len({entry.job_id for entry in matching_entries if entry.job_id is not None}),
            "jobs": schedule_jobs,
            "note": item.note,
            "source_period_ids": source_period_ids,
            "is_period_scoped": period_id is None or source_period_ids == [period_id],
        })
    return result


def _finish_schedule(schedule_id: int, status_value: str, note: Optional[str], db: Session, current_user):
    schedule = db.get(CommissionPayoutSchedule, schedule_id)
    if not schedule or schedule.status != "SCHEDULED":
        raise HTTPException(status_code=409, detail="Lịch chi trả không tồn tại hoặc không còn ở trạng thái đã lập lịch.")
    action_note = note.strip() if note and note.strip() else None
    if status_value == "CANCELLED" and not action_note:
        raise HTTPException(status_code=422, detail="Vui lòng nhập lý do hủy lịch chi trả.")
    actor = current_user.username if hasattr(current_user, "username") else str(current_user.id)
    allocations = db.query(CommissionPayoutScheduleAllocation).filter(CommissionPayoutScheduleAllocation.schedule_id == schedule.id, CommissionPayoutScheduleAllocation.status == "SCHEDULED").all()
    affected_jobs: dict[int, tuple[CommissionJob, Optional[int]]] = {}
    for allocation in allocations:
        reserved = db.get(CommissionWalletLedger, allocation.ledger_entry_id)
        if not reserved:
            continue
        _ensure_bonus_editable(db, reserved.period_id, reserved.sales_rep)
        common = dict(period_id=reserved.period_id, job_id=reserved.job_id, entitlement_id=reserved.entitlement_id, schedule_id=schedule.id, sales_rep=reserved.sales_rep, employee_id=reserved.employee_id, payout_period=schedule.payout_period, note=action_note or schedule.note, created_by=actor)
        db.add(CommissionWalletLedger(**common, entry_type="SCHEDULE_RELEASE", amount=-allocation.amount, reason_code="SCHEDULE_RELEASE"))
        if status_value == "PAID":
            db.add(CommissionWalletLedger(**common, entry_type="PAID", amount=allocation.amount, reason_code="SCHEDULE_PAID", approved_by=actor))
        elif schedule.payment_verification_id:
            # A cancelled accounting command returns only its cancelled amount
            # to the automatic hold. Existing ledger rows are never altered.
            db.add(CommissionWalletLedger(**common, entry_type="PAYMENT_STATUS_HOLD", amount=allocation.amount, reason_code="PAYMENT_COMMAND_CANCELLED"))
        if status_value == "CANCELLED" and reserved.job_id is not None:
            job = db.get(CommissionJob, reserved.job_id)
            if job:
                affected_jobs[job.id] = (job, reserved.employee_id or schedule.employee_id)
        allocation.status = status_value
    schedule.status = status_value
    if action_note:
        schedule.note = action_note
    schedule.approved_by = actor
    if status_value == "CANCELLED" and schedule.payment_verification_id:
        remaining = db.query(CommissionPayoutSchedule).filter(
            CommissionPayoutSchedule.payment_verification_id == schedule.payment_verification_id,
            CommissionPayoutSchedule.status == "SCHEDULED",
            CommissionPayoutSchedule.id != schedule.id,
        ).count()
        if remaining == 0:
            verification = db.get(CommissionPaymentVerification, schedule.payment_verification_id)
            if verification:
                # Keep the audit row, but expose this workflow as a fresh,
                # requestable JOB again in both accounting and employee views.
                verification.status = "CANCELLED"
                verification.verification_note = f"Đã hủy lịch chi trả: {action_note}"
                verification.verified_by = None
                verification.verified_at = None
                verification.command_created_by = None
                verification.command_created_at = None
                job = db.get(CommissionJob, verification.job_id)
                if job:
                    job.payment_received = "NO"
                    job.bonus_remark = f"Lịch chi trả đã hủy: {action_note}"
                    affected_jobs.setdefault(job.id, (job, schedule.employee_id))

    if status_value == "CANCELLED" and schedule.payment_verification_id:
        from app.models.employee import Employee

        for job, employee_id in affected_jobs.values():
            if not employee_id:
                continue
            target_employee = db.get(Employee, employee_id)
            if not target_employee:
                continue
            add_employee_notification(
                db,
                target_employee,
                category=BONUS,
                event_type="BONUS_PAYOUT_CANCELLED",
                title=f"Đã hủy lịch chi trả bonus JOB {job.job_no}",
                message=(
                    f"Kế toán đã hủy lịch chi trả bonus JOB {job.job_no}, tháng {schedule.payout_period}. "
                    f"Lý do: {action_note}. JOB đã trở về trạng thái chưa yêu cầu và bonus được hoàn vào đang giữ."
                ),
                actor_user_id=actor_id(current_user),
                resource_type="COMMISSION_JOB",
                resource_id=job.id,
                action_url="/user/my-held-bonuses",
            )
    db.commit()
    return {
        "message": "Đã chi trả lịch bonus." if status_value == "PAID" else "Đã hủy lịch chi trả bonus và hoàn JOB về trạng thái đang giữ.",
        "schedule_id": schedule.id,
    }


@router.post("/wallet/schedules/{schedule_id}/pay")
def pay_commission_schedule(schedule_id: int, payload: CommissionScheduleActionIn, db: Session = Depends(get_db), current_user=Depends(get_admin_user)):
    return _finish_schedule(schedule_id, "PAID", payload.note, db, current_user)


@router.post("/wallet/schedules/{schedule_id}/cancel")
def cancel_commission_schedule(schedule_id: int, payload: CommissionScheduleCancelIn, db: Session = Depends(get_db), current_user=Depends(get_admin_user)):
    return _finish_schedule(schedule_id, "CANCELLED", payload.reason, db, current_user)


# ══════════════════════════════════════════════════════
# DELETE /api/commission/periods/{id}
# ══════════════════════════════════════════════════════
@router.delete("/periods/{period_id}", status_code=status.HTTP_200_OK)
def delete_period(period_id: int, db: Session = Depends(get_db)):
    period = db.query(CommissionPeriod).filter(CommissionPeriod.id == period_id).first()
    if not period:
        raise HTTPException(status_code=404, detail="Kỳ commission không tồn tại.")
    locked_reps = db.query(CommissionBonusLock.sales_rep).filter(
        CommissionBonusLock.period_id == period_id,
    ).all()
    if locked_reps:
        raise HTTPException(status_code=409, detail="Không thể xóa kỳ commission vì đang có bảng bonus đã khóa.")
    receivable_attachments = db.query(CommissionJobReceivableAttachment).filter(
        CommissionJobReceivableAttachment.period_id == period_id,
    ).all()
    receivable_paths = [COMMISSION_RECEIVABLE_UPLOAD_DIR / item.stored_filename for item in receivable_attachments]
    db.query(CommissionJobReceivableLink).filter(
        CommissionJobReceivableLink.period_id == period_id,
    ).delete(synchronize_session=False)
    db.query(CommissionJobReceivableAttachment).filter(
        CommissionJobReceivableAttachment.period_id == period_id,
    ).delete(synchronize_session=False)
    db.query(CommissionWalletLedger).filter(CommissionWalletLedger.period_id == period_id).delete(synchronize_session=False)
    db.query(CommissionRepOverride).filter(CommissionRepOverride.period_id == period_id).delete(synchronize_session=False)
    db.query(CommissionJob).filter(CommissionJob.period_id == period_id).delete(synchronize_session=False)
    db.delete(period)
    db.commit()
    for path in receivable_paths:
        path.unlink(missing_ok=True)
    return {"message": f"Đã xóa toàn bộ commission của kỳ ID {period_id}."}


@router.delete("/periods/{period_id}/reps/{sales_rep}", status_code=status.HTTP_200_OK)
def delete_sales_rep_commission(period_id: int, sales_rep: str, db: Session = Depends(get_db)):
    """Test-friendly delete: remove only one Sales Rep's JOBs and wallet rows in one period."""
    period = db.query(CommissionPeriod).filter(CommissionPeriod.id == period_id).first()
    if not period:
        raise HTTPException(status_code=404, detail="Kỳ commission không tồn tại.")
    _ensure_bonus_editable(db, period_id, sales_rep)
    job_count = db.query(CommissionJob).filter(CommissionJob.period_id == period_id, CommissionJob.sales_rep == sales_rep).count()
    if not job_count:
        raise HTTPException(status_code=404, detail="Không tìm thấy commission của nhân viên này trong kỳ đã chọn.")
    rep_job_ids = [row[0] for row in db.query(CommissionJob.id).filter(
        CommissionJob.period_id == period_id,
        CommissionJob.sales_rep == sales_rep,
    ).all()]
    receivable_attachment_ids = [row[0] for row in db.query(
        CommissionJobReceivableLink.attachment_id,
    ).filter(CommissionJobReceivableLink.job_id.in_(rep_job_ids)).distinct().all()]
    db.query(CommissionJobReceivableLink).filter(
        CommissionJobReceivableLink.job_id.in_(rep_job_ids),
    ).delete(synchronize_session=False)
    db.flush()
    orphan_attachments = db.query(CommissionJobReceivableAttachment).filter(
        CommissionJobReceivableAttachment.id.in_(receivable_attachment_ids),
        ~CommissionJobReceivableAttachment.job_links.any(),
    ).all() if receivable_attachment_ids else []
    receivable_paths = [COMMISSION_RECEIVABLE_UPLOAD_DIR / item.stored_filename for item in orphan_attachments]
    for attachment in orphan_attachments:
        db.delete(attachment)
    wallet_count = db.query(CommissionWalletLedger).filter(CommissionWalletLedger.period_id == period_id, CommissionWalletLedger.sales_rep == sales_rep).count()
    db.query(CommissionWalletLedger).filter(CommissionWalletLedger.period_id == period_id, CommissionWalletLedger.sales_rep == sales_rep).delete(synchronize_session=False)
    db.query(CommissionRepOverride).filter(CommissionRepOverride.period_id == period_id, CommissionRepOverride.sales_rep == sales_rep).delete(synchronize_session=False)
    db.query(CommissionJob).filter(CommissionJob.period_id == period_id, CommissionJob.sales_rep == sales_rep).delete(synchronize_session=False)
    if not db.query(CommissionJob).filter(CommissionJob.period_id == period_id).first():
        db.query(CommissionWalletLedger).filter(CommissionWalletLedger.period_id == period_id).delete(synchronize_session=False)
        db.query(CommissionRepOverride).filter(CommissionRepOverride.period_id == period_id).delete(synchronize_session=False)
        db.delete(period)
    db.commit()
    for path in receivable_paths:
        path.unlink(missing_ok=True)
    return {
        "message": f"Đã xóa commission và phễu thưởng của {sales_rep} trong kỳ đã chọn.",
        "jobs_deleted": job_count,
        "wallet_entries_deleted": wallet_count,
    }


# ══════════════════════════════════════════════════════
# POST /api/commission/periods/{period_id}/reps/{sales_rep}/override
# ══════════════════════════════════════════════════════
@router.post("/periods/{period_id}/reps/{sales_rep}/override")
def upsert_rep_override(
    period_id: int,
    sales_rep: str,
    payload: CommissionRepOverrideIn,
    db: Session = Depends(get_db),
    current_user=Depends(get_admin_user),
):
    """
    Tạo hoặc cập nhật giá trị ghi đè cho Sales Rep trong kỳ commission.
    """
    from app.models.commission import CommissionRepOverride, CommissionPeriod

    period = db.query(CommissionPeriod).filter(CommissionPeriod.id == period_id).first()
    if not period:
        raise HTTPException(status_code=404, detail="Kỳ commission không tồn tại.")
    _ensure_bonus_editable(db, period_id, sales_rep)

    override = db.query(CommissionRepOverride).filter(
        CommissionRepOverride.period_id == period_id,
        CommissionRepOverride.sales_rep == sales_rep
    ).first()

    if not override:
        override = CommissionRepOverride(
            period_id=period_id,
            sales_rep=sales_rep
        )
        db.add(override)

    override.override_job_count = payload.override_job_count
    override.override_profit_loss = payload.override_profit_loss
    override.override_target = payload.override_target
    override.override_bonus_rate = payload.override_bonus_rate
    override.override_total_bonus = payload.override_total_bonus
    override.override_monthly_bonus = payload.override_monthly_bonus
    override.remark = payload.remark

    db.commit()
    return {"message": f"Đã lưu các giá trị chỉnh sửa cho {sales_rep}."}
