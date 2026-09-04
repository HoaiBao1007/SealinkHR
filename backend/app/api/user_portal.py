from datetime import date, datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_personal_portal_user
from app.core.auth import get_password_hash, verify_password
from app.models.user import User
from app.models.employee import Employee
from app.models.monthly_salary_input import MonthlySalaryInput
from app.models.timesheet_entry import TimesheetEntry
from app.models.attendance_log import AttendanceLog
from app.models.attendance_daily import AttendanceDaily
from app.models.commission import CommissionJob, CommissionPaymentVerification, CommissionPeriod, CommissionWalletLedger
from app.services.salary import cake_salary, calculate_period_working_days, clean_name_for_match, get_commission_payslip_summary
from app.services.audit_service import record_audit
from app.services.notification_service import BONUS, actor_id, add_notification

router = APIRouter(prefix="/api/user", tags=["user_portal"])


class HeldBonusRequestIn(BaseModel):
    note: Optional[str] = None


class MyAccountUpdateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    personal_email: Optional[str] = Field(default=None, max_length=150)
    phone_number: Optional[str] = Field(default=None, max_length=50)
    username: Optional[str] = Field(default=None, min_length=3, max_length=100, pattern=r"^[A-Za-z0-9._@-]+$")
    current_password: Optional[str] = Field(default=None, max_length=200)
    new_password: Optional[str] = Field(default=None, min_length=8, max_length=200)


def _portal_employee(db: Session, current_user: User) -> Employee:
    employee = db.query(Employee).filter(Employee.user_id == current_user.id).first()
    if not employee:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tài khoản của bạn chưa được liên kết với hồ sơ nhân sự.",
        )
    return employee


def _optional_text(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def _my_account_payload(employee: Employee, current_user: User) -> dict:
    return {
        "employee_id": employee.id,
        "employee_code": employee.employee_code,
        "machine_employee_id": employee.machine_employee_id,
        "full_name": employee.full_name,
        "notion_name": employee.notion_name,
        "department_name": employee.department_name,
        "position": employee.position,
        "company_email": employee.company_email,
        "company_phone_number": employee.company_phone_number,
        "personal_email": employee.personal_email,
        "phone_number": employee.phone_number,
        "username": current_user.username,
        "role": current_user.role,
        "created_at": current_user.created_at,
        "updated_at": current_user.updated_at,
    }


@router.get("/my-account")
def get_my_account(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_personal_portal_user),
):
    employee = _portal_employee(db, current_user)
    return _my_account_payload(employee, current_user)


@router.patch("/my-account")
def update_my_account(
    payload: MyAccountUpdateIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_personal_portal_user),
):
    employee = _portal_employee(db, current_user)
    fields = payload.model_fields_set
    before = {
        "personal_email": employee.personal_email,
        "phone_number": employee.phone_number,
        "username": current_user.username,
        "password_changed": False,
    }

    requested_username = payload.username.strip() if payload.username is not None else current_user.username
    username_changed = "username" in fields and requested_username != current_user.username
    password_changed = "new_password" in fields and bool(payload.new_password)
    if username_changed or password_changed:
        if not payload.current_password or not verify_password(payload.current_password, current_user.password_hash):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Mật khẩu hiện tại không chính xác.",
            )

    if username_changed:
        duplicate = (
            db.query(User)
            .filter(func.lower(User.username) == requested_username.lower(), User.id != current_user.id)
            .first()
        )
        if duplicate:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Tên đăng nhập đã được sử dụng.")
        current_user.username = requested_username

    if password_changed:
        current_user.password_hash = get_password_hash(payload.new_password or "")

    if "personal_email" in fields:
        personal_email = _optional_text(payload.personal_email)
        if personal_email and ("@" not in personal_email or personal_email.startswith("@") or personal_email.endswith("@")):
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Email cá nhân không hợp lệ.")
        employee.personal_email = personal_email
    if "phone_number" in fields:
        employee.phone_number = _optional_text(payload.phone_number)

    after = {
        "personal_email": employee.personal_email,
        "phone_number": employee.phone_number,
        "username": current_user.username,
        "password_changed": password_changed,
    }
    record_audit(
        db,
        actor=current_user,
        action="PERSONAL_ACCOUNT_UPDATE",
        resource_type="USER_ACCOUNT",
        resource_id=current_user.id,
        summary="Người dùng cập nhật thông tin tài khoản cá nhân.",
        before=before,
        after=after,
    )
    db.commit()
    db.refresh(current_user)
    db.refresh(employee)
    return _my_account_payload(employee, current_user)


