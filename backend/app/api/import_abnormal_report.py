from fastapi import APIRouter, UploadFile, File, HTTPException
from pydantic import BaseModel
from typing import List, Optional
import pandas as pd
import io

router = APIRouter()

class AbnormalReportPreview(BaseModel):
    machine_employee_id: str
    full_name: Optional[str]
    work_date: str
    note: Optional[str]
    status: Optional[str]
    department: Optional[str]
    missing_punch: bool = False
    error: Optional[str]

@router.post("/api/import/abnormal-report", response_model=List[AbnormalReportPreview])
async def import_abnormal_report(file: UploadFile = File(...)):
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
        "Ghi chú": "note",
        "Trạng thái": "status",
        "Phòng ban": "department",
    }
    for col in col_map:
        if col not in df.columns:
            raise HTTPException(status_code=400, detail=f"Thiếu cột bắt buộc: {col}")
    results = []
    for _, row in df.iterrows():
        try:
            note = str(row.get("Ghi chú", ""))
            missing_punch = "Bỏ lỡ" in note
            results.append(AbnormalReportPreview(
                machine_employee_id=str(row["Mã NV"]),
                full_name=row.get("Họ tên"),
                work_date=str(row["Ngày"]),
                note=note,
                status=row.get("Trạng thái"),
                department=row.get("Phòng ban"),
                missing_punch=missing_punch,
                error=None
            ))
        except Exception as e:
            results.append(AbnormalReportPreview(
                machine_employee_id=str(row.get("Mã NV", "")),
                full_name=row.get("Họ tên"),
                work_date=str(row.get("Ngày", "")),
                note=str(row.get("Ghi chú", "")),
                status=row.get("Trạng thái"),
                department=row.get("Phòng ban"),
                missing_punch=False,
                error=str(e)
            ))
    return results