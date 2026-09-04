# Quy tắc đồng bộ dữ liệu realtime trên frontend

Sau khi người dùng tạo, sửa, duyệt hoặc xóa dữ liệu thành công, mọi vùng giao diện đang hiển thị dữ liệu liên quan phải cập nhật ngay mà không yêu cầu F5.

## Quy ước bắt buộc

- Mọi request ghi dữ liệu trong phiên đăng nhập phải đi qua `apiRequest` hoặc `credentialedFetch`.
- Không gọi `window.location.reload()` để đồng bộ dữ liệu nghiệp vụ.
- Thành phần vừa thao tác có thể cập nhật state cục bộ ngay; tín hiệu `sealink:data-changed` sẽ đồng bộ các bảng/tổng hợp bên ngoài.
- Nhiều request trong cùng một thao tác Lưu được gom thành một tín hiệu để tránh gọi API lặp.
- Request chỉ đọc hoặc preview/inspect file không phát tín hiệu thay đổi dữ liệu.
- Chỉ tải lại trang khi cần nhận mã frontend mới và hot reload không thực hiện được.

## Điểm triển khai

- `frontend/src/shared/api/dataSync.ts`: phát và đăng ký tín hiệu thay đổi dữ liệu.
- `frontend/src/shared/api/credentialedFetch.ts`: tự phát tín hiệu sau mutation thành công.
- `frontend/src/App.tsx`: làm mới các nguồn dữ liệu dùng chung theo endpoint đã thay đổi.
- Module có state riêng vẫn nên cập nhật state ngay sau Save; nếu dữ liệu còn được hiển thị ở nơi khác, nhận thêm `externalRefreshVersion` hoặc đăng ký `subscribeDataChanged`.