def _held_amounts(entries: list[CommissionWalletLedger]) -> tuple[float, float]:
    """Read a JOB hold from immutable wallet rows without changing balances."""
    payment_hold_types = {"ACCRUAL_HELD", "ADJUSTMENT_HELD", "REVERSAL_HELD", "PAYMENT_STATUS_HOLD"}
    payment_hold = released = manual_hold = manual_released = 0.0
    for entry in entries:
        amount = float(entry.amount or 0.0)
        if entry.entry_type in payment_hold_types:
            payment_hold += amount
        elif entry.entry_type == "RELEASED":
            released += amount
        elif entry.entry_type in {"MANUAL_HOLD", "MANUAL_HOLD_REVERSAL"}:
            manual_hold += amount
        elif entry.entry_type in {"MANUAL_RELEASE", "MANUAL_RELEASE_REVERSAL"}:
            manual_released += amount
    return (
        max(0.0, round(payment_hold - released, 2)),
        max(0.0, round(manual_hold - manual_released, 2)),
    )


def _format_vnd(value: object) -> str:
    return f"{round(float(value or 0)):,}".replace(",", ".") + " VND"


def _format_salary_period(period: str) -> str:
    try:
        year, month = period.split("-")
        return f"Tháng {month}/{year}"
    except ValueError:
        return period


