# Hướng dẫn Commission, Ví thưởng và Phễu bonus

Tài liệu này mô tả cách vận hành phần **Commission & Job PnL** từ lúc chuẩn bị dữ liệu, import báo cáo, đối soát số tiền, giữ/mở khóa bonus theo JOB, chuyển kỳ, lập lịch và chi trả. Mục tiêu là mọi thay đổi liên quan đến tiền thưởng đều có thể kiểm tra lại trong sổ cái.

> Phạm vi: Commission của Sales. Tài liệu không thay đổi công thức bonus do phòng ban cấu hình; các thao tác trong Ví thưởng và Phễu bonus chỉ tạo bút toán vận hành.

## 1. Nguyên tắc quan trọng

1. **Công thức gốc và sổ cái là hai lớp khác nhau.**
   - Công thức tính ra tổng thưởng quý và thưởng tháng từ Profit/Loss, target, hệ số và cấu hình bonus.
   - Ví thưởng ghi nhận cách vận hành khoản thưởng đó: đang giữ, khả dụng, chuyển kỳ, đã lập lịch, đã trả hoặc cần thu hồi.
2. **Không sửa lịch sử sổ cái.** Khi cần sửa một khoản đã ghi nhận, hệ thống thêm bút toán chênh lệch mới. Vì vậy người kiểm tra vẫn thấy được nguyên nhân và thời điểm của từng thay đổi.
3. **Chỉ chi trả từ số khả dụng.** Tiền đang giữ tự động, giữ thủ công, đã chuyển kỳ sau hoặc đã lập lịch không được chi trả thêm lần nữa.
4. **Payment Received quyết định giữ tự động.** `NO` giữ lại phần bonus của JOB; `YES` mở khóa phần giữ tự động đó. Giữ thủ công là độc lập và chỉ quản trị viên mới mở khóa được.
5. **Đồng bộ ví sau khi dữ liệu nguồn thay đổi.** Sau import, cập nhật Payment Received, hoặc sửa override của kỳ, cần dùng **Đồng bộ ví thưởng** để sổ cái nhận phần chênh lệch. Đồng bộ chỉ thêm delta; không xóa lịch sử cũ.

## 2. Các khái niệm và cột số liệu

| Khái niệm | Ý nghĩa | Có làm đổi công thức không? |
| --- | --- | --- |
| Tổng Profit/Loss | Tổng P&L của các JOB trong kỳ/quý | Là dữ liệu đầu vào |
| Tổng thưởng quý | Kết quả theo công thức bonus của kỳ/quý | Có thể thay đổi khi cấu hình/override công thức thay đổi |
| Thưởng/tháng | Tổng thưởng quý chia 3, hoặc giá trị override tháng | Là nguồn để phân bổ vào Ví |
| Ghi nhận / Tổng thưởng trong Ví | Tổng bonus đã được ghi vào sổ cái của tháng nguồn | Không tự thay đổi công thức |
| Giữ tự động | Bonus đang bị khóa vì `Payment Received = NO` | Không |
| Giữ thủ công | Khoản quản trị viên khóa riêng theo JOB | Không |
| Đang giữ | Giữ tự động + giữ thủ công | Không |
| Đã chuyển kỳ sau | Khoản đã tách khỏi khả dụng hiện tại và ghi nhận kỳ đích | Không |
| Đã lập lịch | Khoản đã được dành cho một đợt chi trả cụ thể | Không |
| Khả dụng | Khoản còn có thể lập lịch hoặc chi trả | Không |
| Đã nhận / Đã trả | Khoản đã hoàn tất chi trả | Không |
| Cần thu hồi | Số dư âm sau điều chỉnh/hủy; cần bù trừ ở commission tiếp theo | Không |

### Khoản Giảm bonus đi về đâu?

Khoản **Giảm bonus** không được chuyển vào ví của nhân viên khác và cũng không phải là một khoản chi trả. Đây là **khấu trừ khỏi quyền hưởng bonus** của Sales Rep/JOB nguồn, được ghi bằng bút toán `MANUAL_DECREASE` âm trong sổ cái.

