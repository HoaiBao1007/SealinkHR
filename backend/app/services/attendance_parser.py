from __future__ import annotations

import argparse
import json
import re
import unicodedata
from collections import Counter
from datetime import date, datetime, timedelta
from io import BytesIO
from pathlib import Path
from typing import Any

import pandas as pd


TIME_PATTERN = re.compile(r"(?:[01]?\d|2[0-3]):[0-5]\d")
INTEGER_PATTERN = re.compile(r"-?\d+")

SHEET_ALIASES = {
    "schedule": ["bang thong tin lich trinh", "bảng thông tin lịch trình"],
    "checkin_report": ["bao cao check in", "báo cáo check-in", "báo cáo check in"],
    "abnormal": ["bao cao bat thuong", "báo cáo bất thường"],
    "profile": ["ho so check in", "hồ sơ check-in", "hồ sơ check in"],
    "summary": ["bang tom tat check in", "bảng tóm tắt check-in", "bảng tóm tắt check in"],
}

FIELD_ALIASES = {
    "employee_id": ["id", "ma nv", "mã nv", "ma nhan vien", "mã nhân viên", "machine id", "machine employee id"],
    "employee_name": ["ten", "họ tên", "ho ten", "họ và tên", "ten nhan vien", "ho va ten nhan vien"],
    "department": ["phong ban", "phòng ban", "department", "bo phan", "bộ phận", "p ban"],
    "work_date": ["ngay", "ngày", "date", "work date", "ngay lam viec", "ngày làm việc"],
    "check_in": ["gio vao", "giờ vào", "vao lam", "vào làm", "buoi 1 vao lam", "buổi 1 vào làm", "check in", "in"],
    "check_out": ["gio ra", "giờ ra", "ra nghi", "ra nghỉ", "buoi 1 ra nghi", "buổi 1 ra nghỉ", "check out", "out"],
    "raw_times": ["moc gio", "mốc giờ", "du lieu quet", "dữ liệu quẹt", "scan data", "gio quet", "giờ quét"],
    "late_minutes": ["thoi gian tre", "thời gian trễ", "di muon", "đi muộn", "late minutes", "late"],
    "early_minutes": ["thoi gian som", "thời gian sớm", "ve som", "về sớm", "early minutes", "early"],
    "total_late_minutes": [
        "tong so phut di muon trong thang",
        "tổng số phút đi muộn trong tháng",
        "tong phut di muon",
        "tổng phút đi muộn",
        "total late minutes",
        "di muon phut",
        "đi muộn phút",
    ],
    "total_absent_days": [
        "tong so ngay vang mat",
        "tổng số ngày vắng mặt",
        "so ngay vang",
        "số ngày vắng",
        "total absent days",
        "vang mat",
        "vắng mặt",
    ],
}

HEADER_STOP_WORDS = {"id", "ten", "ho ten", "phong ban", "department", "ngay", "date"}


