import json
import re
import unicodedata
from datetime import date, datetime
from io import BytesIO
from typing import Any, Literal

import pandas as pd
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_attendance_manager_user
from app.models.employee import Employee
from app.services.attendance_parser import AttendanceParser
from app.services.notion_leave_reconciliation import reconcile_attendance_with_notion

router = APIRouter(tags=["importer"], dependencies=[Depends(get_attendance_manager_user)])

TIME_PATTERN = re.compile(r"(?:[01]?\d|2[0-3]):[0-5]\d")
PERIOD_DATE_PATTERN = re.compile(r"(?<!\d)(?:\d{4}[-/.]\d{1,2}[-/.]\d{1,2}|\d{1,2}[-/.]\d{1,2}[-/.]\d{4})(?!\d)")


def clean_machine_id(val: str | None) -> str:
    if not val:
        return ""
    val_str = str(val).strip()
    val_str = re.sub(r"^[#＃]+\s*", "", val_str)
    if val_str.endswith(".0"):
        val_str = val_str[:-2]
    return val_str


HEADER_ALIASES = {
    "checkin": {
        "ID": ["id", "ma nv", "mã nv", "ma nhan vien", "mã nhân viên", "machine id", "machine employee id"],
        "Ten": ["ten", "họ tên", "ho ten", "họ và tên", "ten nhan vien"],
        "Ngay": ["ngay", "ngày", "date", "work date"],
        "Moc gio": ["moc gio", "mốc giờ", "gio quet", "giờ quét", "thoi gian quet", "thời gian quét", "du lieu quet", "dữ liệu quẹt", "scan data"],
        "In": ["in", "check in", "check-in", "gio vao", "giờ vào", "first in"],
        "Out": ["out", "check out", "check-out", "gio ra", "giờ ra", "last out"],
    },
    "abnormal": {
        "ID": ["id", "ma nv", "mã nv", "ma nhan vien", "mã nhân viên", "machine id", "machine employee id"],
        "Ten": ["ten", "họ tên", "ho ten", "họ và tên", "ten nhan vien"],
        "P.Ban": ["p ban", "phong ban", "phòng ban", "department", "department name"],
        "Ngay": ["ngay", "ngày", "date", "work date"],
        "Thoi gian tre": ["thoi gian tre", "thời gian trễ", "tre", "di muon", "đi muộn", "late", "late minutes"],
        "Thoi gian som": ["thoi gian som", "thời gian sớm", "som", "ve som", "về sớm", "early", "early minutes"],
        "Ghi chu": ["ghi chu", "ghi chú", "note", "notes", "remark", "remarks"],
    },
}

PREFERRED_SHEET_NAMES = {
    "checkin": [
        "ho so check in",
        "ho so checkin",
        "bao cao check in",
        "bao cao checkin",
        "bang tom tat check in",
    ],
    "abnormal": [
        "bao cao bat thuong",
    ],
}

IMPORT_TYPES = Literal["checkin", "abnormal"]


def _build_notion_employee_directory(db: Session) -> dict[str, list[str]]:
    rows = (
        db.query(Employee.notion_name, Employee.full_name, Employee.machine_employee_id)
        .order_by(Employee.id.asc())
        .all()
    )

    directory: dict[str, list[str]] = {}
    for notion_name, full_name, machine_employee_id in rows:
        names = [notion_name, full_name]
        normalized_machine_id = clean_machine_id(machine_employee_id)
        if not normalized_machine_id:
            continue
        for name in names:
            normalized_name = str(name or "").strip()
            if not normalized_name:
                continue
            directory.setdefault(normalized_name, [])
            if normalized_machine_id not in directory[normalized_name]:
                directory[normalized_name].append(normalized_machine_id)

    return directory


def _build_employee_report_directory(db: Session) -> dict[str, dict[str, str | None]]:
    rows = (
        db.query(
            Employee.machine_employee_id,
            Employee.biometric_id,
            Employee.full_name,
            Employee.department_name,
            Employee.notion_name,
        )
        .order_by(Employee.id.asc())
        .all()
    )

    directory: dict[str, dict[str, str | None]] = {}
    for machine_employee_id, biometric_id, full_name, department_name, notion_name in rows:
        normalized_machine_id = clean_machine_id(machine_employee_id)
        if not normalized_machine_id:
            continue
        profile = {
            "machine_employee_id": normalized_machine_id,
            # Tên Notion chỉ dùng làm khóa đối chiếu đơn. Mọi preview/export
            # phải hiển thị tên tiếng Việt được quản lý trong hồ sơ nhân viên.
            "full_name": str(full_name or "").strip() or str(notion_name or "").strip() or None,
            "department_name": str(department_name or "").strip() or None,
        }
        directory[normalized_machine_id] = profile
        normalized_biometric_id = clean_machine_id(biometric_id)
        if normalized_biometric_id:
            directory[normalized_biometric_id] = profile

    return directory