def _payslip_font_names() -> tuple[str, str]:
    """Use a Unicode font so Vietnamese remains selectable text in the PDF."""
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    regular_candidates = [
        Path("C:/Windows/Fonts/arial.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    ]
    bold_candidates = [
        Path("C:/Windows/Fonts/arialbd.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    ]
    regular = next((path for path in regular_candidates if path.exists()), None)
    bold = next((path for path in bold_candidates if path.exists()), None)
    if regular and bold:
        if "SealinkPayslip" not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont("SealinkPayslip", str(regular)))
            pdfmetrics.registerFont(TTFont("SealinkPayslipBold", str(bold)))
        return "SealinkPayslip", "SealinkPayslipBold"
    return "Helvetica", "Helvetica-Bold"


def _build_text_payslip_pdf(data: dict) -> BytesIO:
    """Build a selectable-text payslip; no screenshot or canvas is used."""
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_RIGHT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import HRFlowable, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    normal_font, bold_font = _payslip_font_names()
    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=13 * mm,
        leftMargin=13 * mm,
        topMargin=12 * mm,
        bottomMargin=12 * mm,
        title=f"Phiếu lương {data.get('employee_code') or 'nhan-vien'} {data.get('salary_period')}",
        author="SEALINK INTERNATIONAL",
    )
    styles = getSampleStyleSheet()
    base = ParagraphStyle("SealinkBase", parent=styles["Normal"], fontName=normal_font, fontSize=8.2, leading=11, textColor=colors.HexColor("#172033"))
    small = ParagraphStyle("SealinkSmall", parent=base, fontSize=7.3, leading=9.5, textColor=colors.HexColor("#64748B"))
    bold = ParagraphStyle("SealinkBold", parent=base, fontName=bold_font)
    heading = ParagraphStyle("SealinkHeading", parent=bold, fontSize=15, leading=18, textColor=colors.HexColor("#102B49"))
    section = ParagraphStyle("SealinkSection", parent=bold, fontSize=8.4, leading=11, textColor=colors.HexColor("#475569"), spaceAfter=4)
    right = ParagraphStyle("SealinkRight", parent=base, alignment=TA_RIGHT)
    right_bold = ParagraphStyle("SealinkRightBold", parent=bold, alignment=TA_RIGHT)
    center = ParagraphStyle("SealinkCenter", parent=base, alignment=TA_CENTER)

    def paragraph(value: object, style: ParagraphStyle = base) -> Paragraph:
        safe = str(value if value is not None else "—").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        return Paragraph(safe, style)

    inputs = data.get("inputs") or {}
    calculations = data.get("calculations") or {}
    period = str(data.get("salary_period") or "")
    actual_days = float(inputs.get("actual_working_days") or 0)
    standard_days = calculate_period_working_days(period)
    actual_salary = float(calculations.get("actual_salary") or 0)
    meal = float(inputs.get("meal_allowance_free") or 0) + float(inputs.get("meal_allowance_tax") or 0)
    phone = float(inputs.get("phone_allowance_free") or 0)
    transport = float(inputs.get("trans_allowance_tax") or 0)
    performance = float(inputs.get("perf_allowance_tax") or 0)
    other_income = float(inputs.get("other_income") or 0)
    bonus = float(inputs.get("bonus") or 0)
    sales_bonus = float(inputs.get("sales_bonus") or 0)
    pit_refund = float(inputs.get("pit_refund") or 0)
    insurance = float(calculations.get("total_ins_emp") or 0)
    pit_tax = float(calculations.get("pit_tax") or 0)
    union_fee = float(calculations.get("union_fee") or 0)
    advance = float(inputs.get("advance_payment") or 0)
    other_deductions = float(inputs.get("other_deductions") or 0)
    gross = actual_salary + meal + phone + transport + performance + other_income + bonus + sales_bonus + pit_refund
    deductions_total = insurance + pit_tax + union_fee + advance + other_deductions
    net_pay = float(calculations.get("final_transfer") or 0)

    story = [HRFlowable(width="100%", thickness=2, color=colors.HexColor("#163B66")), Spacer(1, 7)]
    header_left = [paragraph("SEALINK INTERNATIONAL", heading), paragraph("TIỀN LƯƠNG & CHẾ ĐỘ ĐÃI NGỘ", ParagraphStyle("BrandSub", parent=bold, fontSize=7.4, leading=10, textColor=colors.HexColor("#475569")))]
    header_right = [paragraph("PHIẾU LƯƠNG / PAYSLIP", ParagraphStyle("Tag", parent=bold, fontSize=7, alignment=TA_RIGHT, textColor=colors.HexColor("#163B66"))), paragraph(_format_salary_period(period), ParagraphStyle("Period", parent=bold, fontSize=12, alignment=TA_RIGHT, textColor=colors.HexColor("#102B49"))), paragraph(f"Ngày phát hành: {date.today().strftime('%d/%m/%Y')}", small)]
    header_table = Table([[header_left, header_right]], colWidths=[111 * mm, 70 * mm])
    header_table.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("ALIGN", (1, 0), (1, 0), "RIGHT"), ("BOTTOMPADDING", (0, 0), (-1, -1), 8)]))
    story.extend([header_table, HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#CBD5E1")), Spacer(1, 9)])

    pay_month = int(period.split("-")[1]) if "-" in period else 0
    pay_year = int(period.split("-")[0]) if "-" in period else 0
    if pay_month == 12:
        pay_month, pay_year = 1, pay_year + 1
    else:
        pay_month += 1
    pay_date = f"25/{pay_month:02d}/{pay_year}" if pay_month else "N/A"
    employee_rows = [
        [paragraph(f"Họ và tên: {data.get('employee_name') or 'N/A'}", bold), paragraph(f"Mã nhân viên: {data.get('employee_code') or 'N/A'}", bold)],
        [paragraph(f"Chức vụ: {data.get('position') or 'N/A'}", bold), paragraph(f"Ngày vào làm: {data.get('start_date') or 'N/A'}", bold)],
        [paragraph(f"Kỳ thanh toán: {_format_salary_period(period)}", bold), paragraph(f"Ngày chi trả: {pay_date}", bold)],
    ]
    employee_table = Table(employee_rows, colWidths=[56 * mm, 56 * mm])
    employee_table.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -1), 0.25, colors.HexColor("#E2E8F0")), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
    net_box = Table([[paragraph("THỰC NHẬN CHUYỂN KHOẢN", ParagraphStyle("NetLabel", parent=bold, fontSize=7.2, alignment=TA_CENTER, textColor=colors.HexColor("#047857"))),], [paragraph(_format_vnd(net_pay), ParagraphStyle("NetValue", parent=bold, fontSize=14, alignment=TA_CENTER, textColor=colors.HexColor("#047857"))),], [paragraph(f"Ngày công: {actual_days:g} / {standard_days} ngày | Nghỉ không công: {max(0, standard_days - actual_days):g} ngày", ParagraphStyle("NetMeta", parent=small, alignment=TA_CENTER, textColor=colors.HexColor("#065F46"))) ]], colWidths=[58 * mm])
    net_box.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F0FDF4")), ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#86EFAC")), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
    summary_table = Table([[employee_table, net_box]], colWidths=[114 * mm, 62 * mm])
    summary_table.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story.extend([paragraph("TÓM TẮT NHÂN VIÊN / EMPLOYEE SUMMARY", section), summary_table, Spacer(1, 8)])
    employee_type_label = {
        "FULLTIME": "Chính thức",
        "PROBATION": "Thử việc",
        "INTERN": "Học việc",
        "TRAINEE": "Thực tập",
    }.get(data.get("employee_type"), "Chính thức")
    story.append(paragraph(f"Tài khoản: {data.get('account_number') or 'N/A'} ({data.get('bank_name') or 'N/A'}) | Hợp đồng: {employee_type_label}", small))
    story.extend([Spacer(1, 7), HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#CBD5E1")), Spacer(1, 8)])

    commission = data.get("commission_summary") or {}
    cycles = commission.get("cycles") or []
    if cycles:
        cycle_labels = " · ".join(str(cycle.get("period_label") or "") for cycle in cycles)
        commission_cards = Table([[paragraph("TỔNG THƯỞNG QUÝ", bold), paragraph("NHẬN TRONG KỲ", bold), paragraph("CÒN LẠI SAU KỲ NÀY", bold)], [paragraph(_format_vnd(commission.get("total_bonus_quarter")), ParagraphStyle("CardValue1", parent=bold, fontSize=11)), paragraph(_format_vnd(commission.get("current_period_bonus")), ParagraphStyle("CardValue2", parent=bold, fontSize=11, textColor=colors.HexColor("#047857"))), paragraph(_format_vnd(commission.get("remaining_bonus")), ParagraphStyle("CardValue3", parent=bold, fontSize=11, textColor=colors.HexColor("#B45309")))]], colWidths=[58 * mm, 58 * mm, 58 * mm])
        commission_cards.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#BAE6FD")), ("INNERGRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#E2E8F0")), ("BACKGROUND", (1, 0), (1, -1), colors.HexColor("#F0FDF4")), ("BACKGROUND", (2, 0), (2, -1), colors.HexColor("#FFFBEB")), ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7), ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
        plans = []
        for cycle in cycles:
            months = ", ".join(_format_salary_period(str(item)) for item in (cycle.get("payout_periods") or []))
            plans.append(f"{cycle.get('period_label')}: {months}")
        story.extend([paragraph("TỔNG HỢP THƯỞNG DOANH SỐ THEO QUÝ", section), paragraph(f"Dữ liệu chỉ đọc từ ví thưởng commission. Kỳ nguồn: {cycle_labels}.", small), Spacer(1, 5), commission_cards, Spacer(1, 5), paragraph("Kế hoạch chi trả: " + " · ".join(plans) + ". “Còn lại” là phần dự kiến thuộc các tháng sau của cùng chu kỳ chi trả.", small), Spacer(1, 8)])

    note_lines: list[str] = []
    if inputs.get("is_mid_month_change"):
        old_days = float(inputs.get("prorated_days_old") or 0)
        new_days = float(inputs.get("prorated_days_new") or 0)
        total_days = old_days + new_days
        ratio = min(1.0, actual_days / standard_days) if standard_days else 0
        old_amount = round((float(inputs.get("prorated_old_salary") or 0) * old_days / total_days) * ratio) if total_days else 0
        new_amount = round(actual_salary - old_amount)
        effective = str(inputs.get("mid_month_effective_date") or "")
        try:
            effective_date = date.fromisoformat(effective)
            previous_end = effective_date - timedelta(days=1)
            previous_range = f"23/{(effective_date.replace(day=1) - timedelta(days=1)).strftime('%m/%Y')} đến {previous_end.strftime('%d/%m/%Y')}"
            new_range = f"{effective_date.strftime('%d/%m/%Y')} đến 22/{period.split('-')[1]}/{period.split('-')[0]}"
        except ValueError:
            previous_range, new_range = "đầu kỳ đến ngày hiệu lực", "từ ngày hiệu lực đến cuối kỳ"
        note_lines.extend([
            f"Mức cũ: {old_days:g} ngày ({previous_range}): {_format_vnd(inputs.get('prorated_old_salary'))} → {_format_vnd(old_amount)}.",
            f"Mức mới: {new_days:g} ngày ({new_range}): {_format_vnd(inputs.get('prorated_new_salary'))} → {_format_vnd(new_amount)}.",
        ])
    if note_lines:
        story.extend([paragraph("GHI CHÚ ĐIỀU CHỈNH LƯƠNG", section), *[paragraph("• " + line, small) for line in note_lines], Spacer(1, 8)])

    def amount_table(rows: list[tuple[str, float]], total_label: str, total_amount: float, deduction: bool = False) -> Table:
        body = [[paragraph("KHOẢN MỤC", ParagraphStyle("TableHead", parent=bold, fontSize=7.3)), paragraph("SỐ TIỀN", ParagraphStyle("TableHeadR", parent=bold, fontSize=7.3, alignment=TA_RIGHT))]]
        for label, amount in rows:
            if amount > 0:
                body.append([paragraph(label), paragraph(("-" if deduction else "") + _format_vnd(amount), right_bold)])
        if len(body) == 1:
            body.append([paragraph("Không phát sinh", small), paragraph("—", right)])
        body.append([paragraph(total_label, bold), paragraph(("-" if deduction else "") + _format_vnd(total_amount), right_bold)])
        table = Table(body, colWidths=[61 * mm, 31 * mm])
        table.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -2), 0.25, colors.HexColor("#E2E8F0")), ("LINEABOVE", (0, -1), (-1, -1), 0.5, colors.HexColor("#94A3B8")), ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#F8FAFC")), ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4), ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
        return table

    earning_rows = [("Lương thực tế theo ngày công", actual_salary), ("Phụ cấp ăn trưa", meal), ("Phụ cấp điện thoại", phone), ("Phụ cấp xăng xe", transport), ("Phụ cấp hiệu suất / khác", performance), ("Thu nhập bổ sung khác", other_income), ("Tiền thưởng (Bonus)", bonus), ("Tiền thưởng doanh số", sales_bonus), ("Hoàn thuế PIT", pit_refund)]
    deduction_rows = [("Bảo hiểm bắt buộc", insurance), ("Thuế thu nhập cá nhân (PIT)", pit_tax), ("Đoàn phí công đoàn", union_fee), ("Tạm ứng lương", advance), ("Khấu trừ khác", other_deductions)]
    earnings_table = amount_table(earning_rows, "Tổng thu nhập", gross)
    deductions_table = amount_table(deduction_rows, "Tổng khấu trừ", deductions_total, deduction=True)
    story.extend([Table([[paragraph("THU NHẬP / EARNINGS", section)], [earnings_table]], colWidths=[92 * mm]), Table([[paragraph("KHẤU TRỪ / DEDUCTIONS", section)], [deductions_table]], colWidths=[92 * mm])])
    # The two tables are intentionally placed side by side using a wrapper.
    story[-2:] = [Table([[Table([[paragraph("THU NHẬP / EARNINGS", section)], [earnings_table]], colWidths=[92 * mm]), Table([[paragraph("KHẤU TRỪ / DEDUCTIONS", section)], [deductions_table]], colWidths=[92 * mm])]], colWidths=[92 * mm, 92 * mm], hAlign="LEFT"), Spacer(1, 10)]
    net_table = Table([[[paragraph("TỔNG THỰC NHẬN / TOTAL NET PAYABLE", bold), paragraph("Lương thực chuyển = Tổng thu nhập - Tổng khấu trừ", small)], paragraph(_format_vnd(net_pay), ParagraphStyle("FinalNet", parent=bold, fontSize=15, alignment=TA_RIGHT, textColor=colors.HexColor("#047857")))]], colWidths=[121 * mm, 55 * mm])
    net_table.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F0FDF4")), ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#86EFAC")), ("TOPPADDING", (0, 0), (-1, -1), 9), ("BOTTOMPADDING", (0, 0), (-1, -1), 9), ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
    other_income_note = str(inputs.get("other_income_note") or "").strip()
    if other_income > 0 and other_income_note:
        story.extend([
            paragraph("GHI CHÚ THU NHẬP KHÁC", section),
            paragraph(other_income_note, small),
            Spacer(1, 8),
        ])
    story.extend([net_table, Spacer(1, 6), paragraph("Bằng chữ: " + str(net_pay), ParagraphStyle("Words", parent=small, alignment=TA_RIGHT, fontName=bold_font)), Spacer(1, 10), HRFlowable(width="100%", thickness=0.4, color=colors.HexColor("#CBD5E1")), Spacer(1, 4), paragraph("Mọi thắc mắc về số liệu vui lòng liên hệ phòng Kế toán trước ngày 25 hàng tháng. Tài liệu được hệ thống tự động xuất, không yêu cầu chữ ký tay.", small)])
    document.build(story)
    buffer.seek(0)
    return buffer