- **Tổng thưởng quý theo công thức** không đổi, vì công thức nguồn không bị sửa.
- **Ghi nhận ròng** và **Khả dụng** giảm đúng số tiền khấu trừ.
- Cột **Đã giảm/khấu trừ** ở Ví, Phễu và chi tiết JOB tích lũy mọi lần giảm để người dùng thấy ngay tổng đã rút khỏi entitlement.
- Lịch sử sổ cái vẫn là bằng chứng chi tiết gồm JOB, thời điểm và lý do.

Ví dụ: Bonus nguồn 10.000.000, giảm 500.000 thì Ghi nhận ròng còn 9.500.000. Số 500.000 được thể hiện ở **Đã giảm/khấu trừ**, không nằm trong bất kỳ phễu tiền nào khác.

### Công thức số dư Ví

Tại mỗi thời điểm, hệ thống đối soát theo sổ cái:

```text
Khả dụng = Ghi nhận
         - Giữ tự động
         - Giữ thủ công
         - Đã chuyển kỳ sau
         - Đã lập lịch
         - Đã trả
```

`Cần thu hồi = max(0, -Khả dụng)`.

> Tiền tệ được lưu và đối soát đến 2 chữ số thập phân. Giao diện VND hiện làm tròn để dễ đọc. Khi cần kiểm toán số lẻ, xem **Lịch sử sổ cái** hoặc xuất dữ liệu thay vì tự suy ra từ số đã làm tròn trên màn hình.

## 3. Điều kiện trước khi import

Thực hiện theo thứ tự dưới đây trước mỗi kỳ mới.

1. Kiểm tra nhân viên Sales đã tồn tại trong **Nhân sự** và tên nhân viên khớp tên Sales Rep trong file Climax.
2. Kiểm tra nhân viên có phòng ban, lương hợp đồng và cấu hình bonus của phòng ban tại kỳ cần áp dụng.
3. Chuẩn bị file Excel Climax `Job PnL With Realize/Unrealize Detail` (`.xlsx` hoặc `.xls`).
4. Kiểm tra file có các thông tin cần thiết: JOB #, Sales Rep, các cột doanh thu/chi phí, Profit/Loss và Payment Received.
5. Không import trùng cùng dữ liệu chỉ để thử. Nếu cần làm lại trong môi trường test, xóa đúng commission của nhân viên/kỳ cần thử rồi import lại.

## 4. Quy trình Commission từ đầu đến cuối

### Bước 1 — Mở tab Commission

Vào **Bảng lương → Commission**. Thứ tự giao diện là:

1. Upload file Excel.
2. Lịch sử Import đã lưu.
3. Ví thưởng commission.
4. Phễu bonus linh động và chi tiết JOB.

### Bước 2 — Upload và xem trước file

1. Kéo thả file vào vùng upload hoặc bấm chọn file.
2. Kiểm tra kỳ/quý được nhận diện, số JOB và tên Sales Rep.
3. Xem trước các JOB, đặc biệt các cột `Profit/Loss` và `Payment Received`.
4. Nếu sai sheet, header, kỳ áp dụng hoặc tên Sales Rep, quay lại sửa file trước khi xác nhận.
5. Bấm xác nhận/lưu import khi dữ liệu đúng.

**Kết quả:** hệ thống tạo kỳ commission, lưu JOB và tạo dòng trong **Lịch sử Import đã lưu**.

### Bước 3 — Kiểm tra lịch sử import và kết quả công thức

Mỗi dòng lịch sử hiển thị:

- **Kỳ:** khoảng thời gian nguồn.
- **Tên Sales Rep / JOBS:** người nhận bonus và số JOB.
- **Tổng Profit/Loss:** P&L tổng của kỳ.
- **Target, Hệ số:** đầu vào của cấu hình bonus.
- **Tổng thưởng:** tổng theo quý/kỳ.
- **Thưởng/tháng:** khoản được phân bổ vào Ví thưởng.

Nếu cần sửa nguồn tính commission, dùng **Sửa** trên kỳ/import tương ứng và luôn nhập **Remark** giải thích. Sau khi lưu, phải thực hiện Bước 4.

### Bước 4 — Đồng bộ Ví thưởng

