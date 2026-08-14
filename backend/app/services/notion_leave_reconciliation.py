from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from datetime import date, datetime, timedelta
from io import BytesIO
from pathlib import Path
import re
import unicodedata
from typing import Any

import pandas as pd


NOTION_ARROW = "\u2192"
DATE_PATTERN = re.compile(r"(\d{1,2}[-/]\d{1,2}[-/]\d{4})")
NOTION_URL_PATTERN = re.compile(r"\s*\(https?://[^)]*\)\s*")
NOTION_TIME_SPLIT_PATTERN = re.compile(r"\s*(?:\u2192|->)\s*")
TIME_PATTERN = re.compile(r"(?i)\b(\d{1,2}):(\d{2})(?:\s*([ap])\.?m\.?)?\b")
LEAVE_FORM_ALIASES = {
    "leave request",
    "leave",
    "new submission",
    "luot gui moi",
    "xin nghi phep",
}
WORK_FROM_HOME_FORM_ALIASES = {
    "work from home",
    "wfh",
    "lam viec tai nha",
}
# Notion is the attendance source of truth for leave submissions. Every leave
# request is treated as approved for attendance, except a request that has
# explicitly been rejected or cancelled.
INACTIVE_NOTION_STATUSES = {
    "rejected",
    "reject",
    "tu choi",
    "cancelled",
    "canceled",
    "cancel",
    "withdrawn",
    "declined",
}
MORNING_LEAVE_START_MARKERS = ("8:00 am", "8:30 am")
MORNING_LEAVE_END_MARKERS = ("12:00 pm", "1:00 pm", "1:30 pm")
AFTERNOON_LEAVE_END_MARKERS = ("5:00 pm", "5:30 pm", "6:00 pm")
NOON_MINUTES = 12 * 60


def _normalize_key(value: str | None) -> str:
    text = str(value or "")
    text = unicodedata.normalize("NFKD", text)
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = text.replace("đ", "d").replace("Đ", "D")
    text = re.sub(r"[^a-zA-Z0-9]+", " ", text)
    return " ".join(text.lower().split())


def _normalize_column_key(value: str | None) -> str:
    return _normalize_key(value).replace(" ", "_")


def _is_inactive_notion_status(value: str | None) -> bool:
    return _normalize_key(value) in INACTIVE_NOTION_STATUSES


def _load_notion_dataframe(source: str | Path | bytes | bytearray | BytesIO) -> pd.DataFrame:
    if isinstance(source, (str, Path)):
        return pd.read_csv(source)
    if isinstance(source, (bytes, bytearray)):
        return pd.read_csv(BytesIO(bytes(source)))
    if isinstance(source, BytesIO):
        source.seek(0)
        return pd.read_csv(source)
    raise ValueError("notion_csv_path phải là đường dẫn hoặc bytes hợp lệ")


def _resolve_column(df: pd.DataFrame, normalized_key: str) -> str | None:
    column_map = {_normalize_column_key(column): column for column in df.columns}
    return column_map.get(normalized_key)


def _clean_notion_person_value(raw_value: str | None) -> str | None:
    if raw_value is None or pd.isna(raw_value):
        return None
    text = NOTION_URL_PATTERN.sub("", str(raw_value)).strip()
    if not text:
        return None
    return " ".join(text.split()) or None


def _extract_employee_name(raw_value: str | None) -> str | None:
    text = _clean_notion_person_value(raw_value)
    if not text:
        return None
    parts = re.split(r"\s*-\s*", text, maxsplit=1)
    candidate = parts[1] if len(parts) == 2 and parts[1].strip() else text
    candidate = " ".join(candidate.split())
    return candidate or None


def _collect_employee_name_candidates(*raw_values: str | None) -> list[str]:
    candidates: list[str] = []
    seen: set[str] = set()
    for raw_value in raw_values:
        for candidate in (_clean_notion_person_value(raw_value), _extract_employee_name(raw_value)):
            normalized_candidate = _normalize_key(candidate)
            if candidate and normalized_candidate and normalized_candidate not in seen:
                seen.add(normalized_candidate)
                candidates.append(candidate)
    return candidates


def _tokens_match_by_prefix(left_tokens: list[str], right_tokens: list[str]) -> bool:
    if len(left_tokens) < 2 or len(left_tokens) != len(right_tokens):
        return False
    for left_token, right_token in zip(left_tokens, right_tokens):
        if left_token == right_token:
            continue
        shorter, longer = (left_token, right_token) if len(left_token) <= len(right_token) else (right_token, left_token)
        if len(shorter) < 2 or not longer.startswith(shorter):
            return False
    return True