def _latest_completed_payroll_period(reference: date | None = None) -> str:
    """Return the previous calendar month in YYYY-MM format."""
    current = reference or date.today()
    previous_month_last_day = current.replace(day=1) - timedelta(days=1)
    return previous_month_last_day.strftime("%Y-%m")


def _order_payslip_periods_for_default(
    periods: list[str],
    reference: date | None = None,
) -> list[str]:
    """Put the newest issued, completed payroll month first.

    Future/current published rows remain selectable for audit purposes, but
    they must not become the employee portal's automatic selection.
    """
    cutoff = _latest_completed_payroll_period(reference)
    unique_periods = sorted(set(periods), reverse=True)
    completed = [period for period in unique_periods if period <= cutoff]
    current_or_future = [period for period in unique_periods if period > cutoff]
    return completed + current_or_future


@router.get("/my-payslip-periods")
def get_my_payslip_periods(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_personal_portal_user),
):
    """Return only periods that the employee can actually open.

    The user portal uses this list for its selector, so it never probes
    arbitrary/unpublished months and creates avoidable 403/404 requests.
    """
    employee = db.query(Employee).filter(Employee.user_id == current_user.id).first()
    if not employee:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tài khoản của bạn chưa được liên kết với hồ sơ nhân sự.",
        )
    periods = (
        db.query(MonthlySalaryInput.salary_period)
        .filter(
            MonthlySalaryInput.employee_id == employee.id,
            MonthlySalaryInput.is_published.is_(True),
        )
        .order_by(MonthlySalaryInput.salary_period.desc())
        .all()
    )
    return _order_payslip_periods_for_default([item[0] for item in periods])


