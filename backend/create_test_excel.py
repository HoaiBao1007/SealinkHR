import pandas as pd
from io import BytesIO

# Cycle days for 2026-04-23 to 2026-05-22
# April has 30 days, so the days are: 23, 24, 25, 26, 27, 28, 29, 30, 1, 2, ..., 22
cycle_days = list(range(23, 31)) + list(range(1, 23))

def build_matrix_row(prefix, values_by_day):
    return prefix + [values_by_day.get(day, "") for day in cycle_days]

# 1. Bảng thông tin lịch trình (schedule)
# Row 1: Headers
# Row 2: Tommy Dat (26)
# Row 3: Hoai Bao (38)
schedule_data = [
    ["ID", "Ten", "Phong ban", *cycle_days],
    build_matrix_row(["26", "NGUYỄN THANH ĐẠT", "Operations"], {d: 1 for d in cycle_days if d not in [25, 26, 2, 3, 9, 10, 16, 17]}), # exclude weekends
    build_matrix_row(["38", "ĐẶNG HOÀI BẢO", "Management"], {d: 1 for d in cycle_days if d not in [25, 26, 2, 3, 9, 10, 16, 17]}),
]
schedule_df = pd.DataFrame(schedule_data)

# 2. Hồ sơ check-in (profile)
# We will simulate punch times. Tommy Dat missed punch on some days.
# On 2026-05-15 (day 15), he has no punch (he requested leave).
# On 2026-05-18 (day 18), he has no punch (unapproved leave request).
# On 2026-05-19 (day 19), Hoai Bao has only afternoon check-out or morning check-in (half-day leave).
profile_data = [
    ["ID", "Ten", "Phong ban", *cycle_days],
    # Tommy Dat's profile rows (Row 1: name, Row 2: scans)
    build_matrix_row(["26", "NGUYỄN THANH ĐẠT", "Operations"], {}),
    build_matrix_row(["", "", ""], {
        d: "08:15\n17:35" for d in cycle_days 
        if d not in [25, 26, 2, 3, 9, 10, 16, 17, 15, 18] # weekday working days except 15 (leave) and 18 (unapproved leave)
    }),
    # Hoai Bao's profile rows
    build_matrix_row(["38", "ĐẶNG HOÀI BẢO", "Management"], {}),
    build_matrix_row(["", "", ""], {
        d: "08:20\n17:40" if d != 19 else "13:00\n17:40" # Hoai Bao has half-day leave on May 19
        for d in cycle_days
        if d not in [25, 26, 2, 3, 9, 10, 16, 17]
    }),
]
profile_df = pd.DataFrame(profile_data)

# 3. Báo cáo check-in (checkin_report)
checkin_rows = []
for d in cycle_days:
    # Tommy Dat
    if d not in [25, 26, 2, 3, 9, 10, 16, 17, 15, 18]:
        day_val = f"2026-04-{d}" if d >= 23 else f"2026-05-{str(d).zfill(2)}"
        checkin_rows.append(["26", "NGUYỄN THANH ĐẠT", "Operations", day_val, "08:15", "17:35"])
    # Hoai Bao
    if d not in [25, 26, 2, 3, 9, 10, 16, 17]:
        day_val = f"2026-04-{d}" if d >= 23 else f"2026-05-{str(d).zfill(2)}"
        if d == 19:
            checkin_rows.append(["38", "ĐẶNG HOÀI BẢO", "Management", day_val, "13:00", "17:40"])
        else:
            checkin_rows.append(["38", "ĐẶNG HOÀI BẢO", "Management", day_val, "08:20", "17:40"])

checkin_report_df = pd.DataFrame(
    [["Mã NV", "Họ tên", "Phòng ban", "Ngày", "Giờ vào", "Giờ ra"]] + checkin_rows
)

# 4. Báo cáo bất thường (abnormal)
abnormal_rows = []
# Tommy Dat has absent on 15 and 18
abnormal_rows.append(["26", "2026-05-15", "Bỏ lỡ", "Bỏ lỡ", 0, 0])
abnormal_rows.append(["26", "2026-05-18", "Bỏ lỡ", "Bỏ lỡ", 0, 0])
# Hoai Bao is late or has missing punch on 19
abnormal_rows.append(["38", "2026-05-19", "Bỏ lỡ", "17:40", 0, 0])

abnormal_df = pd.DataFrame(
    [["Mã NV", "Ngày", "Buổi 1 Vào làm", "Buổi 1 Ra nghỉ", "Thời gian trễ", "Thời gian sớm"]] + abnormal_rows
)

# 5. Bảng tóm tắt check-in (summary)
summary_df = pd.DataFrame([
    ["Mã NV", "Họ tên", "Phòng ban", "Tổng số phút đi muộn trong tháng", "Tổng số ngày vắng mặt"],
    ["26", "NGUYỄN THANH ĐẠT", "Operations", 0, 2],
    ["38", "ĐẶNG HOÀI BẢO", "Management", 0, 1],
])

# Save to excel file
with pd.ExcelWriter("test_attendance.xlsx", engine="openpyxl") as writer:
    schedule_df.to_excel(writer, index=False, header=False, sheet_name="Bảng thông tin lịch trình")
    checkin_report_df.to_excel(writer, index=False, header=False, sheet_name="Báo cáo check-in")
    abnormal_df.to_excel(writer, index=False, header=False, sheet_name="Báo cáo bất thường")
    profile_df.to_excel(writer, index=False, header=False, sheet_name="Hồ sơ check-in")
    summary_df.to_excel(writer, index=False, header=False, sheet_name="Bảng tóm tắt check-in")

print("Generated test_attendance.xlsx successfully.")

# Create notion csv
# Columns: Name, Tên nhân viên, Leave Balance, Lý do Nghỉ, Thời Gian, Số Ngày Nghỉ, Trạng Thái
# Note the date format in Notion CSV is mm/dd/yyyy
# Tommy Dat: 05/15/2026 (Approved), 05/18/2026 (Need Review)
# Hoai Bao: 05/19/2026 8:00 AM -> 12:00 PM (Approved)
notion_content = """Name,Tên nhân viên,Leave Balance,Lý do Nghỉ,Thời Gian,Số Ngày Nghỉ,Trạng Thái
Leave Request,TOMMY DAT,TOMMY DAT,Cá nhân,05/15/2026 8:00 AM (GMT+7) → 5:30 PM,1.0,Approved
Leave Request,TOMMY DAT,TOMMY DAT,Đau ốm,05/18/2026 8:00 AM (GMT+7) → 5:30 PM,1.0,Need Review
Leave Request,HOAI BAO,HOAI BAO,Cá nhân,05/19/2026 8:00 AM (GMT+7) → 12:00 PM,0.5,Đã duyệt
"""

with open("test_notion.csv", "w", encoding="utf-8") as f:
    f.write(notion_content)

print("Generated test_notion.csv successfully.")