def _apply_employee_report_metadata(
    employees: list[dict],
    employee_report_directory: dict[str, dict[str, str | None]],
) -> list[dict]:
    merged_employees: dict[str, dict] = {}
    for employee in employees:
        machine_employee_id = clean_machine_id(employee.get("employee_id"))
        if not machine_employee_id:
            continue

        profile = employee_report_directory.get(machine_employee_id)
        canonical_id = str(profile.get("machine_employee_id") or machine_employee_id) if profile else machine_employee_id

        if profile and profile.get("full_name"):
            employee["full_name"] = profile["full_name"]
            employee["employee_name"] = profile["full_name"]
        if profile and profile.get("department_name"):
            employee["department_name"] = profile["department_name"]
            employee["department"] = profile["department_name"]
        employee["employee_id"] = canonical_id

        current = merged_employees.get(canonical_id)
        if current is None:
            merged_employees[canonical_id] = employee
            continue

        current_details = current.setdefault("attendance_details", {})
        for work_date, incoming_detail in (employee.get("attendance_details") or {}).items():
            existing_detail = current_details.get(work_date)
            if existing_detail is None:
                current_details[work_date] = incoming_detail
                continue

            punches = sorted({
                value
                for value in [
                    existing_detail.get("check_in"),
                    existing_detail.get("check_out"),
                    incoming_detail.get("check_in"),
                    incoming_detail.get("check_out"),
                ]
                if value
            })
            existing_detail["check_in"] = punches[0] if punches else None
            existing_detail["check_out"] = punches[-1] if len(punches) > 1 else None
            existing_detail["scheduled_to_work"] = bool(
                existing_detail.get("scheduled_to_work") or incoming_detail.get("scheduled_to_work")
            )
            existing_detail["late_minutes"] = max(
                int(existing_detail.get("late_minutes") or 0),
                int(incoming_detail.get("late_minutes") or 0),
            )
            if len(punches) > 1:
                existing_detail["status"] = "Normal"
            elif punches:
                existing_detail["status"] = "Missing_Punch"
            elif incoming_detail.get("status") == "Absent":
                existing_detail["status"] = "Absent"

    for employee in merged_employees.values():
        details = employee.get("attendance_details") or {}
        employee["summary_from_machine"] = {
            "total_late_minutes": sum(int(item.get("late_minutes") or 0) for item in details.values()),
            "total_absent_days": sum(1 for item in details.values() if item.get("status") == "Absent"),
        }

    return list(merged_employees.values())


class WorkbookColumnOption(BaseModel):
    index: int
    label: str
    display_label: str | None = None


class RawCheckinDayEntry(BaseModel):
    day_label: str
    time_values: list[str]


class RawCheckinEmployeeBlock(BaseModel):
    employee_id: str
    employee_name: str
    department_name: str
    day_entries: list[RawCheckinDayEntry]
    row_start_index: int
    row_end_index: int


class WorkbookSheetInspection(BaseModel):
    sheet_name: str
    header_row_index: int
    columns: list[WorkbookColumnOption]
    suggested_mapping: dict[str, int]
    match_score: int
    has_time_columns: bool = False
    sample_rows: list[dict[str, str]]
    raw_rows: list[dict[str, str]] = Field(default_factory=list)
    data_row_count: int = 0
    employee_blocks: list[RawCheckinEmployeeBlock] = Field(default_factory=list)
    period_start: str | None = None
    period_end: str | None = None


class WorkbookInspectionResponse(BaseModel):
    import_type: IMPORT_TYPES
    sheets: list[WorkbookSheetInspection]
    recommended_sheet_name: str | None = None
    recommended_header_row_index: int | None = None
    recommended_mapping: dict[str, int]


def required_columns_for_import(import_type: str) -> list[str]:
    if import_type == "checkin":
        return ["ID", "Ten", "Ngay"]
    return list(HEADER_ALIASES[import_type].keys())


def normalize_sheet_name(value: str) -> str:
    return normalize_header_text(value)


def normalize_import_type(value: str) -> str:
    normalized = str(value or "").strip().lower()
    if normalized not in HEADER_ALIASES:
        raise HTTPException(status_code=400, detail="import_type must be checkin or abnormal")
    return normalized


def score_sheet_name(name: str, import_type: str) -> int:
    preferred_names = PREFERRED_SHEET_NAMES.get(import_type, [])
    normalized_preferred = [normalize_sheet_name(item) for item in preferred_names]
    normalized = normalize_sheet_name(name)
    for idx, preferred in enumerate(normalized_preferred):
        if preferred in normalized:
            return len(normalized_preferred) - idx
    return 0


def sort_sheet_items(sheets: dict[str, pd.DataFrame], import_type: str) -> list[tuple[str, pd.DataFrame]]:
    return sorted(sheets.items(), key=lambda item: score_sheet_name(item[0], import_type), reverse=True)


def parse_time_tokens(raw_value: str | None) -> list:
    if raw_value is None or pd.isna(raw_value):
        return []
    text = str(raw_value).replace("*", " ").replace("\n", " ").replace(";", ",")
    tokens = [m.group(0) for m in TIME_PATTERN.finditer(text)]
    parsed = []
    for token in tokens:
        try:
            parsed.append(datetime.strptime(token, "%H:%M").time())
        except ValueError:
            continue
    parsed.sort()
    return parsed