@router.get("/my-held-bonus-jobs")
def get_my_held_bonus_jobs(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_personal_portal_user),
):
    """List only the authenticated employee's JOBs that still have a hold.

    This is a read-only employee view over the same immutable ledger used by
    accounting.  It deliberately never releases or recalculates bonus money.
    """
    employee = _portal_employee(db, current_user)
    employee_name = clean_name_for_match(employee.full_name)
    jobs = [
        job for job in db.query(CommissionJob).join(CommissionPeriod).filter(
            CommissionPeriod.is_voided.is_(False),
        ).order_by(CommissionPeriod.from_date.desc(), CommissionJob.id.desc()).all()
        if clean_name_for_match(job.sales_rep or "") == employee_name
    ]
    if not jobs:
        return []

    job_ids = [job.id for job in jobs]
    entries_by_job: dict[int, list[CommissionWalletLedger]] = {job_id: [] for job_id in job_ids}
    for entry in db.query(CommissionWalletLedger).filter(CommissionWalletLedger.job_id.in_(job_ids)).order_by(CommissionWalletLedger.id).all():
        if entry.job_id is not None:
            entries_by_job.setdefault(entry.job_id, []).append(entry)
    verifications = {
        item.job_id: item
        for item in db.query(CommissionPaymentVerification).filter(
            CommissionPaymentVerification.job_id.in_(job_ids),
        ).all()
    }

    result = []
    for job in jobs:
        payment_held, manual_held = _held_amounts(entries_by_job.get(job.id, []))
        total_held = round(payment_held + manual_held, 2)
        if total_held < 0.005:
            continue
        verification = verifications.get(job.id)
        verification_status = verification.status if verification else "NONE"
        if verification_status == "CANCELLED":
            verification_status = "NONE"
        result.append({
            "job_id": job.id,
            "period_id": job.period_id,
            "period_label": job.period.period_label if job.period else f"Kỳ #{job.period_id}",
            "job_no": job.job_no,
            "customer": job.customer,
            "payment_received": job.payment_received or "NO",
            "payment_held": payment_held,
            "manual_held": manual_held,
            "total_held": total_held,
            "request_status": verification_status,
            "request_note": verification.report_note if verification else None,
            "accounting_note": verification.verification_note if verification else None,
            "can_request": payment_held >= 0.005 and verification_status in {"NONE", "REJECTED"},
        })
    return result