def _find_matching_employees(
    employee_index: dict[str, list[dict[str, Any]]],
    employee_name_candidates: list[str],
) -> list[dict[str, Any]]:
    normalized_candidates = [_normalize_key(candidate) for candidate in employee_name_candidates if _normalize_key(candidate)]

    for normalized_candidate in normalized_candidates:
        matched_employees = employee_index.get(normalized_candidate)
        if matched_employees:
            return matched_employees

    fuzzy_matches: list[str] = []
    for normalized_candidate in normalized_candidates:
        candidate_tokens = normalized_candidate.split()
        for employee_key in employee_index:
            if _tokens_match_by_prefix(candidate_tokens, employee_key.split()):
                fuzzy_matches.append(employee_key)

    unique_matches = list(dict.fromkeys(fuzzy_matches))
    if len(unique_matches) == 1:
        return employee_index[unique_matches[0]]

    return []


def _normalize_notion_employee_directory(
    notion_employee_directory: Mapping[str, str | list[str] | tuple[str, ...]] | None,
) -> dict[str, list[str]]:
    normalized_directory: dict[str, list[str]] = {}
    if not notion_employee_directory:
        return normalized_directory

    for notion_name, raw_machine_ids in notion_employee_directory.items():
        normalized_name = _normalize_key(notion_name)
        if not normalized_name:
            continue

        values = raw_machine_ids if isinstance(raw_machine_ids, (list, tuple, set)) else [raw_machine_ids]
        current_ids = normalized_directory.setdefault(normalized_name, [])
        for raw_machine_id in values:
            machine_id = str(raw_machine_id or "").strip()
            if machine_id and machine_id not in current_ids:
                current_ids.append(machine_id)

    return normalized_directory


def _find_matching_employees_from_directory(
    attendance_employee_id_index: dict[str, list[dict[str, Any]]],
    notion_employee_directory: dict[str, list[str]],
    employee_name_candidates: list[str],
) -> list[dict[str, Any]]:
    normalized_candidates = [_normalize_key(candidate) for candidate in employee_name_candidates if _normalize_key(candidate)]

    for normalized_candidate in normalized_candidates:
        mapped_machine_ids = notion_employee_directory.get(normalized_candidate)
        if not mapped_machine_ids:
            continue

        matched_employees: list[dict[str, Any]] = []
        seen_keys: set[str] = set()
        for mapped_machine_id in mapped_machine_ids:
            normalized_machine_id = _normalize_key(mapped_machine_id)
            for employee in attendance_employee_id_index.get(normalized_machine_id, []):
                unique_key = _normalize_key(str(employee.get("employee_id") or "")) or str(id(employee))
                if unique_key in seen_keys:
                    continue
                seen_keys.add(unique_key)
                matched_employees.append(employee)

        if matched_employees:
            return matched_employees

    return []


def _detect_date_format(
    df: pd.DataFrame,
    time_col: str,
    period_start: date | None = None,
    period_end: date | None = None,
) -> str:
    # Default to %d/%m/%Y (Vietnamese format).  A Notion export may however
    # use the English month/day format, so the selected attendance cycle is
    # used as the primary signal whenever both parts of a date are ambiguous.
    detected_format = "%d/%m/%Y"
    if not time_col or time_col not in df.columns:
        return detected_format

    date_pattern_flexible = re.compile(r"(\d{1,2})([-/])(\d{1,2})[-/](\d{4})")
    detected_separator = "/"
    d_m_y_certainty = 0
    m_d_y_certainty = 0
    d_m_y_votes = 0
    m_d_y_votes = 0

    for val in df[time_col].dropna():
        val_str = str(val).strip()
        matches = date_pattern_flexible.findall(val_str)
        for m in matches:
            first = int(m[0])
            sep = m[1]
            second = int(m[2])
            year = int(m[3])
            detected_separator = sep
            if first > 12:
                d_m_y_certainty += 1
            elif second > 12:
                m_d_y_certainty += 1

            if period_start and period_end:
                try:
                    d_m_y_date = date(year, second, first)
                    if period_start <= d_m_y_date <= period_end:
                        d_m_y_votes += 1
                except ValueError:
                    pass
                try:
                    m_d_y_date = date(year, first, second)
                    if period_start <= m_d_y_date <= period_end:
                        m_d_y_votes += 1
                except ValueError:
                    pass

    # The active cycle has priority: it makes a July 06 Notion submission
    # become 6 July (MM/DD) instead of 7 June (DD/MM), for example.
    if m_d_y_votes > d_m_y_votes:
        return f"%m{detected_separator}%d{detected_separator}%Y"
    if d_m_y_votes > m_d_y_votes:
        return f"%d{detected_separator}%m{detected_separator}%Y"
    if m_d_y_certainty > d_m_y_certainty:
        return f"%m{detected_separator}%d{detected_separator}%Y"
    if d_m_y_certainty > m_d_y_certainty:
        return f"%d{detected_separator}%m{detected_separator}%Y"
    return detected_format