def stringify_cell(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    return str(value).strip()


def parse_detected_period_date(value: str) -> date | None:
    """Parse the two common date formats used in timekeeping workbook headings."""
    normalized = value.replace(".", "-").replace("/", "-")
    formats = ("%Y-%m-%d", "%d-%m-%Y")
    for date_format in formats:
        try:
            return datetime.strptime(normalized, date_format).date()
        except ValueError:
            continue
    return None


def detect_report_period(df: pd.DataFrame) -> tuple[date | None, date | None]:
    """Find a date range in a report heading, preferring the standard 23 → 22 payroll cycle."""
    max_scan_rows = min(len(df), 16)
    fallback: tuple[date, date] | None = None

    for row_index in range(max_scan_rows):
        row_text = " ".join(stringify_cell(value) for value in df.iloc[row_index].tolist())
        date_tokens = PERIOD_DATE_PATTERN.findall(row_text)
        parsed_dates = [parsed for token in date_tokens if (parsed := parse_detected_period_date(token)) is not None]
        for start, end in zip(parsed_dates, parsed_dates[1:]):
            if start > end:
                continue
            if start.day == 23 and end.day == 22:
                return start, end
            if fallback is None:
                fallback = (start, end)

    return fallback if fallback is not None else (None, None)


def normalize_header_text(value: str | None) -> str:
    if value is None:
        return ""
    text = str(value).strip().lower()
    text = unicodedata.normalize("NFD", text)
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def header_cell_matches(cell_value: str, candidate_key: str) -> bool:
    if not cell_value or not candidate_key:
        return False
    if cell_value == candidate_key:
        return True
    if len(candidate_key) >= 3 and candidate_key in cell_value:
        return True
    if len(cell_value) >= 3 and cell_value in candidate_key:
        return True
    return False


def required_match_count(mapping: dict[str, int], import_type: str) -> int:
    required = required_columns_for_import(import_type)
    return sum(1 for field in required if field in mapping)


def has_complete_required_mapping(mapping: dict[str, int], import_type: str) -> bool:
    if required_match_count(mapping, import_type) != len(required_columns_for_import(import_type)):
        return False
    if import_type == "checkin":
        return any(field in mapping for field in ["Moc gio", "In", "Out"])
    return True


def get_best_preview_header_row_index(df: pd.DataFrame) -> int:
    best_row_index = 0
    best_score = -1
    max_scan_rows = min(len(df), 30)
    for row_idx in range(max_scan_rows):
        row_values = [stringify_cell(value) for value in df.iloc[row_idx].tolist()]
        non_empty_values = [value for value in row_values if value]
        if not non_empty_values:
            continue

        text_like_count = sum(1 for value in non_empty_values if re.search(r"[A-Za-zÀ-ỹà-ỹ]", value))
        compact_value_count = sum(1 for value in non_empty_values if len(value) <= 24)
        day_like_count = sum(1 for value in non_empty_values if re.fullmatch(r"\d{1,2}(?:\s+(?:T7|CN))?", value, re.IGNORECASE))
        long_text_penalty = sum(1 for value in non_empty_values if len(value) > 36)
        score = len(non_empty_values) * 6 + text_like_count * 2 + compact_value_count + day_like_count * 2 - long_text_penalty * 4
        if score > best_score:
            best_score = score
            best_row_index = row_idx

    return best_row_index


def build_effective_header_values(df: pd.DataFrame, header_row_index: int) -> list[str]:
    if df.empty:
        return []

    effective_values: list[str] = []
    max_lookup_rows = 2
    for col_idx in range(df.shape[1]):
        chosen_value = ""
        for row_idx in range(header_row_index, max(-1, header_row_index - max_lookup_rows) - 1, -1):
            if row_idx < 0 or row_idx >= len(df):
                continue
            cell_value = stringify_cell(df.iat[row_idx, col_idx])
            if cell_value:
                chosen_value = cell_value
                break
        effective_values.append(chosen_value)
    return effective_values


def detect_mapping_from_row_values(row_values: list[Any], import_type: str) -> dict[str, int]:
    aliases = HEADER_ALIASES[import_type]
    normalized_values = [normalize_header_text(v) for v in row_values]
    current_mapping: dict[str, int] = {}

    for target_col, candidates in aliases.items():
        candidate_keys = [normalize_header_text(c) for c in candidates]
        for col_idx, cell_value in enumerate(normalized_values):
            if not cell_value or target_col in current_mapping:
                continue
            if any(header_cell_matches(cell_value, candidate_key) for candidate_key in candidate_keys):
                current_mapping[target_col] = col_idx
                break

    return current_mapping


def detect_header_mapping(df: pd.DataFrame, import_type: str) -> tuple[int | None, dict[str, int]]:
    best_row_idx: int | None = None
    best_mapping: dict[str, int] = {}
    best_required_matches = -1

    max_scan_rows = min(len(df), 30)
    for row_idx in range(max_scan_rows):
        row_values = build_effective_header_values(df, row_idx)
        current_mapping = detect_mapping_from_row_values(row_values, import_type)
        current_required_matches = required_match_count(current_mapping, import_type)

        if current_required_matches > best_required_matches or (
            current_required_matches == best_required_matches and len(current_mapping) > len(best_mapping)
        ):
            best_mapping = current_mapping
            best_row_idx = row_idx
            best_required_matches = current_required_matches

        if has_complete_required_mapping(current_mapping, import_type):
            return row_idx, current_mapping

    if best_required_matches > 0:
        return best_row_idx, best_mapping
    return None, best_mapping


def preprocess_import_dataframe(df: pd.DataFrame, import_type: str) -> pd.DataFrame:
    header_row_idx, mapping = detect_header_mapping(df, import_type)
    required_columns = required_columns_for_import(import_type)
    missing = [col for col in required_columns if col not in mapping]
    if header_row_idx is None or missing:
        raise HTTPException(status_code=400, detail=f"Missing required columns: {', '.join(missing or required_columns)}")

    result = pd.DataFrame()
    columns_to_extract = list(required_columns)
    if import_type == "checkin":
        for opt_col in ["Moc gio", "In", "Out"]:
            if opt_col in mapping and opt_col not in columns_to_extract:
                columns_to_extract.append(opt_col)

    for col in columns_to_extract:
        result[col] = df.iloc[header_row_idx + 1 :, mapping[col]].reset_index(drop=True)

    # Bo cac dong trong hoan toan sau khi cat header.
    result = result.dropna(how="all")
    return result


def get_first_nonempty_row_index(df: pd.DataFrame) -> int:
    max_scan_rows = min(len(df), 30)
    for row_idx in range(max_scan_rows):
        row_values = [stringify_cell(value) for value in df.iloc[row_idx].tolist()]
        if any(row_values):
            return row_idx
    return 0


def find_first_sample_value(df: pd.DataFrame, header_row_index: int, column_index: int) -> str:
    max_scan_rows = min(len(df), header_row_index + 11)
    for row_idx in range(header_row_index + 1, max_scan_rows):
        if column_index >= df.shape[1]:
            return ""
        value = stringify_cell(df.iat[row_idx, column_index])
        if value:
            return value
    return ""


def get_column_letter(col_idx: int) -> str:
    letter = ""
    while col_idx >= 0:
        letter = chr(col_idx % 26 + 65) + letter
        col_idx = col_idx // 26 - 1
    return letter


def build_column_options(df: pd.DataFrame, header_row_index: int) -> list[WorkbookColumnOption]:
    raw_values = build_effective_header_values(df, header_row_index)
    options: list[WorkbookColumnOption] = []
    for index, value in enumerate(raw_values):
        col_letter = get_column_letter(index)
        header_text = stringify_cell(value) or "Trống"
        
        # Lấy giá trị mẫu của cột dưới dòng tiêu đề
        sample_hint = find_first_sample_value(df, header_row_index, index)
        hint_text = ""
        if sample_hint:
            shortened = sample_hint.replace("\n", " | ")
            if len(shortened) > 24:
                shortened = f"{shortened[:21]}..."
            hint_text = f" (Mẫu: {shortened})"
            
        display_label = f"Cột {col_letter} | {header_text}{hint_text}"
        options.append(WorkbookColumnOption(index=index, label=header_text, display_label=display_label))
    return options


def build_row_records(
    df: pd.DataFrame,
    header_row_index: int,
    columns: list[WorkbookColumnOption],
    limit: int | None = None,
) -> list[dict[str, str]]:
    sample_df = df.iloc[header_row_index + 1 :]
    rows: list[dict[str, str]] = []
    for _, sample_row in sample_df.iterrows():
        item: dict[str, str] = {}
        has_value = False
        for column in columns:
            value = stringify_cell(sample_row.iloc[column.index]) if column.index < len(sample_row) else ""
            if value:
                has_value = True
            item[column.label] = value
        if has_value:
            rows.append(item)
            if limit is not None and len(rows) >= limit:
                break
    return rows


def split_raw_time_values(raw_value: Any) -> list[str]:
    text = stringify_cell(raw_value)
    if not text:
        return []
    parts = [segment.strip() for segment in re.split(r"[\n,;]+", text) if segment.strip()]
    return parts


def is_checkin_day_row(row_values: list[str]) -> bool:
    non_empty_values = [value for value in row_values if value]
    if len(non_empty_values) < 6:
        return False
    day_like_count = sum(1 for value in non_empty_values if re.fullmatch(r"\d{1,2}", value))
    return day_like_count >= 6 and day_like_count >= len(non_empty_values) // 2


def is_checkin_employee_meta_row(row_values: list[str]) -> bool:
    normalized_values = {normalize_header_text(value) for value in row_values if value}
    return "id" in normalized_values and "ten" in normalized_values and "p ban" in normalized_values


def find_value_after_label(row_values: list[str], accepted_labels: set[str]) -> str:
    normalized_values = [normalize_header_text(value) for value in row_values]
    for index, normalized_value in enumerate(normalized_values):
        if normalized_value in accepted_labels:
            for next_index in range(index + 1, len(row_values)):
                candidate = stringify_cell(row_values[next_index])
                if candidate:
                    return candidate
    return ""


def build_checkin_day_entries(day_row_values: list[str], time_row_values: list[str]) -> list[RawCheckinDayEntry]:
    entries: list[RawCheckinDayEntry] = []
    max_columns = min(len(day_row_values), len(time_row_values))
    for column_index in range(max_columns):
        day_label = stringify_cell(day_row_values[column_index])
        if not re.fullmatch(r"\d{1,2}", day_label):
            continue
        time_values = split_raw_time_values(time_row_values[column_index])
        if not time_values:
            continue
        entries.append(RawCheckinDayEntry(day_label=day_label, time_values=time_values))
    return entries


def build_checkin_employee_blocks(df: pd.DataFrame) -> list[RawCheckinEmployeeBlock]:
    blocks: list[RawCheckinEmployeeBlock] = []
    if df.empty:
        return blocks

    total_rows = len(df)
    for row_index in range(max(total_rows - 2, 0)):
        day_row_values = [stringify_cell(value) for value in df.iloc[row_index].tolist()]
        meta_row_values = [stringify_cell(value) for value in df.iloc[row_index + 1].tolist()]
        time_row_values = [stringify_cell(value) for value in df.iloc[row_index + 2].tolist()]

        if not is_checkin_day_row(day_row_values) or not is_checkin_employee_meta_row(meta_row_values):
            continue

        employee_id = clean_machine_id(find_value_after_label(meta_row_values, {"id"}))
        employee_name = find_value_after_label(meta_row_values, {"ten"})
        department_name = find_value_after_label(meta_row_values, {"p ban", "phong ban"})
        day_entries = build_checkin_day_entries(day_row_values, time_row_values)

        if not employee_id and not employee_name and not department_name and not day_entries:
            continue

        blocks.append(
            RawCheckinEmployeeBlock(
                employee_id=employee_id,
                employee_name=employee_name,
                department_name=department_name,
                day_entries=day_entries,
                row_start_index=row_index,
                row_end_index=min(row_index + 2, total_rows - 1),
            )
        )

    # Một nhân viên có thể xuất hiện ở nhiều block trong cùng sheet (máy xuất
    # báo cáo theo từng đoạn). Gộp theo ID/ngày ngay từ preview để UI và bước
    # commit chỉ tính một lần, đồng thời giữ đủ mọi mốc quẹt.
    merged: dict[str, RawCheckinEmployeeBlock] = {}
    for block in blocks:
        current = merged.get(block.employee_id)
        if current is None:
            merged[block.employee_id] = block.model_copy(deep=True)
            continue

        if not current.employee_name and block.employee_name:
            current.employee_name = block.employee_name
        if (not current.department_name or current.department_name.lower().startswith("not set")) and block.department_name:
            current.department_name = block.department_name
        current.row_start_index = min(current.row_start_index, block.row_start_index)
        current.row_end_index = max(current.row_end_index, block.row_end_index)

        day_map = {entry.day_label: entry for entry in current.day_entries}
        for entry in block.day_entries:
            existing = day_map.get(entry.day_label)
            if existing is None:
                copied = entry.model_copy(deep=True)
                current.day_entries.append(copied)
                day_map[entry.day_label] = copied
                continue
            combined = list(dict.fromkeys([*existing.time_values, *entry.time_values]))
            existing.time_values = sorted(
                combined,
                key=lambda value: (parse_time_tokens(value)[0] if parse_time_tokens(value) else datetime.max.time()),
            )

        current.day_entries.sort(key=lambda entry: int(entry.day_label))

    return list(merged.values())


def detect_time_like_columns(df: pd.DataFrame, header_row_index: int) -> set[int]:
    time_like_columns: set[int] = set()
    max_scan_rows = min(len(df), header_row_index + 16)
    for row_idx in range(header_row_index + 1, max_scan_rows):
        for col_idx in range(df.shape[1]):
            if col_idx in time_like_columns:
                continue
            cell_value = stringify_cell(df.iat[row_idx, col_idx])
            if parse_time_tokens(cell_value):
                time_like_columns.add(col_idx)
    return time_like_columns


def inspect_sheet(
    df: pd.DataFrame,
    sheet_name: str,
    import_type: str,
    forced_header_row_index: int | None = None,
    include_raw_rows: bool = False,
) -> WorkbookSheetInspection:
    detected_header_row_index, detected_mapping = detect_header_mapping(df, import_type)
    fallback_row_index = (
        detected_header_row_index
        if detected_header_row_index is not None and required_match_count(detected_mapping, import_type) > 0
        else get_best_preview_header_row_index(df)
    )
    header_row_index = forced_header_row_index if forced_header_row_index is not None else fallback_row_index
    header_row_index = min(max(header_row_index, 0), max(len(df) - 1, 0))
    effective_header_values = build_effective_header_values(df, header_row_index)
    suggested_mapping = detect_mapping_from_row_values(effective_header_values, import_type)
    columns = build_column_options(df, header_row_index)
    time_like_columns = detect_time_like_columns(df, header_row_index)
    raw_rows = build_row_records(df, header_row_index, columns) if include_raw_rows else []
    sample_rows = raw_rows[:5] if raw_rows else build_row_records(df, header_row_index, columns, limit=5)
    employee_blocks = build_checkin_employee_blocks(df) if include_raw_rows and import_type == "checkin" else []
    period_start, period_end = detect_report_period(df) if import_type == "checkin" else (None, None)
    return WorkbookSheetInspection(
        sheet_name=sheet_name,
        header_row_index=header_row_index,
        columns=columns,
        suggested_mapping={key: value for key, value in suggested_mapping.items()},
        match_score=len(suggested_mapping),
        has_time_columns=any(key in suggested_mapping for key in ["Moc gio", "In", "Out"]) or bool(time_like_columns),
        sample_rows=sample_rows,
        raw_rows=raw_rows,
        data_row_count=len(raw_rows) if include_raw_rows else len(sample_rows),
        employee_blocks=employee_blocks,
        period_start=period_start.isoformat() if period_start else None,
        period_end=period_end.isoformat() if period_end else None,
    )


def inspect_workbook_source(dataframe_source: Any, import_type: str) -> WorkbookInspectionResponse:
    sheets: list[WorkbookSheetInspection] = []
    if isinstance(dataframe_source, pd.DataFrame):
        sheets = [inspect_sheet(dataframe_source, "CSV", import_type)]
    elif isinstance(dataframe_source, dict):
        for sheet_name, sheet_df in sort_sheet_items(dataframe_source, import_type):
            if sheet_df is None or sheet_df.empty:
                continue
            sheets.append(inspect_sheet(sheet_df, sheet_name, import_type))
    else:
        raise HTTPException(status_code=400, detail="Unsupported file content")

    if not sheets:
        raise HTTPException(status_code=400, detail="Workbook does not contain readable sheets")

    sheets.sort(
        key=lambda sheet: (
            1 if has_complete_required_mapping(sheet.suggested_mapping, import_type) else 0,
            required_match_count(sheet.suggested_mapping, import_type),
            score_sheet_name(sheet.sheet_name, import_type),
            1 if sheet.has_time_columns else 0,
            sheet.match_score,
        ),
        reverse=True,
    )
    recommended = next((sheet for sheet in sheets if has_complete_required_mapping(sheet.suggested_mapping, import_type)), None)
    return WorkbookInspectionResponse(
        import_type=import_type,  # type: ignore[arg-type]
        sheets=sheets,
        recommended_sheet_name=recommended.sheet_name if recommended else None,
        recommended_header_row_index=recommended.header_row_index if recommended else None,
        recommended_mapping=recommended.suggested_mapping if recommended else {},
    )


def select_best_sheet_dataframe(sheets: dict[str, pd.DataFrame], import_type: str) -> pd.DataFrame:
    best_required_matches = -1
    best_total_score = -1
    best_name: str | None = None
    best_df: pd.DataFrame | None = None

    sheet_items = sort_sheet_items(sheets, import_type)

    for sheet_name, sheet_df in sheet_items:
        if sheet_df is None or sheet_df.empty:
            continue
        _, mapping = detect_header_mapping(sheet_df, import_type)
        required_matches = required_match_count(mapping, import_type)
        total_score = len(mapping)
        if required_matches > best_required_matches or (
            required_matches == best_required_matches and total_score > best_total_score
        ):
            best_required_matches = required_matches
            best_total_score = total_score
            best_name = sheet_name
            best_df = sheet_df
        if has_complete_required_mapping(mapping, import_type):
            best_name = sheet_name
            best_df = sheet_df
            break

    if best_df is None:
        raise HTTPException(status_code=400, detail="Workbook does not contain readable sheets")

    if not has_complete_required_mapping(detect_header_mapping(best_df, import_type)[1], import_type):
        required_columns = required_columns_for_import(import_type)
        missing = [col for col in required_columns if col not in detect_header_mapping(best_df, import_type)[1]]
        target = best_name or "unknown"
        raise HTTPException(
            status_code=400,
            detail=f"Missing required columns: {', '.join(missing)} (best sheet: {target})",
        )

    return best_df


def resolve_import_dataframe(dataframe_source: Any, import_type: str) -> pd.DataFrame:
    if isinstance(dataframe_source, pd.DataFrame):
        return preprocess_import_dataframe(dataframe_source, import_type)
    if isinstance(dataframe_source, dict):
        if import_type == "checkin":
            candidates: list[pd.DataFrame] = []
            for sheet_name, sheet_df in sort_sheet_items(dataframe_source, import_type):
                if sheet_df is None or sheet_df.empty:
                    continue
                try:
                    parsed = preprocess_import_dataframe(sheet_df, import_type)
                except HTTPException:
                    continue

                parsed = parsed.copy()
                has_time_columns = any(col in parsed.columns for col in ["Moc gio", "In", "Out"])
                parsed["_sheet_name_score"] = score_sheet_name(sheet_name, import_type)
                parsed["_time_col_score"] = 1 if has_time_columns else 0
                candidates.append(parsed)

            if not candidates:
                selected = select_best_sheet_dataframe(dataframe_source, import_type)
                return preprocess_import_dataframe(selected, import_type)

            # Neu co it nhat 1 sheet co cot gio, bo qua cac sheet khong co gio de tranh sai nguon tong hop.
            if any(int(df["_time_col_score"].iloc[0]) > 0 for df in candidates):
                candidates = [df for df in candidates if int(df["_time_col_score"].iloc[0]) > 0]

            combined = pd.concat(candidates, ignore_index=True, sort=False)
            combined["ID"] = combined["ID"].astype(str).str.strip()
            combined["Ten"] = combined["Ten"].astype(str).str.strip()
            combined["Ngay"] = combined["Ngay"].astype(str).str.strip()
            combined = combined[(combined["ID"] != "") & (combined["Ten"] != "") & (combined["Ngay"] != "")]

            combined["_dedupe_key"] = combined["ID"] + "|" + combined["Ten"] + "|" + combined["Ngay"]
            combined = combined.sort_values(["_dedupe_key", "_time_col_score", "_sheet_name_score"], ascending=[True, False, False])
            combined = combined.drop_duplicates(subset=["_dedupe_key"], keep="first")
            combined = combined.drop(columns=["_dedupe_key", "_time_col_score", "_sheet_name_score"])
            return combined.reset_index(drop=True)

        selected = select_best_sheet_dataframe(dataframe_source, import_type)
        return preprocess_import_dataframe(selected, import_type)
    raise HTTPException(status_code=400, detail="Unsupported file content")


def resolve_sheet_dataframe(dataframe_source: Any, sheet_name: str | None, import_type: str) -> pd.DataFrame:
    if isinstance(dataframe_source, pd.DataFrame):
        return dataframe_source
    if isinstance(dataframe_source, dict):
        if sheet_name and sheet_name in dataframe_source:
            return dataframe_source[sheet_name]
        if sheet_name:
            raise HTTPException(status_code=400, detail=f"sheet_name not found: {sheet_name}")
        return select_best_sheet_dataframe(dataframe_source, import_type)
    raise HTTPException(status_code=400, detail="Unsupported file content")


def build_custom_mapped_dataframe(
    df: pd.DataFrame,
    import_type: str,
    header_row_index: int,
    column_mapping: dict[str, int],
) -> pd.DataFrame:
    if header_row_index < 0 or header_row_index >= len(df):
        raise HTTPException(status_code=400, detail="header_row_index out of range")

    required_columns = required_columns_for_import(import_type)
    missing = [column for column in required_columns if column not in column_mapping]
    if missing:
        raise HTTPException(status_code=400, detail=f"Missing required mapping: {', '.join(missing)}")

    allowed_columns = set(HEADER_ALIASES[import_type].keys())
    result = pd.DataFrame()
    for canonical_name, column_index in column_mapping.items():
        if canonical_name not in allowed_columns:
            continue
        if column_index < 0 or column_index >= df.shape[1]:
            raise HTTPException(status_code=400, detail=f"column index out of range for {canonical_name}")
        result[canonical_name] = df.iloc[header_row_index + 1 :, column_index].reset_index(drop=True)

    return result.dropna(how="all")


def normalize_daily_check(raw_time_cell: str | None) -> tuple:
    times = parse_time_tokens(raw_time_cell)
    if len(times) == 0:
        return None, None, True, "missing_all"
    if len(times) == 1:
        return times[0], None, True, "missing_checkout"
    return times[0], times[-1], False, None


def normalize_single_time(raw_value: str | None) -> str | None:
    tokens = parse_time_tokens(raw_value)
    if not tokens:
        return None
    return tokens[0].strftime("%H:%M")


def parse_minutes(value: str | None) -> int:
    if value is None or pd.isna(value):
        return 0
    match = re.search(r"(\d+)", str(value))
    return int(match.group(1)) if match else 0


def detect_bo_lo(note_value: str | None) -> bool:
    if note_value is None or pd.isna(note_value):
        return False
    note = str(note_value).strip().lower()
    return "bo lo" in note or "bo lo" in note.replace("ỏ", "o").replace("ỡ", "o")


def resolve_period_for_work_date(day: date) -> tuple[date, date]:
    if day.day >= 23:
        start = date(day.year, day.month, 23)
        end = date(day.year + (1 if day.month == 12 else 0), 1 if day.month == 12 else day.month + 1, 22)
    else:
        start = date(day.year - (1 if day.month == 1 else 0), 12 if day.month == 1 else day.month - 1, 23)
        end = date(day.year, day.month, 22)
    return start, end


def parse_work_date_value(value: Any) -> date | None:
    text = stringify_cell(value)
    if not text:
        return None
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    try:
        return pd.to_datetime(text, dayfirst=True).date()
    except Exception:
        return None


def load_dataframe(upload: UploadFile) -> Any:
    if not upload.filename:
        raise HTTPException(status_code=400, detail="Missing filename")
    data = upload.file.read()
    name = upload.filename.lower()
    if name.endswith(".csv"):
        return pd.read_csv(BytesIO(data), dtype=str, header=None)
    if name.endswith(".xlsx") or name.endswith(".xls") or name.endswith(".xlsm"):
        return pd.read_excel(BytesIO(data), dtype=str, header=None, sheet_name=None)
    raise HTTPException(status_code=400, detail="Only CSV/XLS/XLSX are supported")


def build_checkin_preview(df: pd.DataFrame) -> dict[str, Any]:
    rows = []
    for _, row in df.iterrows():
        work_date = parse_work_date_value(row.get("Ngay"))
        if not work_date:
            continue
        if pd.notna(row.get("Moc gio")) and str(row.get("Moc gio")).strip():
            check_in, check_out, missing_flag, missing_reason = normalize_daily_check(row.get("Moc gio"))
            raw_values = str(row.get("Moc gio", "")).strip()
        else:
            check_in_text = normalize_single_time(row.get("In"))
            check_out_text = normalize_single_time(row.get("Out"))
            check_in = datetime.strptime(check_in_text, "%H:%M").time() if check_in_text else None
            check_out = datetime.strptime(check_out_text, "%H:%M").time() if check_out_text else None

            if check_in and check_out:
                missing_flag = False
                missing_reason = None
            elif check_in and not check_out:
                missing_flag = True
                missing_reason = "missing_checkout"
            elif not check_in and check_out:
                missing_flag = True
                missing_reason = "missing_checkin"
            else:
                missing_flag = True
                missing_reason = "missing_all"

            raw_values = f"IN={str(row.get('In', '')).strip()};OUT={str(row.get('Out', '')).strip()}"

        period_start, period_end = resolve_period_for_work_date(work_date)
        rows.append(
            {
                "machine_employee_id": clean_machine_id(row.get("ID")),
                "full_name": str(row.get("Ten", "")).strip(),
                "work_date": work_date.isoformat(),
                "raw_time_values": raw_values,
                "check_in_time": check_in.strftime("%H:%M") if check_in else None,
                "check_out_time": check_out.strftime("%H:%M") if check_out else None,
                "missing_flag": missing_flag,
                "missing_reason": missing_reason,
                "period_start": period_start.isoformat(),
                "period_end": period_end.isoformat(),
            }
        )

    return {"rows": len(rows), "preview": rows[:50]}


def build_abnormal_preview(df: pd.DataFrame) -> dict[str, Any]:
    rows = []
    for _, row in df.iterrows():
        work_date = parse_work_date_value(row.get("Ngay"))
        if not work_date:
            continue
        period_start, period_end = resolve_period_for_work_date(work_date)
        bo_lo = detect_bo_lo(row.get("Ghi chu"))
        rows.append(
            {
                "machine_employee_id": clean_machine_id(row.get("ID")),
                "full_name": str(row.get("Ten", "")).strip(),
                "department_name": str(row.get("P.Ban", "")).strip(),
                "work_date": work_date.isoformat(),
                "late_minutes": parse_minutes(row.get("Thoi gian tre")),
                "early_minutes": parse_minutes(row.get("Thoi gian som")),
                "missing_flag": bo_lo,
                "missing_reason": "bo_lo" if bo_lo else None,
                "note": str(row.get("Ghi chu", "")).strip(),
                "period_start": period_start.isoformat(),
                "period_end": period_end.isoformat(),
            }
        )

    return {"rows": len(rows), "preview": rows[:50]}


def build_preview_payload(df: pd.DataFrame, import_type: str) -> dict[str, Any]:
    if import_type == "checkin":
        return build_checkin_preview(df)
    return build_abnormal_preview(df)


@router.post("/import/workbook-inspect", response_model=WorkbookInspectionResponse)
async def inspect_workbook(
    file: UploadFile = File(...),
    import_type: str = Form(...),
) -> WorkbookInspectionResponse:
    normalized_import_type = normalize_import_type(import_type)
    return inspect_workbook_source(load_dataframe(file), normalized_import_type)


@router.post("/import/custom-preview")
async def import_custom_preview(
    file: UploadFile = File(...),
    import_type: str = Form(...),
    sheet_name: str | None = Form(default=None),
    header_row_index: int = Form(...),
    column_mapping_json: str = Form(...),
) -> dict[str, Any]:
    normalized_import_type = normalize_import_type(import_type)
    try:
        raw_mapping = json.loads(column_mapping_json)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="column_mapping_json is invalid JSON") from exc
    if not isinstance(raw_mapping, dict):
        raise HTTPException(status_code=400, detail="column_mapping_json must be an object")

    column_mapping: dict[str, int] = {}
    for key, value in raw_mapping.items():
        if key in HEADER_ALIASES[normalized_import_type]:
            column_mapping[key] = int(value)

    source = load_dataframe(file)
    df = resolve_sheet_dataframe(source, sheet_name, normalized_import_type)
    mapped_df = build_custom_mapped_dataframe(df, normalized_import_type, header_row_index, column_mapping)
    return build_preview_payload(mapped_df, normalized_import_type)