@router.post("/my-held-bonus-jobs/{job_id}/request-accounting")
def request_accounting_payout_for_my_job(
    job_id: int,
    payload: HeldBonusRequestIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_personal_portal_user),
):
    """Let a Sales employee notify accounting about one still-held JOB.

    It creates the existing PENDING verification workflow only.  Payment
    Received, the bonus balance, and ledger history are not modified here.
    """
    employee = _portal_employee(db, current_user)
    job = db.get(CommissionJob, job_id)
    if not job or clean_name_for_match(job.sales_rep or "") != clean_name_for_match(employee.full_name):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy JOB bonus của bạn.")

    payment_held, _manual_held = _held_amounts(
        db.query(CommissionWalletLedger).filter(CommissionWalletLedger.job_id == job.id).order_by(CommissionWalletLedger.id).all()
    )
    if payment_held < 0.005:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="JOB này không còn bonus giữ tự động để yêu cầu kế toán duyệt.")
    verification = db.query(CommissionPaymentVerification).filter(CommissionPaymentVerification.job_id == job.id).first()
    if verification and verification.status in {"PENDING", "VERIFIED", "COMMAND_CREATED"}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="JOB này đã có yêu cầu kế toán đang được xử lý.")

    note = payload.note.strip() if payload.note and payload.note.strip() else "Nhân viên yêu cầu kế toán kiểm tra thanh toán và duyệt lệnh chi trả bonus theo JOB."
    actor = current_user.username or str(current_user.id)
    if verification:
        verification.status = "PENDING"
        verification.report_note = note
        verification.verification_note = None
        verification.reported_by = actor
        verification.reported_at = datetime.now(timezone.utc)
        verification.verified_by = None
        verification.verified_at = None
        verification.command_created_by = None
        verification.command_created_at = None
    else:
        verification = CommissionPaymentVerification(
            period_id=job.period_id,
            job_id=job.id,
            sales_rep=job.sales_rep or employee.full_name,
            status="PENDING",
            report_note=note,
            reported_by=actor,
        )
        db.add(verification)
    db.add(CommissionWalletLedger(
        period_id=job.period_id,
        job_id=job.id,
        sales_rep=job.sales_rep or employee.full_name,
        employee_id=employee.id,
        entry_type="PAYMENT_REPORTED",
        amount=0.0,
        reason_code="EMPLOYEE_REQUESTED_ACCOUNTING_REVIEW",
        note=note,
        created_by=actor,
    ))
    period_label = job.period.period_label if job.period else f"Kỳ #{job.period_id}"
    add_notification(
        db,
        category=BONUS,
        event_type="BONUS_PAYOUT_REQUESTED",
        title=f"Yêu cầu duyệt chi trả bonus JOB {job.job_no}",
        message=(
            f"{employee.full_name} đã yêu cầu kế toán kiểm tra và duyệt chi trả "
            f"{payment_held:,.0f} VND đang giữ của JOB {job.job_no}, kỳ nguồn {period_label}."
        ),
        actor_user_id=actor_id(current_user),
        resource_type="COMMISSION_JOB",
        resource_id=job.id,
        action_url="/admin/commission",
    )
    db.commit()
    return {"message": "Đã gửi yêu cầu đến kế toán. Bonus vẫn được giữ nguyên cho đến khi kế toán xác minh và lập lệnh chi trả.", "status": "PENDING"}