def _select_notion_rows_for_period(
    notion_df: pd.DataFrame,
    time_col: str,
    period_start: date | None,
    period_end: date | None,
) -> tuple[pd.DataFrame, str]:
    """Read the Notion ``Thời Gian`` ranges and retain only rows for the
    attendance cycle being uploaded.

    Notion exports contain a long history. Filtering by overlap (rather than
    by a single start date) keeps leave that starts before the 23rd and ends in
    the active cycle, while preventing old/new months from leaking into the
    current timesheet.
    """
    detected_fmt = _detect_date_format(notion_df, time_col, period_start, period_end)
    if period_start is None or period_end is None:
        return notion_df, detected_fmt

    matching_indexes: list[Any] = []
    for row_index, row in notion_df.iterrows():
        date_range = _parse_date_range(row.get(time_col), fmt=detected_fmt)
        if date_range is None:
            continue
        leave_start, leave_end = date_range
        if leave_start <= period_end and leave_end >= period_start:
            matching_indexes.append(row_index)

    return notion_df.loc[matching_indexes].copy(), detected_fmt



def _parse_date_range(raw_value: str | None, fmt: str = "%d/%m/%Y") -> tuple[date, date] | None:
    if raw_value is None or pd.isna(raw_value):
        return None
    text = str(raw_value).strip()
    if not text:
        return None
    matches = DATE_PATTERN.findall(text)
    if not matches:
        return None
    try:
        start_date = datetime.strptime(matches[0], fmt).date()
        end_date = datetime.strptime(matches[1], fmt).date() if len(matches) > 1 else start_date
        if end_date < start_date:
            start_date, end_date = end_date, start_date
        return start_date, end_date
    except ValueError:
        # Fallback to swapping day/month formats if parsing fails
        if "%d" in fmt:
            fallback_fmt = fmt.replace("%d", "%tmp").replace("%m", "%d").replace("%tmp", "%m")
        else:
            fallback_fmt = fmt.replace("%m", "%tmp").replace("%d", "%m").replace("%tmp", "%d")
        try:
            start_date = datetime.strptime(matches[0], fallback_fmt).date()
            end_date = datetime.strptime(matches[1], fallback_fmt).date() if len(matches) > 1 else start_date
            if end_date < start_date:
                start_date, end_date = end_date, start_date
            return start_date, end_date
        except ValueError:
            return None


def _parse_leave_units(raw_value: Any) -> float | None:
    if raw_value is None or pd.isna(raw_value):
        return None
    text = str(raw_value).strip().replace(",", ".")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _split_notion_time_range(raw_value: Any) -> tuple[str, str] | None:
    if raw_value is None or pd.isna(raw_value):
        return None
    parts = NOTION_TIME_SPLIT_PATTERN.split(str(raw_value), maxsplit=1)
    if len(parts) != 2:
        return None
    start_text = parts[0].strip()
    end_text = parts[1].strip()
    if not start_text or not end_text:
        return None
    return start_text, end_text


def _normalize_time_text(raw_value: str | None) -> str:
    return " ".join(str(raw_value or "").strip().lower().split())