1. Ở khối **Ví thưởng commission**, bấm **Đồng bộ ví thưởng**.
2. Chờ thông báo hoàn tất.
3. Đối chiếu `Tổng thưởng` trong Ví với `Thưởng/tháng` trong lịch sử import.
4. Nếu có chênh lệch, xem **Lịch sử sổ cái** trước; không sửa tay số tổng ở giao diện.

Đồng bộ phân bổ thưởng tháng vào các JOB có Profit/Loss dương theo tỷ trọng P&L dương:

```text
Bonus JOB = Thưởng tháng × (Profit/Loss JOB dương / Tổng Profit/Loss dương của Sales Rep)
```

JOB cuối cùng nhận phần chênh lệch làm tròn để tổng phân bổ khớp chính xác thưởng tháng ở mức lưu trữ.

### Bước 5 — Kiểm tra Ví thưởng

Ví có một hàng cho mỗi Sales Rep. Kiểm tra lần lượt:

1. **Tổng thưởng:** khoản đã ghi nhận vào sổ cái.
2. **Đang giữ:** tổng bonus không thể trả ngay.
3. **Đã chuyển kỳ sau:** khoản đã rút khỏi khả dụng kỳ hiện tại và có kỳ đích trong lịch sử sổ cái.
4. **Khả dụng:** số tối đa được phép lập lịch/chi trả ngay.
5. **Đã nhận:** tổng đã chi trả.
6. **Cần thu hồi:** số âm phải xử lý trước các khoản trả tiếp theo.
7. **Quy tắc chi trả:** Duyệt thủ công, Kỳ lương kế tiếp hoặc Theo ngưỡng.

### Bước 6 — Mở Phễu bonus linh động

1. Bấm vào hàng Sales Rep trong bảng Phễu để chọn người cần xử lý.
2. Kiểm tra thanh thông tin: **Kỳ/quý đang hiển thị cho [Sales Rep]**. Đây là kỳ nguồn của các JOB đang xem.
3. Kiểm tra bảng tóm tắt: Tổng thưởng quý, Ghi nhận, Giữ, Đã lập lịch, Đã chuyển kỳ sau, Khả dụng, Đã trả, Thu hồi.
4. Kéo xuống bảng chi tiết JOB để kiểm tra từng JOB trước khi thao tác.

## 5. Xử lý Payment Received theo JOB

Trong bảng JOB chi tiết, cột **Payment Received** có thể sửa `YES/NO`. Giao diện sẽ hiển thị số dư **Dự kiến** trước khi bấm lưu.

### NO → YES

1. Chọn `YES` tại JOB.
2. Remark mặc định được điền: khách hàng đã thanh toán, mở giữ tự động.
3. Kiểm tra cột Giữ tự động giảm và Khả dụng tăng ở phần dự kiến.
4. Bấm **Lưu** và xác nhận.

Kết quả: phần giữ tự động còn lại của JOB được mở khóa. Phần giữ thủ công, nếu có, vẫn giữ nguyên.

### YES → NO

1. Chọn `NO` tại JOB.
2. Remark mặc định được điền: khách hàng chưa thanh toán, chuyển bonus sang giữ tự động.
3. Kiểm tra Khả dụng dự kiến về 0 cho phần JOB bị giữ.
4. Bấm **Lưu** và xác nhận.

Kết quả: số khả dụng của JOB được chuyển sang giữ tự động. Hệ thống không sửa công thức bonus gốc.

### Quy tắc Remark

- Có thể thay Remark mặc định bằng lý do nghiệp vụ cụ thể.
- Remark nên nêu nguồn xác nhận, ví dụ: `Khách hàng ABC xác nhận thanh toán ngày 18/07/2026`.
- Remark được lưu cùng JOB và bút toán liên quan để phục vụ kiểm toán.

## 6. Giữ/Mở khóa bonus thủ công theo JOB

Phần này dùng khi cần khóa một JOB dù Payment Received đã là `YES`, hoặc chỉ muốn khóa một phần số tiền.

1. Tìm JOB qua ô tìm kiếm. Có thể tick **Chỉ JOB đang giữ thủ công** để rà soát nhanh.
2. Nhập số tiền đích tại cột **Giữ thủ công**.
   - Nhập `0`: mở toàn bộ giữ thủ công của JOB.
   - Nhập một số dương: giữ đúng số đó.