@router.get("/my-payslip")
def get_my_payslip(
    period: str = Query(..., pattern=r"^\d{4}-\d{2}$"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_personal_portal_user),
):
    # 1. Resolve employee
    employee = db.query(Employee).filter(Employee.user_id == current_user.id).first()
    if not employee:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tài khoản đăng nhập của bạn chưa được liên kết với hồ sơ nhân sự nào.",
        )

    # 2. Get monthly salary input
    monthly_input = (
        db.query(MonthlySalaryInput)
        .filter(
            MonthlySalaryInput.employee_id == employee.id,
            MonthlySalaryInput.salary_period == period,
        )
        .first()
    )
    if not monthly_input:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Chưa có dữ liệu bảng lương cho kỳ {period}.",
        )

    # 3. Check if published
    if not monthly_input.is_published:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Phiếu lương kỳ {period} của bạn đang được xử lý và chưa được phát hành.",
        )

    # 4. Resolve overrides
    fullname = employee.full_name
    position = employee.position
    contract_salary = employee.contract_salary
    employee_type = employee.employee_type
    dependents_count = employee.dependents_count
    account_number = employee.account_number
    bank_name = employee.bank_name
    
    if monthly_input.fullname is not None:
        fullname = monthly_input.fullname
    if monthly_input.position is not None:
        position = monthly_input.position
    if monthly_input.contract_salary is not None:
        contract_salary = monthly_input.contract_salary
    if monthly_input.employee_type is not None:
        employee_type = monthly_input.employee_type
    if monthly_input.dependents_count is not None:
        dependents_count = monthly_input.dependents_count
    if monthly_input.account_number is not None:
        account_number = monthly_input.account_number
    if monthly_input.bank_name is not None:
        bank_name = monthly_input.bank_name

    from app.services.salary import get_sales_bonus_for_employee_period
    sales_bonus = int(get_sales_bonus_for_employee_period(db, employee.id, period))
    commission_summary = get_commission_payslip_summary(db, employee, period)

    emp_dict = {
        "contract_salary": contract_salary,
        "actual_working_days": monthly_input.actual_working_days,
        "meal_allowance_free": monthly_input.meal_allowance_free,
        "meal_allowance_tax": monthly_input.meal_allowance_tax,
        "phone_allowance_free": monthly_input.phone_allowance_free,
        "trans_allowance_tax": monthly_input.trans_allowance_tax,
        "perf_allowance_tax": monthly_input.perf_allowance_tax,
        "other_income": monthly_input.other_income,
        "bonus": monthly_input.bonus + sales_bonus,
        "dependents_count": dependents_count,
        "other_deductions": monthly_input.other_deductions,
        "pit_refund": monthly_input.pit_refund,
        "advance_payment": monthly_input.advance_payment,
        "type": employee_type,
        "standard_working_days": calculate_period_working_days(period),
    }

    # Dùng đúng phiên bản chính sách đã gắn với dữ liệu tháng lương.  Nếu kỳ
    # chưa có input, áp dụng chính sách hiệu lực tại tháng đang xem.
    from app.models.salary_policy import SalaryPolicy
    from app.services.salary_policy import policy_to_dict, resolve_salary_policy

    salary_policy = (
        db.get(SalaryPolicy, monthly_input.salary_policy_id)
        if monthly_input.salary_policy_id
        else resolve_salary_policy(db, period)
    )
    calc_results = cake_salary(emp_dict, policy_to_dict(salary_policy))

    return {
        "employee_name": fullname,
        "employee_code": employee.employee_code,
        "position": position,
        "account_number": account_number,
        "bank_name": bank_name,
        "salary_period": period,
        "dependents_count": dependents_count,
        "contract_salary": contract_salary,
        "employee_type": employee_type,
        "start_date": employee.start_date.strftime("%d/%m/%Y") if employee.start_date else "N/A",
        "inputs": {
            "actual_working_days": monthly_input.actual_working_days,
            "meal_allowance_free": monthly_input.meal_allowance_free,
            "meal_allowance_tax": monthly_input.meal_allowance_tax,
            "phone_allowance_free": monthly_input.phone_allowance_free,
            "trans_allowance_tax": monthly_input.trans_allowance_tax,
            "perf_allowance_tax": monthly_input.perf_allowance_tax,
            "other_income": monthly_input.other_income,
            "other_income_note": monthly_input.other_income_note,
            "other_income_document_name": monthly_input.other_income_document_name,
            "bonus": monthly_input.bonus,
            "sales_bonus": sales_bonus,
            "advance_payment": monthly_input.advance_payment,
            "pit_refund": monthly_input.pit_refund,
            "other_deductions": monthly_input.other_deductions,
            "is_mid_month_change": monthly_input.is_mid_month_change,
            "prorated_old_salary": monthly_input.prorated_old_salary,
            "prorated_new_salary": monthly_input.prorated_new_salary,
            "prorated_days_old": monthly_input.prorated_days_old,
            "prorated_days_new": monthly_input.prorated_days_new,
            "mid_month_effective_date": monthly_input.mid_month_effective_date,
        },
        "commission_summary": commission_summary,
        "calculations": calc_results,
    }