def _resolve_half_day_leave_session(
    raw_time_range: Any,
    leave_units: float | None,
    *,
    is_single_day_leave: bool = True,
) -> str | None:
    if not is_single_day_leave:
        return None

    split_range = _split_notion_time_range(raw_time_range)
    if split_range is not None:
        start_mins = _parse_time_to_minutes(split_range[0])
        end_mins = _parse_time_to_minutes(split_range[1])
        if start_mins is not None and end_mins is not None:
            if end_mins <= 13 * 60 + 30:
                return "morning"
            if start_mins >= 12 * 60:
                return "afternoon"

    if leave_units is not None and abs(leave_units - 0.5) > 1e-9:
        return None

    if split_range is None:
        return None

    start_text, end_text = split_range
    normalized_start = _normalize_time_text(start_text)
    normalized_end = _normalize_time_text(end_text)
    has_morning_start = any(marker in normalized_start for marker in MORNING_LEAVE_START_MARKERS)
    has_morning_end = any(marker in normalized_end for marker in MORNING_LEAVE_END_MARKERS)
    has_afternoon_end = any(marker in normalized_end for marker in AFTERNOON_LEAVE_END_MARKERS)

    if has_morning_start and has_morning_end:
        return "morning"
    if has_afternoon_end:
        return "afternoon"
    return None


def _parse_time_to_minutes(raw_value: Any) -> int | None:
    if raw_value is None or pd.isna(raw_value):
        return None
    text = str(raw_value).strip().replace("*", "")
    if not text:
        return None

    match = TIME_PATTERN.search(text)
    if match is None:
        return None

    hour = int(match.group(1))
    minute = int(match.group(2))
    meridiem = (match.group(3) or "").lower()

    if meridiem == "p" and hour < 12:
        hour += 12
    elif meridiem == "a" and hour == 12:
        hour = 0

    return hour * 60 + minute


def _attendance_minutes(detail: Mapping[str, Any]) -> list[int]:
    minutes: list[int] = []
    for value in (detail.get("check_in"), detail.get("check_out")):
        parsed_minutes = _parse_time_to_minutes(value)
        if parsed_minutes is not None:
            minutes.append(parsed_minutes)
    return minutes


def _has_morning_attendance(detail: Mapping[str, Any]) -> bool:
    return any(minutes <= NOON_MINUTES for minutes in _attendance_minutes(detail))


def _has_afternoon_attendance(detail: Mapping[str, Any]) -> bool:
    return any(minutes >= NOON_MINUTES for minutes in _attendance_minutes(detail))


def _resolve_notion_attendance_symbol_for_day(
    detail: Mapping[str, Any],
    day_leave_type: str,
) -> str:
    has_morning = _has_morning_attendance(detail)
    has_afternoon = _has_afternoon_attendance(detail)

    if day_leave_type == "morning":
        return "P/X" if has_afternoon else "P/Ro"
    if day_leave_type == "afternoon":
        return "X/P" if has_morning else "Ro/P"

    # Full day leave
    if has_morning and has_afternoon:
        return "X"
    if has_morning and not has_afternoon:
        return "X/P"
    if not has_morning and has_afternoon:
        return "P/X"
    return "P"


def _iter_weekdays(start_date: date, end_date: date) -> list[date]:
    workdays: list[date] = []
    cursor = start_date
    while cursor <= end_date:
        if cursor.weekday() < 5:
            workdays.append(cursor)
        cursor += timedelta(days=1)
    return workdays


def _get_notion_submission_kind(form_name: str | None) -> str | None:
    if form_name is None or pd.isna(form_name):
        return None
    normalized_form_name = _normalize_key(str(form_name))
    if normalized_form_name in LEAVE_FORM_ALIASES:
        return "leave"
    if normalized_form_name in WORK_FROM_HOME_FORM_ALIASES:
        return "work_from_home"
    return None