3. Nhập **Remark** nêu lý do giữ/mở khóa.
4. Bấm **Lưu**, xem phần dự kiến, rồi xác nhận.

Hệ thống chỉ ghi phần chênh lệch:

- Tăng số giữ: `MANUAL_HOLD`.
- Giảm số giữ: `MANUAL_RELEASE`.

Không thể giữ vượt quá khả dụng của chính JOB đó.

## 7. Các chức năng của Phễu bonus

### 7.1 Giảm / Nhận bonus

Dùng khi có quyết định vận hành ngoài công thức gốc.

| Thao tác | Kết quả sổ cái | Ảnh hưởng |
| --- | --- | --- |
| Giảm | `MANUAL_DECREASE` | Giảm Ghi nhận và Khả dụng; có thể tạo Cần thu hồi |
| Nhận / cộng thủ công | `MANUAL_CREDIT` | Tăng Ghi nhận và Khả dụng |

Quy trình:

1. Chọn loại Giảm hoặc Nhận/cộng thủ công.
2. Nhập số tiền và lý do bắt buộc.
3. Bấm **Ghi sổ cái** và xác nhận.
4. Kiểm tra dòng mới trong Lịch sử sổ cái.

### 7.2 Chuyển sang kỳ/quý sau

Dùng khi muốn đưa một phần bonus khả dụng ra khỏi kỳ hiện tại và ghi nhận kỳ đích, ví dụ `2026-08`.

1. Nhập số tiền chuyển.
2. Chọn tháng/kỳ đích.
3. Nhập lý do.
4. Modal sẽ hiển thị **chính xác số tiền sẽ chuyển**. Đối chiếu kỹ trước khi xác nhận.
5. Bấm **Chuyển bonus**.

Hệ thống tạo đồng thời:

- `TRANSFER_OUT`: số âm ở kỳ nguồn.
- `TRANSFER_IN`: số dương ở kỳ đích.

Do đó, khoản chuyển:

- giảm **Khả dụng** của nguồn ngay lập tức;
- tăng **Đã chuyển kỳ sau**;
- vẫn giữ nguyên **Ghi nhận/Tổng thưởng**, vì tiền đã phát sinh không bị xóa;
- không đồng nghĩa đã chi trả.

> Lưu ý hiện tại: Chuyển kỳ là thao tác dự trữ theo kỳ đích, không tự tạo một đợt trả. Nếu mục tiêu là trả lương vào một tháng cụ thể, dùng **Lập lịch chi trả** ngay từ đầu.

### 7.3 Lập lịch chi trả

Dùng để dành một phần hoặc toàn bộ khả dụng cho tháng trả xác định.

1. Nhập số tiền, hoặc để trống để chọn toàn bộ khả dụng.
2. Chọn tháng trả.
3. Nhập ghi chú.
4. Bấm **Lập lịch**.

Sau khi lập lịch:

- Khả dụng giảm.
- Đã lập lịch tăng.
- Bảng **Lịch chi trả** xuất hiện dòng trạng thái `SCHEDULED`.

Tại bảng lịch:

- **Chi trả:** chuyển lịch thành `PAID`, giảm Đã lập lịch và tăng Đã trả.
- **Hủy lịch:** giải phóng phần đã dành lại về Khả dụng.

### 7.4 Chi trả từ Ví thưởng

Nút **Chi trả** tại Ví thưởng tạo đợt chi trả từ số khả dụng của Sales Rep. Trước khi thực hiện:

1. Kiểm tra Khả dụng.
2. Kiểm tra Cần thu hồi phải bằng 0.
3. Kiểm tra không có JOB nào cần giữ thêm.
4. Kiểm tra Quy tắc chi trả; chế độ Theo ngưỡng không cho trả dưới số tối thiểu cấu hình.
5. Xác nhận số tiền tại modal.

## 8. Lịch sử sổ cái: cách đọc và đối soát

Lịch sử sổ cái hiển thị trong vùng cuộn để không chiếm diện tích màn hình. Các loại bút toán phổ biến:

