from fastapi import APIRouter, UploadFile, File, HTTPException
from pydantic import BaseModel
from typing import List, Optional
import pandas as pd
import io

router = APIRouter()

from datetime import datetime, date, timedelta

class CheckinProfilePreview(BaseModel):
    machine_employee_id: str
    full_name: Optional[str]
    work_date: str
    raw_times: str
    department: Optional[str]
    check_in: Optional[str]
    check_out: Optional[str]
    period_start: Optional[str]
    period_end: Optional[str]
    error: Optional[str]

def get_period_range(work_date_str: str) -> tuple[str, str]:
    """
    Tính period_start, period_end theo quy tắc: 23 tháng trước đến 22 tháng này
    """
    try:
        d = datetime.strptime(work_date_str, "%Y-%m-%d").date()
    except Exception:
        try:
            d = datetime.strptime(work_date_str, "%d/%m/%Y").date()
        except Exception:
            return (None, None)
    if d.day >= 23:
        period_start = d.replace(day=23)
        # Tháng sau, ngày 22
        if d.month == 12:
            period_end = date(d.year+1, 1, 22)
        else:
            period_end = date(d.year, d.month+1, 22)
    else:
        # Tháng trước, ngày 23
        if d.month == 1:
            period_start = date(d.year-1, 12, 23)
        else:
            period_start = date(d.year, d.month-1, 23)
        period_end = d.replace(day=22)
    return (period_start.isoformat(), period_end.isoformat())

@router.post("/api/import/checkin-profile", response_model=List[CheckinProfilePreview])
def parse_checkin_row(row):
    try:
        raw_times = str(row["Giờ chấm công"]).replace("*", "").strip()
        # Multi-check: tách nhiều mốc giờ, loại bỏ ký tự đặc biệt
        times = [t.strip() for t in raw_times.replace(";", "\n").split("\n") if t.strip()]
        check_in = min(times) if times else None
        check_out = max(times) if times else None
        # Missing punch: nếu có từ "Bỏ lỡ" trong ghi chú hoặc raw_times
        missing_flag = "Bỏ lỡ" in raw_times or "Bỏ lỡ" in str(row.get("Ghi chú", ""))
        work_date = str(row["Ngày"])
        period_start, period_end = get_period_range(work_date)
        return CheckinProfilePreview(
            machine_employee_id=str(row["Mã NV"]),
            full_name=row.get("Họ tên"),
            work_date=work_date,
            raw_times=raw_times,
            department=row.get("Phòng ban"),
            check_in=check_in,
            check_out=check_out,
            period_start=period_start,
            period_end=period_end,
            error="Bỏ lỡ" if missing_flag else None
        )
    except Exception as e:
        return CheckinProfilePreview(
            machine_employee_id=str(row.get("Mã NV", "")),
            full_name=row.get("Họ tên"),
            work_date=str(row.get("Ngày", "")),
            raw_times=str(row.get("Giờ chấm công", "")),
            department=row.get("Phòng ban"),
            check_in=None,
            check_out=None,
            period_start=None,
            period_end=None,
            error=str(e)
        )

@router.post("/api/import/checkin-profile", response_model=List[CheckinProfilePreview])
async def import_checkin_profile(file: UploadFile = File(...)):
    try:
        content = await file.read()
        if file.filename.endswith(".csv"):
            df = pd.read_csv(io.BytesIO(content))
        else:
            df = pd.read_excel(io.BytesIO(content))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Lỗi đọc file: {e}")

    # Giả lập mapping cột
    col_map = {
        "Mã NV": "machine_employee_id",
        "Họ tên": "full_name",
        "Ngày": "work_date",
        "Giờ chấm công": "raw_times",
        "Phòng ban": "department",
    }
    for col in col_map:
        if col not in df.columns:
            raise HTTPException(status_code=400, detail=f"Thiếu cột bắt buộc: {col}")
    results = [parse_checkin_row(row) for _, row in df.iterrows()]
    return results