# Huong dan van hanh cho HR/Manager

## 1) Muc dich va pham vi
Tai lieu nay huong dan quy trinh van hanh he thong cham cong SEALINK cho HR/Manager:
- Nhap du lieu cham cong tu file checkin va abnormal
- Doi soat bang cong theo ky 23 -> 22
- Override ngay cong (bat buoc ly do, co audit)
- Phe duyet bang cong
- Xuat bao cao Timesheet va KPI

## 2) Vai tro va trach nhiem
### HR
- Import file, kiem tra preview, commit du lieu.
- Doi soat du lieu bat thuong va thuc hien override neu can.
- Chuan bi bang cong cho Manager phe duyet.

### Manager
- Kiem tra tong quan bang cong cua don vi.
- Phe duyet hoac tu choi bang cong.
- Kiem tra lich su override khi can truy vet.

## 3) Quy tac nghiep vu bat buoc
- Chu ky cong co dinh: tu ngay 23 thang truoc den ngay 22 thang sau.
- Trong 1 ngay co nhieu moc gio: lay gio nho nhat la check-in, lon nhat la check-out.
- Neu ghi chu co "Bo lo": danh dau missing punch.
- Thu tu uu tien du lieu: override > abnormal > checkin profile.
- Moi override phai co ly do ro rang va luu audit.

## 4) Quy trinh van hanh chuan (SOP)
### Buoc 1: Chon ky cong
1. Chon period_start va period_end theo dung ky 23 -> 22.
2. Xac nhan toan bo nguoi van hanh dang su dung cung mot ky.

### Buoc 2: Import checkin profile
1. Vao tab Import, chon loai file Checkin Profile.
2. Upload file CSV/XLS/XLSX.
3. Kiem tra preview:
   - So dong doc duoc
   - Cot check-in/check-out
   - Cac dong bao thieu moc gio
4. Neu du lieu dung, thuc hien commit.

### Buoc 3: Import abnormal report
1. Chon loai file Abnormal Report.
2. Upload file va xem preview.
3. Xac nhan cac dong co "Bo lo", di muon, ve som da duoc nhan dien.

### Buoc 4: Doi soat bang cong
1. Vao tab Timesheet + Approval.
2. Su dung bo loc theo phong ban, nhan vien, trang thai bat thuong.
3. Kiem tra:
   - Ky hieu ngay cong (X/P/V/CT)
   - Tong late minutes
   - Tong early minutes
   - So ngay bat thuong

### Buoc 5: Override (neu can)
1. Bam Override tai dong nhan vien.
2. Nhap day du:
   - employee_id
   - work_date
   - symbol moi
   - ly do (bat buoc)
   - changed_by_user_id
3. Luu override va tai lai lich su audit de xac nhan.

### Buoc 6: Phe duyet
1. Manager review bang tong hop.
2. Chon Approve hoac Reject.
3. Neu reject, HR can doi soat va xu ly lai du lieu.

### Buoc 7: Export
1. Vao tab Export.
2. Xuat file Timesheet Excel.
3. Tai Dashboard, xuat KPI Excel khi can bao cao tong hop.

## 5) Checklist chot ky cong
- Da import checkin profile cho toan ky.
- Da import abnormal report cho toan ky.
- Da map day du machine_employee_id cho nhan vien moi.
- Khong con dong bat thuong chua xu ly.
- Tat ca override deu co ly do hop le.
- Bang cong da duoc Manager phe duyet.
- Da export va luu file Timesheet/KPI.

## 6) Tinh huong loi thuong gap va cach xu ly
### Loi 1: File upload thieu cot
- Trieu chung: thong bao "Missing required columns".
- Xu ly: doi chieu template cot, sua file nguon, upload lai.

### Loi 2: Khong commit duoc do employee khong ton tai
- Trieu chung: skipped voi reason "employee_not_found".
- Xu ly: cap nhat map machine_employee_id trong Employee Directory, sau do import/commit lai.

### Loi 3: Override that bai
- Trieu chung: loi khong tim thay changed_by_user_id hoac timesheet entry.
- Xu ly:
  - Kiem tra user sua ton tai trong he thong.
  - Kiem tra da tao du lieu timesheet cho ngay can sua.

### Loi 4: Khong load duoc KPI/Timesheet
- Trieu chung: frontend bao loi ket noi API.
- Xu ly:
  - Kiem tra backend dang chay o cong 8000.
  - Kiem tra database Docker dang running.

## 7) Luu y kiem soat va tuan thu
- Khong chinh sua du lieu khong co ly do nghiep vu.
- Moi thay doi override phai truy vet duoc ai sua, sua khi nao, sua gi.
- Chi phe duyet khi da hoan tat doi soat bat thuong.