@router.get("/my-payslip-pdf")
def download_my_payslip_pdf(
    period: str = Query(..., pattern=r"^\d{4}-\d{2}$"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_personal_portal_user),
) -> StreamingResponse:
    """Download the published payslip as a selectable-text PDF."""
    payslip_data = get_my_payslip(period=period, db=db, current_user=current_user)
    document = _build_text_payslip_pdf(payslip_data)
    safe_employee_code = "".join(char if char.isalnum() or char in {"-", "_"} else "-" for char in str(payslip_data.get("employee_code") or "nhan-vien"))
    filename = f"Phieu-luong_{safe_employee_code}_{period}.pdf"
    return StreamingResponse(
        document,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/my-attendance")
def get_my_attendance(
    period_start: date = Query(...),
    period_end: date = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_personal_portal_user),
):
    # 1. Resolve employee
    employee = db.query(Employee).filter(Employee.user_id == current_user.id).first()
    if not employee:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tài khoản đăng nhập của bạn chưa được liên kết với hồ sơ nhân sự nào.",
        )

    if period_start > period_end:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ngày bắt đầu phải trước ngày kết thúc.",
        )

    # 2. Get timesheet entries (most authoritative — includes admin overrides)
    entries = (
        db.query(TimesheetEntry)
        .filter(
            TimesheetEntry.employee_id == employee.id,
            TimesheetEntry.work_date >= period_start,
            TimesheetEntry.work_date <= period_end,
        )
        .all()
    )
    entries_map = {e.work_date: e for e in entries}

    # 3. Get raw attendance logs (for raw scan history)
    logs = (
        db.query(AttendanceLog)
        .filter(
            AttendanceLog.employee_id == employee.id,
            AttendanceLog.work_date >= period_start,
            AttendanceLog.work_date <= period_end,
        )
        .all()
    )
    logs_map = {l.work_date: l for l in logs}

    # 4. Get attendance daily (fallback when no timesheet entry exists yet)
    dailies = (
        db.query(AttendanceDaily)
        .filter(
            AttendanceDaily.employee_id == employee.id,
            AttendanceDaily.work_date >= period_start,
            AttendanceDaily.work_date <= period_end,
        )
        .all()
    )
    dailies_map = {d.work_date: d for d in dailies}

    # 5. Reconstruct day-by-day calendar
    results = []
    curr_date = period_start
    while curr_date <= period_end:
        entry = entries_map.get(curr_date)
        log = logs_map.get(curr_date)
        daily = dailies_map.get(curr_date)

        # Parse raw scan list from log
        raw_scans: list[str] = []
        if log and log.raw_time_values:
            raw_scans = [t.strip() for t in log.raw_time_values.split(",") if t.strip()]

        # Priority: TimesheetEntry > AttendanceDaily > AttendanceLog
        if entry:
            check_in = entry.check_in_time
            check_out = entry.check_out_time
            symbol = entry.final_symbol
            late_mins = entry.late_minutes
            early_mins = entry.early_minutes
            is_overridden = entry.is_overridden
            override_reason = entry.override_reason
        elif daily:
            check_in = daily.check_in_time
            check_out = daily.check_out_time
            symbol = daily.attendance_symbol or ""
            late_mins = daily.late_minutes or 0
            early_mins = daily.early_minutes or 0
            is_overridden = False
            override_reason = None
        elif log:
            check_in = log.first_check_in
            check_out = log.last_check_out
            symbol = log.missing_reason if log.missing_flag else ""
            late_mins = log.late_minutes or 0
            early_mins = log.early_minutes or 0
            is_overridden = False
            override_reason = None
        else:
            check_in = None
            check_out = None
            symbol = ""
            late_mins = 0
            early_mins = 0
            is_overridden = False
            override_reason = None

        # Default weekend symbols
        if not symbol and curr_date.weekday() >= 5:
            symbol = "T7" if curr_date.weekday() == 5 else "CN"

        results.append({
            "work_date": curr_date.isoformat(),
            "weekday": curr_date.strftime("%a"),
            "check_in": check_in,
            "check_out": check_out,
            "raw_scans": raw_scans,
            "final_symbol": symbol,
            "late_minutes": late_mins,
            "early_minutes": early_mins,
            "is_overridden": is_overridden,
            "override_reason": override_reason,
            "missing_flag": log.missing_flag if log else False,
        })
        curr_date += timedelta(days=1)

    return results