@router.post("/import/sheet-inspect", response_model=WorkbookSheetInspection)
async def inspect_workbook_sheet(
    file: UploadFile = File(...),
    import_type: str = Form(...),
    sheet_name: str | None = Form(default=None),
    header_row_index: int = Form(...),
) -> WorkbookSheetInspection:
    normalized_import_type = normalize_import_type(import_type)
    source = load_dataframe(file)
    df = resolve_sheet_dataframe(source, sheet_name, normalized_import_type)
    return inspect_sheet(
        df,
        sheet_name or "CSV",
        normalized_import_type,
        forced_header_row_index=header_row_index,
        include_raw_rows=True,
    )


@router.post("/import/checkin-profile")
async def import_checkin_profile(file: UploadFile = File(...)) -> dict:
    return build_checkin_preview(resolve_import_dataframe(load_dataframe(file), "checkin"))


@router.post("/import/abnormal-report")
async def import_abnormal_report(file: UploadFile = File(...)) -> dict:
    return build_abnormal_preview(resolve_import_dataframe(load_dataframe(file), "abnormal"))


@router.post("/import/attendance-json")
async def import_attendance_json(
    file: UploadFile = File(...),
    notion_file: UploadFile | None = File(default=None),
    period_start: str | None = Form(default=None),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    period_start_date = None
    if period_start:
        period_start_date = parse_work_date_value(period_start)
        if period_start_date is None:
            raise HTTPException(status_code=400, detail="period_start must be a valid date")

    try:
        payload = file.file.read()
        parser = AttendanceParser()
        employees = parser.parse(payload, period_start=period_start_date)
        employees = _apply_employee_report_metadata(employees, _build_employee_report_directory(db))
        report_period_start = parser.last_period_start
        report_period_end = parser.last_period_end
        if notion_file is not None:
            notion_payload = notion_file.file.read()
            if notion_payload:
                employees = reconcile_attendance_with_notion(
                    employees,
                    notion_payload,
                    _build_notion_employee_directory(db),
                    period_start=report_period_start,
                    period_end=report_period_end,
                )
                from app.services.notion_leave_reconciliation import (
                    save_notion_leaves_to_db,
                    sync_notion_work_from_home_to_attendance_db,
                )
                save_notion_leaves_to_db(
                    db,
                    notion_payload,
                    _build_notion_employee_directory(db),
                    period_start=report_period_start,
                    period_end=report_period_end,
                )
                sync_notion_work_from_home_to_attendance_db(
                    db,
                    notion_payload,
                    _build_notion_employee_directory(db),
                    period_start=report_period_start,
                    period_end=report_period_end,
                )
    except OperationalError as exc:
        raise HTTPException(status_code=503, detail="database is unavailable") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Không parse được workbook 5 sheet: {exc}") from exc

    return {
        "employees": employees,
        "validation_summary": parser.last_validation_summary,
    }