def reconcile_attendance_with_notion(
    attendance_json: list[dict[str, Any]],
    notion_csv_path: str | Path | bytes | bytearray | BytesIO,
    notion_employee_directory: Mapping[str, str | list[str] | tuple[str, ...]] | None = None,
    period_start: date | None = None,
    period_end: date | None = None,
) -> list[dict[str, Any]]:
    notion_df = _load_notion_dataframe(notion_csv_path)
    if notion_df.empty:
        return deepcopy(attendance_json)

    leave_balance_col = _resolve_column(notion_df, "leave_balance")
    time_col = _resolve_column(notion_df, "thoi_gian")
    leave_days_col = _resolve_column(notion_df, "so_ngay_nghi")
    employee_link_col = _resolve_column(notion_df, "ten_nhan_vien")
    name_col = _resolve_column(notion_df, "name")
    status_col = _resolve_column(notion_df, "trang_thai")

    if leave_balance_col is None or time_col is None:
        raise ValueError("File Notion thiếu cột Leave Balance hoặc Thời Gian")

    notion_df, detected_fmt = _select_notion_rows_for_period(
        notion_df,
        time_col,
        period_start,
        period_end,
    )
    if notion_df.empty:
        return deepcopy(attendance_json)

    reconciled_payload = deepcopy(attendance_json)
    employee_index: dict[str, list[dict[str, Any]]] = {}
    attendance_employee_id_index: dict[str, list[dict[str, Any]]] = {}
    normalized_notion_directory = _normalize_notion_employee_directory(notion_employee_directory)
    for employee in reconciled_payload:
        normalized_employee_id = _normalize_key(str(employee.get("employee_id") or ""))
        if normalized_employee_id:
            attendance_employee_id_index.setdefault(normalized_employee_id, []).append(employee)
        for raw_key in [employee.get("employee_name"), employee.get("employee_id"), employee.get("full_name")]:
            normalized_key = _normalize_key(str(raw_key or ""))
            if normalized_key:
                employee_index.setdefault(normalized_key, []).append(employee)

    for _, row in notion_df.iterrows():
        submission_kind = _get_notion_submission_kind(row.get(name_col)) if name_col is not None else "leave"
        if submission_kind is None:
            continue

        employee_name_candidates = _collect_employee_name_candidates(
            row.get(employee_link_col) if employee_link_col is not None else None,
            row.get(leave_balance_col),
        )
        if not employee_name_candidates:
            continue

        date_range = _parse_date_range(row.get(time_col), fmt=detected_fmt)
        if date_range is None:
            continue

        leave_units = _parse_leave_units(row.get(leave_days_col)) if leave_days_col is not None else None
        if submission_kind == "leave" and leave_units is not None and leave_units <= 0:
            continue

        split_range = _split_notion_time_range(row.get(time_col))
        start_mins = None
        end_mins = None
        if split_range is not None:
            start_mins = _parse_time_to_minutes(split_range[0])
            end_mins = _parse_time_to_minutes(split_range[1])

        leave_session = _resolve_half_day_leave_session(
            row.get(time_col),
            leave_units,
            is_single_day_leave=date_range[0] == date_range[1],
        )

        matched_employees = _find_matching_employees_from_directory(
            attendance_employee_id_index,
            normalized_notion_directory,
            employee_name_candidates,
        )
        if not matched_employees:
            matched_employees = _find_matching_employees(employee_index, employee_name_candidates)
        if not matched_employees:
            continue

        notion_status = str(row.get(status_col) or "submitted").strip() if status_col is not None else "submitted"
        is_inactive = _is_inactive_notion_status(notion_status)

        for employee in matched_employees:
            attendance_details = employee.setdefault("attendance_details", {})
            if not isinstance(attendance_details, dict):
                continue

            for work_date in _iter_weekdays(*date_range):
                if period_start is not None and work_date < period_start:
                    continue
                if period_end is not None and work_date > period_end:
                    continue

                work_date_key = work_date.isoformat()
                existing_detail = attendance_details.get(work_date_key)
                detail = dict(existing_detail) if isinstance(existing_detail, dict) else {}

                # Every submitted Notion request is active for attendance.
                # A rejection/cancellation is the only state that may leave
                # the machine-derived absence unchanged.
                if not is_inactive:
                    if submission_kind == "work_from_home":
                        # WFH is a full working day, not a paid-leave record.
                        # It intentionally does not consume leave quota and
                        # does not require a fingerprint-machine scan.
                        detail["attendance_symbol"] = "X"
                        detail["status"] = "Work_From_Home"
                        detail["notion_work_from_home"] = True
                    else:
                        if date_range[0] == date_range[1]:
                            if leave_session == "morning":
                                day_leave_type = "morning"
                            elif leave_session == "afternoon":
                                day_leave_type = "afternoon"
                            else:
                                day_leave_type = "full"
                        elif work_date == date_range[0]:
                            day_leave_type = "afternoon" if start_mins is not None and start_mins >= 12 * 60 else "full"
                        elif work_date == date_range[1]:
                            day_leave_type = "morning" if end_mins is not None and end_mins <= 13 * 60 + 30 else "full"
                        else:
                            day_leave_type = "full"

                        resolved_symbol = _resolve_notion_attendance_symbol_for_day(detail, day_leave_type)
                        if resolved_symbol:
                            detail["attendance_symbol"] = resolved_symbol
                            if resolved_symbol != "X" or not detail.get("status"):
                                # Keep the existing UI/API status stable; the
                                # original Notion state remains available in
                                # ``notion_status`` below.
                                detail["status"] = "Notion_Submitted"

                detail["notion_submitted"] = not is_inactive
                detail["notion_status"] = notion_status or "submitted"
                detail["notion_submission_type"] = submission_kind
                attendance_details[work_date_key] = detail

    return reconciled_payload