| Mã giao dịch | Diễn giải |
| --- | --- |
| `ACCRUAL_AVAILABLE` | Ghi nhận bonus JOB có Payment Received = YES |
| `ACCRUAL_HELD` | Ghi nhận bonus JOB có Payment Received = NO |
| `ADJUSTMENT_AVAILABLE` / `ADJUSTMENT_HELD` | Đồng bộ phần chênh lệch sau khi nguồn thay đổi |
| `RELEASED` | Mở giữ tự động khi Payment Received chuyển sang YES |
| `PAYMENT_STATUS_HOLD` | Giữ lại khi Payment Received chuyển sang NO |
| `MANUAL_HOLD` / `MANUAL_RELEASE` | Giữ/mở khóa thủ công theo JOB |
| `MANUAL_CREDIT` / `MANUAL_DECREASE` | Cộng/giảm vận hành, không đổi công thức gốc |
| `TRANSFER_OUT` / `TRANSFER_IN` | Chuyển từ kỳ nguồn sang kỳ đích |
| `SCHEDULED` / `SCHEDULE_RELEASE` | Dành tiền cho lịch chi trả / hoàn lịch |
| `PAID` | Đã chi trả |

Khi đối soát chênh lệch, theo thứ tự:

1. Xác định đúng Sales Rep và kỳ/quý đang xem.
2. So sánh **Thưởng/tháng** trong lịch sử import với **Ghi nhận** trong Ví.
3. Nếu dữ liệu nguồn mới được sửa, bấm Đồng bộ ví rồi xem các dòng `ADJUSTMENT_*`.
4. Cộng các dòng `TRANSFER_IN`, đối chiếu cột Đã chuyển kỳ sau và Kỳ đích.
5. Cộng Giữ tự động, Giữ thủ công, Lịch chi trả và PAID để kiểm tra Khả dụng theo công thức ở Mục 2.
6. Không xóa dòng sổ cái để “làm đẹp” số liệu; dùng bút toán điều chỉnh có lý do.

## 9. Ví dụ kiểm thử đầy đủ

### Dữ liệu đầu vào

Giả sử Sales Rep **ANH MINH** có:

- Tổng thưởng quý: `30.000.000` VND.
- Thưởng tháng nguồn: `10.000.000` VND.
- Ba JOB có Profit/Loss dương:

| JOB | Profit/Loss | Tỷ trọng | Payment Received | Bonus phân bổ |
| --- | ---: | ---: | --- | ---: |
| A-001 | 60.000.000 | 60% | YES | 6.000.000 |
| B-002 | 30.000.000 | 30% | NO | 3.000.000 |
| C-003 | 10.000.000 | 10% | YES | 1.000.000 |
| **Tổng** | **100.000.000** | **100%** |  | **10.000.000** |

### Trạng thái sau đồng bộ đầu tiên

| Ghi nhận | Giữ tự động | Giữ thủ công | Đã chuyển | Đã lập lịch | Khả dụng | Đã trả |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 10.000.000 | 3.000.000 | 0 | 0 | 0 | 7.000.000 | 0 |

Giải thích: JOB B-002 ở trạng thái `NO`, nên 3.000.000 bị giữ tự động.

### Tình huống 1 — Khách hàng thanh toán JOB B-002

Đổi B-002 từ `NO` sang `YES`, xem trước và bấm Lưu.

| Ghi nhận | Giữ tự động | Giữ thủ công | Khả dụng |
| ---: | ---: | ---: | ---: |
| 10.000.000 | 0 | 0 | 10.000.000 |

Sổ cái thêm `RELEASED +3.000.000`.

### Tình huống 2 — Giữ thủ công 2.000.000 của JOB A-001

Nhập `2.000.000` vào cột Giữ thủ công của A-001, thêm Remark `Chờ duyệt biên lợi nhuận` rồi Lưu.

| Ghi nhận | Giữ tự động | Giữ thủ công | Khả dụng |
| ---: | ---: | ---: | ---: |
| 10.000.000 | 0 | 2.000.000 | 8.000.000 |

Sổ cái thêm `MANUAL_HOLD +2.000.000`.

### Tình huống 3 — Chuyển 1.500.000 sang tháng 08/2026

Trong khối Chuyển kỳ:

- Số tiền: `1.500.000`.
- Kỳ đích: `2026-08`.
- Lý do: `Dời ghi nhận sang kỳ sau theo phê duyệt.`