def normalize_text(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    text = str(value).strip().lower()
    text = unicodedata.normalize("NFD", text)
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    text = re.sub(r"[^a-z0-9:]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def safe_str(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    return str(value).strip()


def parse_int(value: Any) -> int:
    if value is None or pd.isna(value):
        return 0
    match = INTEGER_PATTERN.search(str(value))
    return int(match.group(0)) if match else 0


def parse_time_tokens(raw_value: Any) -> list[str]:
    if raw_value is None or pd.isna(raw_value):
        return []
    text = str(raw_value).replace("*", " ").replace("\n", " ").replace(";", " ")
    return sorted({match.group(0) for match in TIME_PATTERN.finditer(text)})


def min_max_times(raw_value: Any) -> tuple[str | None, str | None]:
    tokens = parse_time_tokens(raw_value)
    if not tokens:
        return None, None
    if len(tokens) == 1:
        return tokens[0], None
    return tokens[0], tokens[-1]


def merge_attendance_times(target: dict[str, Any], *time_values: str | None) -> None:
    """Merge punches from repeated tables into one first-in/last-out pair."""
    punches = {
        value
        for value in [target.get("check_in"), target.get("check_out"), *time_values]
        if value
    }
    if not punches:
        return
    ordered = sorted(punches)
    target["check_in"] = ordered[0]
    target["check_out"] = ordered[-1] if len(ordered) > 1 else None
    target["has_raw_data"] = True


def parse_single_time(raw_value: Any) -> str | None:
    tokens = parse_time_tokens(raw_value)
    return tokens[0] if tokens else None


def contains_missing_punch(value: Any) -> bool:
    normalized = normalize_text(value)
    return "bo lo" in normalized if normalized else False


def parse_date_value(value: Any) -> date | None:
    if value is None or pd.isna(value):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = safe_str(value)
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    try:
        return pd.to_datetime(text, dayfirst=True, errors="raise").date()
    except Exception:
        return None


def parse_date_range_values(value: Any) -> list[date]:
    text = safe_str(value)
    if not text:
        return []
    matches = re.findall(r"\d{4}-\d{2}-\d{2}|\d{2}/\d{2}/\d{4}|\d{2}-\d{2}-\d{4}", text)
    results: list[date] = []
    for match in matches:
        parsed = parse_date_value(match)
        if parsed is not None:
            results.append(parsed)
    return results


def parse_day_number(value: Any) -> int | None:
    if value is None or pd.isna(value):
        return None
    parsed_date = parse_date_value(value)
    if parsed_date:
        return parsed_date.day
    if isinstance(value, (int, float)) and not pd.isna(value):
        integer_value = int(value)
        if float(value) == float(integer_value) and 1 <= integer_value <= 31:
            return integer_value
    text = safe_str(value)
    if re.fullmatch(r"\d{1,2}", text):
        integer_value = int(text)
        if 1 <= integer_value <= 31:
            return integer_value
    return None


def header_value_matches(cell_value: Any, aliases: list[str]) -> bool:
    normalized_cell = normalize_text(cell_value)
    if not normalized_cell:
        return False
    normalized_aliases = [normalize_text(alias) for alias in aliases]
    for alias in normalized_aliases:
        if not alias:
            continue
        if normalized_cell == alias:
            return True
        if len(alias) >= 3 and alias in normalized_cell:
            return True
    return False


class AttendanceParser:
    def __init__(self) -> None:
        self.last_validation_summary: dict[str, dict[str, int | bool]] = {}
        self.last_period_start: date | None = None
        self.last_period_end: date | None = None

    def parse(self, source: str | Path | bytes | BytesIO, period_start: date | None = None) -> list[dict[str, Any]]:
        workbook = self._load_workbook(source)
        sheet_frames = self._resolve_required_sheets(workbook)

        report_payload = self._parse_checkin_report_sheet(sheet_frames["checkin_report"])
        abnormal_payload = self._parse_abnormal_sheet(sheet_frames["abnormal"])
        cycle_start, cycle_end = self._resolve_cycle_bounds(
            explicit_period_start=period_start,
            reference_dates=report_payload["reference_dates"] + abnormal_payload["reference_dates"],
            extra_dataframes=[sheet_frames["profile"], sheet_frames["schedule"]],
        )
        self.last_period_start = cycle_start
        self.last_period_end = cycle_end
        day_lookup = self._build_day_lookup(cycle_start, cycle_end)

        profile_payload = self._parse_profile_sheet(sheet_frames["profile"], day_lookup)
        schedule_payload = self._parse_schedule_sheet(sheet_frames["schedule"], day_lookup)
        summary_payload = self._parse_summary_sheet(sheet_frames["summary"])

        employees: dict[str, dict[str, Any]] = {}
        self._merge_employee_metadata(employees, report_payload["employees"])
        self._merge_employee_metadata(employees, abnormal_payload["employees"])
        self._merge_employee_metadata(employees, profile_payload["employees"])
        self._merge_employee_metadata(employees, schedule_payload["employees"])
        self._merge_employee_metadata(employees, summary_payload["employees"])
        self._merge_summary(employees, summary_payload["summary"])
        self._merge_daily_payload(employees, report_payload["daily"])
        self._merge_daily_payload(employees, profile_payload["daily"])
        self._merge_daily_payload(employees, schedule_payload["daily"])
        self._merge_daily_payload(employees, abnormal_payload["daily"])

        observed_employee_ids = set(report_payload["daily"].keys()) | set(profile_payload["daily"].keys()) | set(abnormal_payload["daily"].keys())

        return self._finalize_records(employees, allowed_employee_ids=observed_employee_ids)

    def parse_json(self, source: str | Path | bytes | BytesIO, period_start: date | None = None, indent: int = 2) -> str:
        return json.dumps(self.parse(source, period_start=period_start), ensure_ascii=False, indent=indent)

    def _load_workbook(self, source: str | Path | bytes | BytesIO) -> dict[str, pd.DataFrame]:
        workbook_source: Any = source
        engine = "openpyxl"
        if isinstance(source, (bytes, bytearray)):
            workbook_source = BytesIO(source)
            signature = bytes(source[:8])
            if signature.startswith(b"\xd0\xcf\x11\xe0"):
                engine = "xlrd"
        elif hasattr(source, "seek"):
            try:
                source.seek(0)
                signature = source.read(8)
                source.seek(0)
                if isinstance(signature, (bytes, bytearray)) and bytes(signature).startswith(b"\xd0\xcf\x11\xe0"):
                    engine = "xlrd"
            except Exception:
                pass
        elif isinstance(source, (str, Path)) and Path(source).suffix.lower() == ".xls":
            engine = "xlrd"

        if isinstance(source, (str, Path)) and Path(source).suffix.lower() == ".xls":
            engine = "xlrd"

        try:
            workbook = pd.read_excel(workbook_source, sheet_name=None, header=None, dtype=object, engine=engine)
        except Exception as exc:
            raise ValueError(f"Không đọc được file Excel: {exc}") from exc
        if not isinstance(workbook, dict) or not workbook:
            raise ValueError("Workbook không chứa sheet hợp lệ")
        return workbook

    def _match_header_fields(
        self,
        row_values: list[Any],
        required_fields: list[str],
        optional_fields: list[str] | None = None,
    ) -> dict[str, int]:
        optional_fields = optional_fields or []
        current_mapping: dict[str, int] = {}
        for field_name in required_fields + optional_fields:
            aliases = FIELD_ALIASES[field_name]
            for column_index, cell_value in enumerate(row_values):
                if field_name in current_mapping:
                    continue
                if header_value_matches(cell_value, aliases):
                    current_mapping[field_name] = column_index
                    break
        return current_mapping

    def _combine_header_rows(self, dataframe: pd.DataFrame, top_row_index: int, bottom_row_index: int | None = None) -> list[str]:
        combined_values: list[str] = []
        carried_top_value = ""
        for column_index in range(dataframe.shape[1]):
            top_value = safe_str(dataframe.iat[top_row_index, column_index]) if top_row_index < len(dataframe) else ""
            bottom_value = safe_str(dataframe.iat[bottom_row_index, column_index]) if bottom_row_index is not None and bottom_row_index < len(dataframe) else ""
            if top_value:
                carried_top_value = top_value

            effective_top_value = top_value or (carried_top_value if bottom_value else "")
            if effective_top_value and bottom_value and normalize_text(effective_top_value) != normalize_text(bottom_value):
                combined_values.append(f"{effective_top_value} {bottom_value}".strip())
            elif effective_top_value:
                combined_values.append(effective_top_value)
            else:
                combined_values.append(bottom_value)
        return combined_values

    def _find_combined_header_row(
        self,
        dataframe: pd.DataFrame,
        required_fields: list[str],
        optional_fields: list[str] | None = None,
        max_scan_rows: int = 15,
    ) -> tuple[int, int, dict[str, int]]:
        optional_fields = optional_fields or []
        best_row_index = -1
        best_mapping: dict[str, int] = {}
        scan_rows = min(len(dataframe) - 1, max_scan_rows)
        for row_index in range(max(scan_rows, 0)):
            row_values = self._combine_header_rows(dataframe, row_index, row_index + 1)
            current_mapping = self._match_header_fields(row_values, required_fields, optional_fields)
            if len(current_mapping) > len(best_mapping):
                best_row_index = row_index
                best_mapping = current_mapping
            if all(field in current_mapping for field in required_fields):
                return row_index, row_index + 2, current_mapping
        if best_row_index == -1 or not all(field in best_mapping for field in required_fields):
            raise ValueError(f"Không tìm được header ghép phù hợp cho các cột: {', '.join(required_fields)}")
        return best_row_index, best_row_index + 2, best_mapping

    def _extract_labeled_value_from_row(self, row_values: list[Any], field_name: str) -> str:
        aliases = [normalize_text(alias) for alias in FIELD_ALIASES[field_name]]
        for column_index, cell_value in enumerate(row_values):
            raw_text = safe_str(cell_value)
            normalized_text = normalize_text(raw_text)
            if not normalized_text:
                continue
            for alias in aliases:
                if not alias:
                    continue
                if normalized_text == alias or normalized_text.startswith(f"{alias}:"):
                    value_parts = re.split(r"[:：]", raw_text, maxsplit=1)
                    if len(value_parts) == 2 and value_parts[1].strip():
                        return value_parts[1].strip()
                    for next_index in range(column_index + 1, min(len(row_values), column_index + 5)):
                        candidate = safe_str(row_values[next_index])
                        if candidate:
                            return candidate
        return ""

    def _resolve_required_sheets(self, workbook: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
        normalized_map = {normalize_text(sheet_name): dataframe for sheet_name, dataframe in workbook.items()}
        resolved: dict[str, pd.DataFrame] = {}
        missing: list[str] = []
        for canonical_name, aliases in SHEET_ALIASES.items():
            matched_frame = None
            for alias in aliases:
                normalized_alias = normalize_text(alias)
                if normalized_alias in normalized_map:
                    matched_frame = normalized_map[normalized_alias]
                    break
            if matched_frame is None:
                missing.append(aliases[0])
            else:
                resolved[canonical_name] = matched_frame
        if missing:
            raise ValueError(f"Thiếu sheet bắt buộc: {', '.join(missing)}")
        return resolved

    def _find_flat_header_row(
        self,
        dataframe: pd.DataFrame,
        required_fields: list[str],
        optional_fields: list[str] | None = None,
        max_scan_rows: int = 15,
    ) -> tuple[int, dict[str, int]]:
        optional_fields = optional_fields or []
        best_row_index = -1
        best_mapping: dict[str, int] = {}
        scan_rows = min(len(dataframe), max_scan_rows)
        for row_index in range(scan_rows):
            row_values = dataframe.iloc[row_index].tolist()
            current_mapping = self._match_header_fields(row_values, required_fields, optional_fields)
            if len(current_mapping) > len(best_mapping):
                best_row_index = row_index
                best_mapping = current_mapping
            if all(field in current_mapping for field in required_fields):
                return row_index, current_mapping
        if best_row_index == -1 or not all(field in best_mapping for field in required_fields):
            raise ValueError(f"Không tìm được header phù hợp cho các cột: {', '.join(required_fields)}")
        return best_row_index, best_mapping

    def _find_day_header_row(self, dataframe: pd.DataFrame, max_scan_rows: int = 10) -> int:
        best_row_index = 0
        best_score = -1
        scan_rows = min(len(dataframe), max_scan_rows)
        for row_index in range(scan_rows):
            row_values = dataframe.iloc[row_index].tolist()
            parsed_days = [parse_day_number(value) for value in row_values if parse_day_number(value) is not None]
            unique_days = len(set(parsed_days))
            score = unique_days * 100 + len(parsed_days)
            if score > best_score:
                best_score = score
                best_row_index = row_index
        return best_row_index

    def _build_effective_header_values(self, dataframe: pd.DataFrame, header_row_index: int) -> list[str]:
        values: list[str] = []
        max_backtrack = 2
        for column_index in range(dataframe.shape[1]):
            chosen_value = ""
            for row_index in range(header_row_index, max(-1, header_row_index - max_backtrack) - 1, -1):
                if row_index < 0:
                    continue
                cell_value = safe_str(dataframe.iat[row_index, column_index])
                if cell_value:
                    chosen_value = cell_value
                    break
            values.append(chosen_value)
        return values

    def _build_column_date_map(self, dataframe: pd.DataFrame, header_row_index: int, day_lookup: dict[int, date]) -> dict[int, date]:
        column_dates: dict[int, date] = {}
        for column_index in range(dataframe.shape[1]):
            resolved_date: date | None = None
            for row_index in range(max(0, header_row_index - 1), min(len(dataframe), header_row_index + 1)):
                cell_value = dataframe.iat[row_index, column_index]
                parsed_date = parse_date_value(cell_value)
                if parsed_date is not None:
                    resolved_date = parsed_date
                    break
                parsed_day = parse_day_number(cell_value)
                if parsed_day is not None and parsed_day in day_lookup:
                    resolved_date = day_lookup[parsed_day]
                    break
            if resolved_date is not None:
                column_dates[column_index] = resolved_date
        return column_dates

    def _detect_metadata_columns(self, dataframe: pd.DataFrame, header_row_index: int, day_columns: set[int]) -> dict[str, int]:
        effective_headers = self._build_effective_header_values(dataframe, header_row_index)
        mapping: dict[str, int] = {}
        for field_name in ("employee_id", "employee_name", "department"):
            for column_index, header_value in enumerate(effective_headers):
                if column_index in day_columns or field_name in mapping:
                    continue
                if header_value_matches(header_value, FIELD_ALIASES[field_name]):
                    mapping[field_name] = column_index
                    break
        return mapping

    def _extract_identity_from_row(
        self,
        row_values: list[Any],
        metadata_columns: dict[str, int],
        day_columns: set[int],
    ) -> tuple[str, str, str]:
        metadata_values: list[str] = []
        for column_index, raw_value in enumerate(row_values):
            if column_index in day_columns:
                continue
            text = safe_str(raw_value)
            if text:
                metadata_values.append(text)

        employee_id = safe_str(row_values[metadata_columns["employee_id"]]) if "employee_id" in metadata_columns else ""
        employee_name = safe_str(row_values[metadata_columns["employee_name"]]) if "employee_name" in metadata_columns else ""
        department = safe_str(row_values[metadata_columns["department"]]) if "department" in metadata_columns else ""

        if not employee_id and metadata_values:
            employee_id = metadata_values[0]
        if not employee_name and len(metadata_values) >= 2:
            employee_name = metadata_values[1]
        if not department and len(metadata_values) >= 3:
            department = metadata_values[2]

        normalized_id = normalize_text(employee_id)
        normalized_name = normalize_text(employee_name)
        if normalized_id in HEADER_STOP_WORDS or normalized_name in HEADER_STOP_WORDS:
            return "", "", ""
        return employee_id, employee_name, department

    def _resolve_cycle_bounds(
        self,
        explicit_period_start: date | None,
        reference_dates: list[date],
        extra_dataframes: list[pd.DataFrame],
    ) -> tuple[date, date]:
        if explicit_period_start is not None:
            if explicit_period_start.day != 23:
                raise ValueError("period_start phải bắt đầu từ ngày 23")
            period_end = self._shift_to_cycle_end(explicit_period_start)
            return explicit_period_start, period_end

        candidate_dates = list(reference_dates)
        for dataframe in extra_dataframes:
            candidate_dates.extend(self._collect_date_like_cells(dataframe))

        cycle_counter: Counter[tuple[date, date]] = Counter()
        for current_date in candidate_dates:
            cycle_counter[self._resolve_period_for_date(current_date)] += 1

        if not cycle_counter:
            raise ValueError("Không xác định được chu kỳ 23 -> 22 từ workbook. Hãy truyền period_start thủ công.")
        period_start, period_end = cycle_counter.most_common(1)[0][0]
        return period_start, period_end

    def _collect_date_like_cells(self, dataframe: pd.DataFrame) -> list[date]:
        dates: list[date] = []
        scan_rows = min(len(dataframe), 12)
        scan_columns = min(dataframe.shape[1], 64)
        for row_index in range(scan_rows):
            for column_index in range(scan_columns):
                parsed = parse_date_value(dataframe.iat[row_index, column_index])
                if parsed is not None:
                    dates.append(parsed)
                    continue
                dates.extend(parse_date_range_values(dataframe.iat[row_index, column_index]))
        return dates

    def _resolve_period_for_date(self, current_date: date) -> tuple[date, date]:
        if current_date.day >= 23:
            period_start = date(current_date.year, current_date.month, 23)
            period_end = self._shift_to_cycle_end(period_start)
            return period_start, period_end
        if current_date.month == 1:
            period_start = date(current_date.year - 1, 12, 23)
        else:
            period_start = date(current_date.year, current_date.month - 1, 23)
        return period_start, date(current_date.year, current_date.month, 22)

    def _shift_to_cycle_end(self, period_start: date) -> date:
        if period_start.month == 12:
            return date(period_start.year + 1, 1, 22)
        return date(period_start.year, period_start.month + 1, 22)

    def _build_day_lookup(self, period_start: date, period_end: date) -> dict[int, date]:
        lookup: dict[int, date] = {}
        cursor = period_start
        while cursor <= period_end:
            lookup[cursor.day] = cursor
            cursor += timedelta(days=1)
        return lookup

    def _build_month_day_lookup(self, period_start: date, period_end: date) -> dict[str, date]:
        lookup: dict[str, date] = {}
        cursor = period_start
        while cursor <= period_end:
            lookup[cursor.strftime("%m-%d")] = cursor
            cursor += timedelta(days=1)
        return lookup

    def _is_checkin_report_block_header_row(self, row_values: list[Any]) -> bool:
        normalized_values = [normalize_text(value) for value in row_values if normalize_text(value)]
        return normalized_values.count("ngay") >= 2 and "vao lam" in normalized_values and "ra nghi" in normalized_values

    def _parse_checkin_report_block_sheet(self, dataframe: pd.DataFrame) -> dict[str, Any]:
        employees: dict[str, dict[str, str]] = {}
        daily: dict[str, dict[str, dict[str, Any]]] = {}
        reference_dates: list[date] = []

        total_rows = len(dataframe)
        row_index = 0
        while row_index < total_rows:
            row_values = dataframe.iloc[row_index].tolist()
            employee_id = self._extract_labeled_value_from_row(row_values, "employee_id")
            employee_name = self._extract_labeled_value_from_row(row_values, "employee_name")
            department = self._extract_labeled_value_from_row(row_values, "department")
            date_range_values = parse_date_range_values(" ".join(safe_str(value) for value in row_values))

            if not employee_id or len(date_range_values) < 2:
                row_index += 1
                continue

            header_row_index = None
            for next_index in range(row_index + 1, min(row_index + 8, total_rows)):
                if self._is_checkin_report_block_header_row(dataframe.iloc[next_index].tolist()):
                    header_row_index = next_index
                    break

            if header_row_index is None:
                row_index += 1
                continue

            employees.setdefault(employee_id, {"employee_name": employee_name, "department": department})
            block_day_lookup = self._build_month_day_lookup(date_range_values[0], date_range_values[1])
            daily.setdefault(employee_id, {})

            data_row_index = header_row_index + 1
            while data_row_index < total_rows:
                data_row_values = dataframe.iloc[data_row_index].tolist()
                next_employee_id = self._extract_labeled_value_from_row(data_row_values, "employee_id")
                if next_employee_id:
                    break

                found_day_group = False
                for group_start in range(0, len(data_row_values), 8):
                    if group_start >= len(data_row_values):
                        break

                    day_label = safe_str(data_row_values[group_start])
                    if not re.fullmatch(r"\d{2}-\d{2}", day_label):
                        continue

                    found_day_group = True
                    work_date = block_day_lookup.get(day_label)
                    if work_date is None:
                        continue

                    time_cells = [safe_str(value) for value in data_row_values[group_start + 2 : group_start + 8] if safe_str(value)]
                    any_missing = any(contains_missing_punch(value) for value in time_cells)
                    full_missing = bool(time_cells) and all(contains_missing_punch(value) for value in time_cells)
                    actual_time_cells = [value for value in time_cells if not contains_missing_punch(value)]
                    check_in, check_out = min_max_times("\n".join(actual_time_cells))

                    if not check_in and not check_out and not any_missing:
                        continue

                    reference_dates.append(work_date)
                    date_key = work_date.isoformat()
                    current = daily[employee_id].setdefault(date_key, {})
                    if check_in or check_out:
                        merge_attendance_times(current, check_in, check_out)
                    if any_missing:
                        current["abnormal_missing"] = True
                    if full_missing:
                        current["abnormal_full_missing"] = True

                if not found_day_group:
                    break

                data_row_index += 1

            row_index = max(data_row_index, row_index + 1)

        return {"employees": employees, "daily": daily, "reference_dates": reference_dates}

    def _parse_checkin_report_sheet(self, dataframe: pd.DataFrame) -> dict[str, Any]:
        try:
            header_row_index, mapping = self._find_flat_header_row(
                dataframe,
                required_fields=["employee_id", "work_date"],
                optional_fields=["employee_name", "department", "check_in", "check_out", "raw_times"],
            )
        except ValueError:
            return self._parse_checkin_report_block_sheet(dataframe)

        employees: dict[str, dict[str, str]] = {}
        daily: dict[str, dict[str, dict[str, Any]]] = {}
        reference_dates: list[date] = []
        for row_index in range(header_row_index + 1, len(dataframe)):
            row = dataframe.iloc[row_index]
            employee_id = safe_str(row.iloc[mapping["employee_id"]])
            work_date = parse_date_value(row.iloc[mapping["work_date"]])
            if not employee_id or work_date is None:
                continue
            reference_dates.append(work_date)
            employees.setdefault(
                employee_id,
                {
                    "employee_name": safe_str(row.iloc[mapping["employee_name"]]) if "employee_name" in mapping else "",
                    "department": safe_str(row.iloc[mapping["department"]]) if "department" in mapping else "",
                },
            )
            date_key = work_date.isoformat()
            daily.setdefault(employee_id, {})
            current = daily[employee_id].setdefault(date_key, {})
            check_in, check_out = None, None
            if "raw_times" in mapping:
                check_in, check_out = min_max_times(row.iloc[mapping["raw_times"]])
            if check_in is None and "check_in" in mapping:
                check_in = parse_single_time(row.iloc[mapping["check_in"]])
            if check_out is None and "check_out" in mapping:
                check_out = parse_single_time(row.iloc[mapping["check_out"]])
            if check_in or check_out:
                merge_attendance_times(current, check_in, check_out)
        return {"employees": employees, "daily": daily, "reference_dates": reference_dates}

    def _parse_abnormal_sheet(self, dataframe: pd.DataFrame) -> dict[str, Any]:
        header_row_index, mapping = self._find_flat_header_row(
            dataframe,
            required_fields=["employee_id", "work_date", "late_minutes", "early_minutes"],
            optional_fields=["employee_name", "department", "check_in", "check_out"],
        )
        header_values = [normalize_text(value) for value in self._combine_header_rows(dataframe, header_row_index, header_row_index + 1)]
        punch_columns: list[int] = []
        for column_index, header_value in enumerate(header_values):
            if column_index in {
                mapping.get("late_minutes", -1),
                mapping.get("early_minutes", -1),
            }:
                continue
            if "vao" in header_value or "ra" in header_value:
                punch_columns.append(column_index)

        employees: dict[str, dict[str, str]] = {}
        daily: dict[str, dict[str, dict[str, Any]]] = {}
        reference_dates: list[date] = []
        for row_index in range(header_row_index + 1, len(dataframe)):
            row = dataframe.iloc[row_index]
            employee_id = safe_str(row.iloc[mapping["employee_id"]])
            work_date = parse_date_value(row.iloc[mapping["work_date"]])
            if not employee_id or work_date is None:
                continue
            reference_dates.append(work_date)
            employees.setdefault(
                employee_id,
                {
                    "employee_name": safe_str(row.iloc[mapping["employee_name"]]) if "employee_name" in mapping else "",
                    "department": safe_str(row.iloc[mapping["department"]]) if "department" in mapping else "",
                },
            )

            punch_values = [safe_str(row.iloc[column_index]) for column_index in punch_columns if safe_str(row.iloc[column_index])]
            any_missing = any(contains_missing_punch(value) for value in punch_values)
            full_missing = bool(punch_values) and all(contains_missing_punch(value) for value in punch_values)
            actual_punch_values = [value for value in punch_values if not contains_missing_punch(value)]
            check_in, check_out = min_max_times("\n".join(actual_punch_values))

            date_key = work_date.isoformat()
            daily.setdefault(employee_id, {})
            daily[employee_id][date_key] = {
                "late_minutes": parse_int(row.iloc[mapping["late_minutes"]]),
                "early_minutes": parse_int(row.iloc[mapping["early_minutes"]]),
                "abnormal_missing": any_missing,
                "abnormal_full_missing": full_missing,
            }
            if check_in or check_out:
                daily[employee_id][date_key].update(
                    {
                        "check_in": check_in,
                        "check_out": check_out,
                        "has_raw_data": True,
                    }
                )
        return {"employees": employees, "daily": daily, "reference_dates": reference_dates}

    def _parse_summary_sheet(self, dataframe: pd.DataFrame) -> dict[str, Any]:
        try:
            header_row_index, mapping = self._find_flat_header_row(
                dataframe,
                required_fields=["employee_id", "total_late_minutes", "total_absent_days"],
                optional_fields=["employee_name", "department"],
            )
            data_start_row = header_row_index + 1
        except ValueError:
            header_row_index, data_start_row, mapping = self._find_combined_header_row(
                dataframe,
                required_fields=["employee_id", "total_late_minutes", "total_absent_days"],
                optional_fields=["employee_name", "department"],
            )
        employees: dict[str, dict[str, str]] = {}
        summary: dict[str, dict[str, int]] = {}
        for row_index in range(data_start_row, len(dataframe)):
            row = dataframe.iloc[row_index]
            employee_id = safe_str(row.iloc[mapping["employee_id"]])
            if not employee_id:
                continue
            employees.setdefault(
                employee_id,
                {
                    "employee_name": safe_str(row.iloc[mapping["employee_name"]]) if "employee_name" in mapping else "",
                    "department": safe_str(row.iloc[mapping["department"]]) if "department" in mapping else "",
                },
            )
            summary[employee_id] = {
                "total_late_minutes": parse_int(row.iloc[mapping["total_late_minutes"]]),
                "total_absent_days": parse_int(row.iloc[mapping["total_absent_days"]]),
            }
        return {"employees": employees, "summary": summary}

    def _parse_schedule_sheet(self, dataframe: pd.DataFrame, day_lookup: dict[int, date]) -> dict[str, Any]:
        header_row_index = self._find_day_header_row(dataframe)
        column_dates = self._build_column_date_map(dataframe, header_row_index, day_lookup)
        day_columns = set(column_dates.keys())
        metadata_columns = self._detect_metadata_columns(dataframe, header_row_index, day_columns)
        employees: dict[str, dict[str, str]] = {}
        daily: dict[str, dict[str, dict[str, Any]]] = {}
        for row_index in range(header_row_index + 1, len(dataframe)):
            row_values = dataframe.iloc[row_index].tolist()
            employee_id, employee_name, department = self._extract_identity_from_row(row_values, metadata_columns, day_columns)
            if not employee_id:
                continue
            employees.setdefault(employee_id, {"employee_name": employee_name, "department": department})
            daily.setdefault(employee_id, {})
            for column_index, work_date in column_dates.items():
                if work_date.weekday() >= 5:
                    continue
                cell_value = dataframe.iat[row_index, column_index]
                if parse_int(cell_value) != 1:
                    continue
                date_key = work_date.isoformat()
                current = daily[employee_id].setdefault(date_key, {})
                current["scheduled_to_work"] = True
        return {"employees": employees, "daily": daily}

    def _parse_profile_sheet(self, dataframe: pd.DataFrame, day_lookup: dict[int, date]) -> dict[str, Any]:
        employees: dict[str, dict[str, str]] = {}
        daily: dict[str, dict[str, dict[str, Any]]] = {}

        day_header_rows: list[int] = []
        scan_rows = min(len(dataframe), 40)
        for row_index in range(scan_rows):
            row_values = dataframe.iloc[row_index].tolist()
            day_count = sum(1 for value in row_values if parse_day_number(value) is not None)
            if day_count >= 8:
                day_header_rows.append(row_index)

        for header_row_index in day_header_rows:
            metadata_row_index = header_row_index + 1
            time_row_index = header_row_index + 2
            if metadata_row_index >= len(dataframe) or time_row_index >= len(dataframe):
                continue

            column_dates = self._build_column_date_map(dataframe, header_row_index, day_lookup)
            day_columns = set(column_dates.keys())
            metadata_columns = self._detect_metadata_columns(dataframe, header_row_index, day_columns)
            info_row = dataframe.iloc[metadata_row_index].tolist()
            employee_id = self._extract_labeled_value_from_row(info_row, "employee_id")
            employee_name = self._extract_labeled_value_from_row(info_row, "employee_name")
            department = self._extract_labeled_value_from_row(info_row, "department")

            if not employee_id:
                employee_id, employee_name, department = self._extract_identity_from_row(info_row, metadata_columns, day_columns)
            if not employee_id:
                continue

            time_row = dataframe.iloc[time_row_index]
            employees.setdefault(employee_id, {"employee_name": employee_name, "department": department})
            daily.setdefault(employee_id, {})
            for column_index, work_date in column_dates.items():
                raw_cell = time_row.iloc[column_index] if column_index < len(time_row) else None
                check_in, check_out = min_max_times(raw_cell)
                if not check_in and not check_out:
                    continue
                date_key = work_date.isoformat()
                current = daily[employee_id].setdefault(date_key, {})
                merge_attendance_times(current, check_in, check_out)
        return {"employees": employees, "daily": daily}

    def _merge_employee_metadata(self, employees: dict[str, dict[str, Any]], payload: dict[str, dict[str, str]]) -> None:
        for employee_id, meta in payload.items():
            current = employees.setdefault(
                employee_id,
                {
                    "employee_id": employee_id,
                    "employee_name": "",
                    "department": "",
                    "summary_from_machine": {"total_late_minutes": 0, "total_absent_days": 0},
                    "attendance_details": {},
                },
            )
            next_name = safe_str(meta.get("employee_name"))
            next_department = safe_str(meta.get("department"))
            if next_name and not current["employee_name"]:
                current["employee_name"] = next_name
            if next_department and (not current["department"] or current["department"].lower().startswith("not set")):
                current["department"] = next_department

    def _merge_summary(self, employees: dict[str, dict[str, Any]], payload: dict[str, dict[str, int]]) -> None:
        for employee_id, summary in payload.items():
            current = employees.setdefault(
                employee_id,
                {
                    "employee_id": employee_id,
                    "employee_name": "",
                    "department": "",
                    "summary_from_machine": {"total_late_minutes": 0, "total_absent_days": 0},
                    "attendance_details": {},
                },
            )
            current["summary_from_machine"] = {
                "total_late_minutes": int(summary.get("total_late_minutes", 0)),
                "total_absent_days": int(summary.get("total_absent_days", 0)),
            }

    def _merge_daily_payload(self, employees: dict[str, dict[str, Any]], payload: dict[str, dict[str, dict[str, Any]]]) -> None:
        for employee_id, days in payload.items():
            current_employee = employees.setdefault(
                employee_id,
                {
                    "employee_id": employee_id,
                    "employee_name": "",
                    "department": "",
                    "summary_from_machine": {"total_late_minutes": 0, "total_absent_days": 0},
                    "attendance_details": {},
                },
            )
            for date_key, values in days.items():
                current_day = current_employee["attendance_details"].setdefault(
                    date_key,
                    {
                        "scheduled_to_work": False,
                        "check_in": None,
                        "check_out": None,
                        "late_minutes": 0,
                        "has_raw_data": False,
                        "abnormal_missing": False,
                        "abnormal_full_missing": False,
                    },
                )
                if values.get("scheduled_to_work"):
                    current_day["scheduled_to_work"] = True
                if values.get("check_in") or values.get("check_out"):
                    merge_attendance_times(current_day, values.get("check_in"), values.get("check_out"))
                if values.get("has_raw_data"):
                    current_day["has_raw_data"] = True
                if "late_minutes" in values:
                    current_day["late_minutes"] = int(values.get("late_minutes") or 0)
                if values.get("abnormal_missing"):
                    current_day["abnormal_missing"] = True
                if values.get("abnormal_full_missing"):
                    current_day["abnormal_full_missing"] = True

    def _finalize_records(
        self,
        employees: dict[str, dict[str, Any]],
        allowed_employee_ids: set[str] | None = None,
    ) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        validation_summary: dict[str, dict[str, int | bool]] = {}
        for employee_id in sorted(employees.keys(), key=self._employee_sort_key):
            if allowed_employee_ids is not None and employee_id not in allowed_employee_ids:
                continue

            employee = employees[employee_id]
            details: dict[str, dict[str, Any]] = {}
            computed_late_minutes = 0
            computed_absent_days = 0

            for date_key in sorted(employee["attendance_details"].keys()):
                work_date = date.fromisoformat(date_key)
                if work_date.weekday() >= 5:
                    continue

                raw_detail = employee["attendance_details"][date_key]
                has_raw = bool(raw_detail.get("has_raw_data") or raw_detail.get("check_in") or raw_detail.get("check_out"))
                scheduled_to_work = bool(raw_detail.get("scheduled_to_work"))
                abnormal_missing = bool(raw_detail.get("abnormal_missing"))
                abnormal_full_missing = bool(raw_detail.get("abnormal_full_missing"))
                late_minutes = int(raw_detail.get("late_minutes") or 0)
                
                # Không suy diễn vắng mặt chỉ từ lịch trình; chỉ giữ ngày có dữ liệu thực tế.
                include_row = has_raw or abnormal_missing or late_minutes > 0
                if not include_row:
                    continue

                check_in = raw_detail.get("check_in")
                check_out = raw_detail.get("check_out")
                if abnormal_full_missing:
                    status = "Absent"
                    if not has_raw:
                        check_in = None
                        check_out = None
                elif (abnormal_missing or bool(check_in) != bool(check_out)):
                    status = "Missing_Punch"
                else:
                    status = "Normal"

                details[date_key] = {
                    "scheduled_to_work": scheduled_to_work,
                    "check_in": check_in,
                    "check_out": check_out,
                    "status": status,
                    "late_minutes": late_minutes,
                }
                computed_late_minutes += late_minutes
                if status == "Absent":
                    computed_absent_days += 1

            if not details:
                continue

            validation_summary[employee_id] = {
                "computed_total_late_minutes": computed_late_minutes,
                "computed_total_absent_days": computed_absent_days,
                "machine_total_late_minutes": int(employee["summary_from_machine"].get("total_late_minutes", 0)),
                "machine_total_absent_days": int(employee["summary_from_machine"].get("total_absent_days", 0)),
                "late_minutes_match": computed_late_minutes == int(employee["summary_from_machine"].get("total_late_minutes", 0)),
                "absent_days_match": computed_absent_days == int(employee["summary_from_machine"].get("total_absent_days", 0)),
            }

            records.append(
                {
                    "employee_id": employee_id,
                    "employee_name": employee["employee_name"],
                    "department": employee["department"],
                    "summary_from_machine": employee["summary_from_machine"],
                    "attendance_details": details,
                }
            )

        self.last_validation_summary = validation_summary
        return records

    def _employee_sort_key(self, employee_id: str) -> tuple[int, str]:
        return (0, f"{int(employee_id):09d}") if employee_id.isdigit() else (1, employee_id)


def main() -> None:
    parser = argparse.ArgumentParser(description="Parse workbook máy chấm công 5 sheet thành JSON")
    parser.add_argument("input_file", help="Đường dẫn file Excel cần parse")
    parser.add_argument("--period-start", dest="period_start", help="Chu kỳ bắt đầu ngày 23, định dạng YYYY-MM-DD", default=None)
    args = parser.parse_args()

    attendance_parser = AttendanceParser()
    period_start = parse_date_value(args.period_start) if args.period_start else None
    result = attendance_parser.parse(args.input_file, period_start=period_start)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