def save_notion_leaves_to_db(
    db: Session,
    notion_csv_path: str | Path | bytes | bytearray | BytesIO,
    notion_employee_directory: Mapping[str, str | list[str] | tuple[str, ...]] | None = None,
    period_start: date | None = None,
    period_end: date | None = None,
) -> None:
    from app.models.employee import Employee
    from app.models.off_request import OffRequest

    notion_df = _load_notion_dataframe(notion_csv_path)
    if notion_df.empty:
        return

    leave_balance_col = _resolve_column(notion_df, "leave_balance")
    time_col = _resolve_column(notion_df, "thoi_gian")
    leave_days_col = _resolve_column(notion_df, "so_ngay_nghi")
    employee_link_col = _resolve_column(notion_df, "ten_nhan_vien")
    name_col = _resolve_column(notion_df, "name")
    status_col = _resolve_column(notion_df, "trang_thai")
    reason_col = _resolve_column(notion_df, "ly_do_nghi") or _resolve_column(notion_df, "ly_do_khac")

    if leave_balance_col is None or time_col is None:
        raise ValueError("File Notion thiếu cột Leave Balance hoặc Thời Gian")

    notion_df, detected_fmt = _select_notion_rows_for_period(
        notion_df,
        time_col,
        period_start,
        period_end,
    )

    employees = db.query(Employee).all()
    employee_index: dict[str, list[dict[str, Any]]] = {}
    attendance_employee_id_index: dict[str, list[dict[str, Any]]] = {}
    normalized_notion_directory = _normalize_notion_employee_directory(notion_employee_directory)

    employee_type_by_id: dict[int, str] = {}
    for emp in employees:
        employee_type_by_id[emp.id] = str(emp.employee_type or "FULLTIME").upper()
        emp_dict = {
            "id": emp.id,
            "employee_id": emp.machine_employee_id,
            "employee_name": emp.full_name,
            "full_name": emp.full_name,
        }
        normalized_employee_id = _normalize_key(str(emp.machine_employee_id or ""))
        if normalized_employee_id:
            attendance_employee_id_index.setdefault(normalized_employee_id, []).append(emp_dict)
        for raw_key in [emp.notion_name, emp.machine_employee_id, emp.full_name]:
            normalized_key = _normalize_key(str(raw_key or ""))
            if normalized_key:
                employee_index.setdefault(normalized_key, []).append(emp_dict)

    if period_start and period_end:
        db.query(OffRequest).filter(
            OffRequest.start_date <= period_end,
            OffRequest.end_date >= period_start
        ).delete()
        db.commit()

    for _, row in notion_df.iterrows():
        # WFH affects the preview/committed attendance symbol but is not an
        # off-request: it must not consume or create leave balance entries.
        submission_kind = _get_notion_submission_kind(row.get(name_col)) if name_col is not None else "leave"
        if submission_kind != "leave":
            continue

        employee_name_candidates = _collect_employee_name_candidates(
            row.get(employee_link_col) if employee_link_col is not None else None,
            row.get(leave_balance_col),
        )
        if not employee_name_candidates:
            continue

        date_range = _parse_date_range(row.get(time_col), fmt=detected_fmt)
        if date_range is None:
            continue

        if period_start and date_range[1] < period_start:
            continue
        if period_end and date_range[0] > period_end:
            continue

        leave_units = _parse_leave_units(row.get(leave_days_col)) if leave_days_col is not None else None
        if leave_units is not None and leave_units <= 0:
            continue

        matched_employees = _find_matching_employees_from_directory(
            attendance_employee_id_index,
            normalized_notion_directory,
            employee_name_candidates,
        )
        if not matched_employees:
            matched_employees = _find_matching_employees(employee_index, employee_name_candidates)
        if not matched_employees:
            continue

        notion_status = str(row.get(status_col) or "submitted").strip() if status_col is not None else "submitted"
        if _is_inactive_notion_status(notion_status):
            continue

        reason = str(row.get(reason_col) or "").strip() if reason_col is not None else ""
        ly_do_nghi_col = _resolve_column(notion_df, "ly_do_nghi")
        ly_do_nghi_val = str(row.get(ly_do_nghi_col) or "").strip() if ly_do_nghi_col else ""
        
        leave_session = _resolve_half_day_leave_session(
            row.get(time_col),
            leave_units,
            is_single_day_leave=date_range[0] == date_range[1],
        )

        request_type = "paid_leave"
        reason_lower = (reason + " " + ly_do_nghi_val).lower()
        is_unpaid = "không lương" in reason_lower or "khong luong" in reason_lower or "unpaid" in reason_lower

        if leave_session == "morning":
            request_type = "unpaid_leave_am" if is_unpaid else "paid_leave_am"
            total_days_val = 0.5
        elif leave_session == "afternoon":
            request_type = "unpaid_leave_pm" if is_unpaid else "paid_leave_pm"
            total_days_val = 0.5
        else:
            request_type = "unpaid_leave" if is_unpaid else "paid_leave"
            total_days_val = leave_units or 1.0

        for emp_dict in matched_employees:
            emp_id = emp_dict["id"]
            # Học việc/thử việc không có phép năm. Các đơn nghỉ nhập từ
            # Notion được lưu là nghỉ không lương để toàn bộ luồng tính dùng
            # cùng một quy tắc với template Final của kế toán.
            if employee_type_by_id.get(emp_id, "FULLTIME") != "FULLTIME":
                if leave_session == "morning":
                    request_type = "unpaid_leave_am"
                elif leave_session == "afternoon":
                    request_type = "unpaid_leave_pm"
                else:
                    request_type = "unpaid_leave"
            
            existing = db.query(OffRequest).filter(
                OffRequest.employee_id == emp_id,
                OffRequest.start_date == date_range[0],
                OffRequest.end_date == date_range[1],
                OffRequest.request_type == request_type,
            ).first()
            if existing:
                continue

            off_req = OffRequest(
                employee_id=emp_id,
                request_type=request_type,
                start_date=date_range[0],
                end_date=date_range[1],
                total_days=total_days_val,
                reason=reason or ly_do_nghi_val or "Notion Leave Request",
                status="approved"
            )
            db.add(off_req)
    db.commit()