| Ghi nhận | Giữ thủ công | Đã chuyển kỳ sau | Khả dụng |
| ---: | ---: | ---: | ---: |
| 10.000.000 | 2.000.000 | 1.500.000 | 6.500.000 |

Sổ cái có hai dòng: `TRANSFER_OUT -1.500.000` và `TRANSFER_IN +1.500.000`, trong đó dòng IN mang kỳ đích `2026-08`.

### Tình huống 4 — Lập lịch trả 4.000.000 trong tháng 09/2026

Nhập `4.000.000`, kỳ trả `2026-09`, ghi chú `Đợt chi trả tháng 9`.

| Ghi nhận | Giữ thủ công | Đã chuyển | Đã lập lịch | Khả dụng |
| ---: | ---: | ---: | ---: | ---: |
| 10.000.000 | 2.000.000 | 1.500.000 | 4.000.000 | 2.500.000 |

Sau khi bấm **Chi trả** tại Lịch chi trả:

| Ghi nhận | Giữ thủ công | Đã chuyển | Đã lập lịch | Khả dụng | Đã trả |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 10.000.000 | 2.000.000 | 1.500.000 | 0 | 2.500.000 | 4.000.000 |

### Tình huống 5 — Giảm bonus thủ công 500.000

Chọn **Giảm**, nhập `500.000`, nêu lý do `Điều chỉnh sau đối soát chi phí`.

| Ghi nhận | Giữ thủ công | Đã chuyển | Khả dụng | Đã trả |
| ---: | ---: | ---: | ---: | ---: |
| 9.500.000 | 2.000.000 | 1.500.000 | 2.000.000 | 4.000.000 |

Sổ cái thêm `MANUAL_DECREASE -500.000`; công thức bonus quý/tháng ban đầu không bị thay đổi.

### Tình huống 6 — Payment Received chuyển YES về NO sau đó

Nếu JOB còn khả dụng chuyển `YES → NO`, hệ thống chuyển phần khả dụng của JOB đó sang Giữ tự động. Khoản đang giữ thủ công không bị tính lặp lại. Cần xem phần **Dự kiến** trước khi Lưu.

## 10. Checklist trước khi chốt chi trả

- [ ] Kỳ/quý và Sales Rep đang hiển thị là đúng.
- [ ] Thưởng/tháng trong lịch sử import đã được đồng bộ vào Ví.
- [ ] Mọi Payment Received và Remark của JOB đã được rà soát.
- [ ] Các JOB cần chờ phê duyệt đã có Giữ thủ công.
- [ ] Đã chuyển kỳ sau và Đã lập lịch có lý do/kỳ đích đúng.
- [ ] Khả dụng đủ để chi trả; Cần thu hồi bằng 0.
- [ ] Đã kiểm tra lịch sử sổ cái có đầy đủ bút toán tương ứng.
- [ ] Người có thẩm quyền đã xác nhận số tiền chi trả.

## 11. Kiểm thử kỹ thuật

Sau khi thay đổi logic Ví/phễu, chạy kiểm thử backend:

```powershell
Set-Location 'D:\SEALINK WEB\backend'
.\.venv\Scripts\python.exe -m pytest tests/test_commission_wallet_api.py -q
```

Bản kiểm thử bao gồm phân bổ theo JOB, giữ/mở khóa, điều chỉnh, chuyển kỳ, lập lịch và chi trả.

## 12. Khi nào cần báo IT/Quản trị hệ thống

Báo ngay khi gặp một trong các trường hợp sau:

- Tổng Ví không khớp với Thưởng/tháng sau khi đã Đồng bộ ví.
- Bút toán chuyển hiển thị khác số tiền đã xác nhận tại modal.
- Khả dụng âm nhưng không có lý do điều chỉnh/hủy kỳ.
- JOB Payment Received đã đổi nhưng không tạo dòng sổ cái phù hợp.
- Không thể chi trả/hủy lịch hoặc số tiền lịch không khớp phân bổ JOB.

Khi báo lỗi, gửi kèm: tên Sales Rep, kỳ nguồn, JOB #, ảnh bảng tóm tắt, và các dòng liên quan trong Lịch sử sổ cái.
