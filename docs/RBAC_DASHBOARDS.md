# Ma trận phân quyền Dashboard SEALINK

## Nguyên tắc

- Tài khoản liên kết hồ sơ Nguyễn Lý Tưởng (`SL016`) mang vai trò `ADMIN`, dùng Dashboard Kế toán trưởng hiện tại và không thay đổi công thức lương, commission hoặc bonus.
- Tài khoản dùng chung `admin_sealink` mang vai trò `IT_ADMIN` — quyền cao nhất. Vai trò này kế thừa toàn bộ quyền nghiệp vụ của Kế toán trưởng và có thêm Backup/Audit dành riêng cho IT.
- Việc ẩn menu chỉ là lớp giao diện. Backend luôn kiểm tra vai trò trước khi trả dữ liệu hoặc ghi thay đổi.
- API nhân sự dành cho Admin vận hành không trả về lương hợp đồng, phụ cấp hoặc dữ liệu bonus.
- Mỗi tài khoản mới phải liên kết với đúng một hồ sơ nhân viên để truy cập dữ liệu cá nhân và để ghi nhận người thao tác.

## Ma trận quyền

| Chức năng | `ADMIN` Kế toán trưởng | `HR_ADMIN` Admin vận hành | `IT_ADMIN` IT | `USER` Nhân viên |
|---|---:|---:|---:|---:|
| Dashboard Kế toán trưởng hiện tại | Toàn quyền | Không | Toàn quyền | Không |
| Lương, commission, bonus | Toàn quyền | Không | Toàn quyền | Chỉ dữ liệu cá nhân |
| Hồ sơ nhân sự không có trường tài chính | Có | Xem, thêm, sửa | Toàn quyền | Không |
| Phòng ban và sơ đồ tổ chức | Có | Xem, thêm, sửa, phân bổ nhân sự | Toàn quyền | Không |
| Import, rà soát, override và phê duyệt bảng công | Có | Có | Toàn quyền | Chỉ dữ liệu cá nhân |
| Xuất báo cáo HR/chấm công | Có | Có | Toàn quyền | Không |
| Phiếu lương, chấm công, bảng công và bonus đang giữ cá nhân | Backend giữ tương thích | Không | Dữ liệu cá nhân | Dữ liệu cá nhân |
| Backup cơ sở dữ liệu | Không hiển thị ở Dashboard hiện tại | Không | Xem và tạo backup | Không |
| Audit hệ thống và lịch sử override | Không hiển thị ở Dashboard hiện tại | Không | Chỉ đọc | Không |
| Cấp tài khoản nhân viên và đồng bộ quyền | Có | Theo phạm vi HR | Toàn quyền | Không |

## Dashboard theo vai trò

- `ADMIN`: tài khoản Nguyễn Lý Tưởng, giữ nguyên các route `/admin/*` và toàn bộ giao diện Kế toán trưởng hiện tại; không có menu Backup/Audit IT.
- `HR_ADMIN`: dùng `/hr/dashboard`, `/hr/employees`, `/hr/departments`, `/hr/timesheets`, `/hr/export`.
- `IT_ADMIN`: tài khoản dùng chung `admin_sealink`, dùng toàn bộ route và giao diện `/admin/*` như Kế toán trưởng, đồng thời có thêm `/it/backups` và `/it/audit`.
- `USER`: dùng `/user/dashboard`, phiếu lương, lịch chấm công, bảng công cá nhân và bonus đang giữ.

## Cấp và đồng bộ tài khoản

- Tài khoản Kế toán trưởng được liên kết cố định với hồ sơ Nguyễn Lý Tưởng bằng script `backend/scripts/transfer_chief_accountant_access.py`.
- `admin_sealink` luôn được đồng bộ về `IT_ADMIN`.
- Chức vụ `Admin` trong nhánh IT & ADMIN nhận `HR_ADMIN`.
- Tài khoản cá nhân của nhân viên IT và các nhân viên khác nhận `USER`; nhân viên IT dùng `admin_sealink` khi thực hiện Backup/Audit.
- Người quản trị nhập tên đăng nhập và mật khẩu tối thiểu 12 ký tự trong hồ sơ nhân viên; không chọn vai trò thủ công.

## Backup và audit

- Windows Scheduled Task: `SEALINK-DB-Backup-Daily`.
- Lịch chạy: hằng ngày lúc `23:30`, tự chạy bù khi máy khởi động lại.
- Thư mục: `backups/`.
- Mỗi bản backup có file `.sql.gz` và checksum `.sha256`; giữ tối đa 30 bản gần nhất.
- IT có thể xem/tạo backup qua `/api/it/backups`, `/api/it/backups/run`.
- Audit chỉ đọc qua `/api/it/audit` và `/api/it/attendance-overrides`.
- Lịch sử không lưu mật khẩu hoặc nội dung request nhạy cảm.

## Kiểm thử bắt buộc khi thay đổi quyền

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest -q

cd ..\frontend
npm run lint
npm run build
```

Mọi thay đổi sau này phải kiểm thử cả quyền được phép lẫn phản hồi `403 Forbidden` của vai trò không được phép.
