from io import BytesIO

from openpyxl import Workbook

from app.services.commission_receivable_parser import parse_receivable_workbook


def _workbook_bytes(rows: list[list[object]]) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "AGEING"
    sheet.append([None] * 18)
    sheet.append([None] * 18)
    sheet.append([None] * 18)
    sheet.append([None] * 18)
    sheet.append([
        "Sr #", "Date", "Due Date", "Voucher No", "Code", "Invoice No", "Job No",
        "Customer / Vendor", "Cur", "Receivable / Payable", "Received / Paid", "Balance",
        "D.Day", "Tax Inv No", "Work Order No", "Origin", "Destination", "Project Ref No",
    ])
    for row in rows:
        sheet.append(row)
    output = BytesIO()
    workbook.save(output)
    workbook.close()
    return output.getvalue()


def test_parse_receivable_workbook_keeps_zero_balance_and_ignores_only_negative():
    result = parse_receivable_workbook(_workbook_bytes([
        [1, None, None, None, None, None, " SEJ-100 / 26 ", None, "VND", 60_000_000, 30_000_000, 30_000_000],
        [2, None, None, None, None, None, "SEJ-100/26", None, "VND", 40_000_000, 30_000_000, 10_000_000],
        [3, None, None, None, None, None, "SEJ-NEG/26", None, "VND", 20_000_000, 21_000_000, -1_000_000],
        [4, None, None, None, None, None, "SEJ-ZERO/26", None, "VND", 20_000_000, 20_000_000, 0],
        [5, None, None, None, None, None, "SEJ-INVALID/26", None, "VND", 0, 0, 5_000_000],
    ]), "payment-report.xlsx")

    assert result.sheet_name == "AGEING"
    assert result.header_row == 5
    assert result.positive_rows == 4
    assert result.ignored_non_positive_rows == 1
    assert result.invalid_positive_rows == 1
    assert len(result.jobs) == 2
    by_job_no = {job.job_no: job for job in result.jobs}
    job = by_job_no["SEJ-100/26"]
    assert job.job_no == "SEJ-100/26"
    assert job.source_rows == 2
    assert job.receivable_amount == 100_000_000
    assert job.received_amount == 60_000_000
    assert job.balance_amount == 40_000_000
    assert job.paid_percent == 60
    assert job.hold_bonus_percent == 30
    fully_paid = by_job_no["SEJ-ZERO/26"]
    assert fully_paid.receivable_amount == 20_000_000
    assert fully_paid.received_amount == 20_000_000
    assert fully_paid.balance_amount == 0
    assert fully_paid.paid_percent == 100
    assert fully_paid.hold_bonus_percent == 0


def test_parse_receivable_workbook_keeps_fixed_hold_when_unpaid_ratio_is_below_thirty_percent():
    result = parse_receivable_workbook(_workbook_bytes([
        [1, None, None, None, None, None, "SEJ-75/26", None, "VND", 100_000_000, 75_000_000, 25_000_000],
    ]), "payment-report.xlsx")
    assert result.jobs[0].paid_percent == 75
    assert result.jobs[0].hold_bonus_percent == 30