def sync_notion_work_from_home_to_attendance_db(
    db: Session,
    notion_csv_path: str | Path | bytes | bytearray | BytesIO,
    notion_employee_directory: Mapping[str, str | list[str] | tuple[str, ...]] | None = None,
    period_start: date | None = None,
    period_end: date | None = None,
) -> int:
    """Persist active Notion WFH entries as working days in AttendanceDaily.

    WFH is deliberately kept out of ``off_requests``: it is normal work and
    must neither consume leave quota nor appear as paid leave.  Returning the
    number of affected dates makes this operation straightforward to audit.
    """
    from app.models.attendance_daily import AttendanceDaily
    from app.models.employee import Employee
    from app.models.monthly_salary_input import MonthlySalaryInput
    from app.models.timesheet import Timesheet
    from app.models.timesheet_entry import TimesheetEntry
    from app.services.final_timesheet_report import (
        _absent_units_for_symbol,
        _paid_leave_units_for_symbol,
        _work_units_for_symbol,
    )

    if period_start is None or period_end is None:
        return 0

    notion_df = _load_notion_dataframe(notion_csv_path)
    if notion_df.empty:
        return 0

    leave_balance_col = _resolve_column(notion_df, "leave_balance")
    time_col = _resolve_column(notion_df, "thoi_gian")
    employee_link_col = _resolve_column(notion_df, "ten_nhan_vien")
    name_col = _resolve_column(notion_df, "name")
    status_col = _resolve_column(notion_df, "trang_thai")
    if leave_balance_col is None or time_col is None:
        raise ValueError("File Notion thiáº¿u cá»™t Leave Balance hoáº·c Thá»i Gian")

    notion_df, detected_fmt = _select_notion_rows_for_period(
        notion_df,
        time_col,
        period_start,
        period_end,
    )
    if notion_df.empty:
        return 0

    employee_index: dict[str, list[dict[str, Any]]] = {}
    attendance_employee_id_index: dict[str, list[dict[str, Any]]] = {}
    normalized_notion_directory = _normalize_notion_employee_directory(notion_employee_directory)
    for emp in db.query(Employee).all():
        employee_data = {
            "id": emp.id,
            "employee_id": emp.machine_employee_id,
            "employee_name": emp.full_name,
            "full_name": emp.full_name,
        }
        normalized_machine_id = _normalize_key(str(emp.machine_employee_id or ""))
        if normalized_machine_id:
            attendance_employee_id_index.setdefault(normalized_machine_id, []).append(employee_data)
        for raw_key in [emp.notion_name, emp.machine_employee_id, emp.full_name]:
            normalized_key = _normalize_key(str(raw_key or ""))
            if normalized_key:
                employee_index.setdefault(normalized_key, []).append(employee_data)

    affected_dates = 0
    affected_timesheet_ids: set[int] = set()
    for _, row in notion_df.iterrows():
        if _get_notion_submission_kind(row.get(name_col)) != "work_from_home":
            continue
        notion_status = str(row.get(status_col) or "submitted").strip() if status_col is not None else "submitted"
        if _is_inactive_notion_status(notion_status):
            continue
        date_range = _parse_date_range(row.get(time_col), fmt=detected_fmt)
        if date_range is None:
            continue
        employee_name_candidates = _collect_employee_name_candidates(
            row.get(employee_link_col) if employee_link_col is not None else None,
            row.get(leave_balance_col),
        )
        matched_employees = _find_matching_employees_from_directory(
            attendance_employee_id_index,
            normalized_notion_directory,
            employee_name_candidates,
        )
        if not matched_employees:
            matched_employees = _find_matching_employees(employee_index, employee_name_candidates)

        for employee in matched_employees:
            for work_date in _iter_weekdays(*date_range):
                if work_date < period_start or work_date > period_end:
                    continue
                daily = db.query(AttendanceDaily).filter(
                    AttendanceDaily.employee_id == employee["id"],
                    AttendanceDaily.work_date == work_date,
                ).first()
                if daily is None:
                    daily = AttendanceDaily(
                        employee_id=employee["id"],
                        work_date=work_date,
                        period_start=period_start,
                        period_end=period_end,
                        attendance_symbol="X",
                        abnormal_level=None,
                        source_priority=1,
                    )
                    db.add(daily)
                else:
                    daily.attendance_symbol = "X"
                    daily.abnormal_level = None
                    daily.period_start = period_start
                    daily.period_end = period_end

                timesheet = db.query(Timesheet).filter(
                    Timesheet.employee_id == employee["id"],
                    Timesheet.period_start == period_start,
                    Timesheet.period_end == period_end,
                ).first()
                if timesheet is not None:
                    entry = db.query(TimesheetEntry).filter(
                        TimesheetEntry.timesheet_id == timesheet.id,
                        TimesheetEntry.employee_id == employee["id"],
                        TimesheetEntry.work_date == work_date,
                    ).first()
                    if entry is None:
                        db.add(
                            TimesheetEntry(
                                timesheet_id=timesheet.id,
                                employee_id=employee["id"],
                                work_date=work_date,
                                original_symbol="X",
                                final_symbol="X",
                                is_overridden=False,
                            )
                        )
                    elif not entry.is_overridden:
                        entry.original_symbol = "X"
                        entry.final_symbol = "X"
                    affected_timesheet_ids.add(timesheet.id)
                affected_dates += 1

    db.commit()

    # Keep saved timesheet and salary-day totals consistent for imports that
    # were already committed before the WFH rule was introduced.
    for timesheet_id in affected_timesheet_ids:
        timesheet = db.get(Timesheet, timesheet_id)
        if timesheet is None:
            continue
        entries = db.query(TimesheetEntry).filter(TimesheetEntry.timesheet_id == timesheet.id).all()
        timesheet.total_work_days = float(sum(_work_units_for_symbol(entry.final_symbol) for entry in entries))
        timesheet.total_paid_leave_days = float(sum(_paid_leave_units_for_symbol(entry.final_symbol) for entry in entries))
        absent_days = float(sum(_absent_units_for_symbol(entry.final_symbol) for entry in entries))
        timesheet.total_unpaid_leave_days = absent_days
        timesheet.total_absent_days = absent_days
        timesheet.total_late_minutes = sum(int(entry.late_minutes or 0) for entry in entries)
        timesheet.total_business_trip_days = float(sum(1.0 for entry in entries if entry.final_symbol == "CT"))

        salary_period = period_end.strftime("%Y-%m")
        salary_input = db.query(MonthlySalaryInput).filter(
            MonthlySalaryInput.employee_id == timesheet.employee_id,
            MonthlySalaryInput.salary_period == salary_period,
        ).first()
        if salary_input is not None:
            salary_input.actual_working_days = timesheet.total_work_days + timesheet.total_paid_leave_days

    db.commit()
    return affected_dates
