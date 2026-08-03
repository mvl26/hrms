# Đồng bộ mã công cho mọi loại nghỉ

**Ngày:** 2026-08-03 · **Trạng thái:** thiết kế đã duyệt

## 1. Vấn đề

Nghỉ phép **có lương** nhưng bảng chấm công hiện mã `V` (vắng) và đếm vào cột **Vắng** thay vì **Phép**.

Đã tái hiện được trên site `miyano` (dưới rollback, không ghi dữ liệu thật). **Hai lỗi chồng nhau:**

### Lỗi 1 — `db_set` bỏ qua cầu nối mã công

[`leave_application.py:284-299`](../hrms/hr/doctype/leave_application/leave_application.py) — nhánh *cập nhật bản ghi đã có* dùng `doc.db_set(...)`, ghi thẳng xuống DB nên `before_validate` → `apply_attendance_code_bridge()` không chạy. Mã công cũ nằm nguyên.

Diễn biến: job `hourly_long` tạo Attendance `Absent` (mã `V`) vì không có checkin → đơn nghỉ duyệt sau → `db_set` lật `status`/`leave_type` nhưng để nguyên `V`.

| Đường đi | Kết quả |
|---|---|
| Đã có bản ghi `Absent` → `db_set` | On Leave + Nghỉ phép năm + mã **`V`** ← sai |
| Chưa có bản ghi → `insert()` | On Leave + Nghỉ phép năm + mã **`P`** ← đúng |

**Lớp Miyano đã có hàng rào nhưng hụt:** [`leave_single_pool.set_leave_attendance_code`](../hrms/hr/doctype/leave_application/leave_single_pool.py) hook vào `on_submit` (chạy *sau* `update_attendance`) ghi mã đúng cách — nhưng dòng 63 `if doc.get("leave_type") != POOL_LEAVE_TYPE: return` chỉ áp cho `"Nghỉ phép năm"`. Mọi loại nghỉ khác rơi vào nhánh "để bridge tự suy" — mà bridge không chạy trên đường `db_set`.

### Lỗi 2 — loại nghỉ không được map tới mã công nào

`"Nghỉ phép năm có tính lương"` không nằm trong 8 Leave Type fixture. Không `Attendance Code` nào trỏ tới nó ⇒ suy ngược trả về **rỗng**. Sửa lỗi 1 thôi **chưa đủ** cho loại nghỉ này.

### Mức ảnh hưởng

- **Tiền lương KHÔNG sai.** Payroll đọc `status`/`leave_type`/`half_day_status` — cả ba đúng. `Công = 0` cũng đúng: mã `P` có `work_fraction = 0.0`.
- **Bảng chấm công sai.** Tổng cột gom theo *category* của mã công (`"Vắng" → absent`, `"Phép" → annual_leave`) nên ngày này đếm nhầm cột trên bảng đã ký.

## 2. Ràng buộc mô hình dữ liệu

**Một loại nghỉ → NHIỀU mã công.** `P` và `1/2P` cùng trỏ `"Nghỉ phép năm"`; `K` và `1/2K` cùng trỏ `"Nghỉ không lương"`. Phân biệt bằng `maps_to_status` (`On Leave` vs `Half Day`) — đó là lý do tồn tại `_pick_reverse_code`.

⇒ **Một ô "mã công" trên Leave Type không thể là nguồn sự thật** — không diễn tả được cặp cả-ngày/nửa-ngày. `Attendance Code.leave_type` vẫn là nguồn duy nhất.

## 3. Thiết kế

### Phần 1 — Tổng quát hoá `set_leave_attendance_code`

Bỏ chốt chặn theo `POOL_LEAVE_TYPE`. Với loại nghỉ ngoài quỹ phép năm: suy mã từ `Attendance Code` khớp `maps_to_status` + `leave_type` (dùng lại `_pick_reverse_code` để chọn xác định khi nhiều mã khớp), rồi ghi **display-only** qua `frappe.db.set_value` — đúng cách hàm này đang làm.

Ghi thêm `custom_work_credit` từ `work_fraction` của mã. **Tuyệt đối không đụng** `status` / `leave_type` / `half_day_status` ⇒ payroll bất biến theo cấu trúc.

Không map được mã thì **để nguyên**, không bịa.

### Phần 2 — Ô chọn mã công trên Leave Type

Custom field `Leave Type-custom_attendance_code` (Link → Attendance Code), nhãn **"Mã công cả ngày"**.

- Là **mặt bàn để nhập**, không phải nguồn sự thật: khi lưu Leave Type, ghi ngược `Attendance Code.leave_type = <loại nghỉ này>` và gỡ liên kết khỏi mã cả-ngày cũ nếu đổi.
- Chỉ nhận mã có `maps_to_status` ∈ {`On Leave`, `Half Day`}; chọn mã khác thì `throw`.
- Mã **nửa ngày** vẫn quản ở phía Attendance Code (một ô không chứa được cặp).
- Leave Type chưa có mã cả-ngày nào trỏ tới ⇒ `msgprint` cảnh báo khi lưu, **không chặn** (HR vẫn phải tạo được loại nghỉ).

### Phần 3 — Nút đồng bộ (xem trước rồi mới áp)

Module `hrms/hr/attendance_code_sync.py`, hai endpoint whitelist:

- `preview_sync(filters)` → liệt kê bản ghi mà mã công lệch với `status`/`leave_type`: `{attendance, employee, employee_name, attendance_date, old_code, new_code, skipped_reason}`. **Không ghi gì.**
- `apply_sync(rows, reason)` → áp đúng danh sách người dùng đã duyệt.

Ràng buộc:
- **Né kỳ đã chốt** — `guard_period_not_locked` *throw*, phải bắt và xếp vào `skipped` kèm lý do, không để vỡ giữa chừng.
- **Chỉ ghi field hiển thị** (`custom_attendance_code`, `custom_morning_code`, `custom_afternoon_code`, `custom_work_credit`).
- **Ghi vết** vào `Attendance Correction Log` (doctype sẵn có, đủ field old/new + reason + người + lúc).
- Bỏ qua bản ghi có mã nhập tay theo buổi (`custom_morning_code`/`custom_afternoon_code`) — không đè ý định của người dùng.

Nút đặt cạnh **"Chốt công tháng"** sẵn có trên báo cáo chấm công tháng, dùng chung bộ lọc kỳ/công ty của báo cáo.

## 4. Ngoài phạm vi

- Sửa `leave_application.py` thượng nguồn — lớp Miyano xử lý đủ, giữ vá ở một chỗ.
- Đổi tên / gộp Leave Type trên dữ liệu thật (không `git revert` được — cần ký duyệt riêng).
- Backfill tự động không qua nút.

## 5. Kiểm chứng

- Test tái hiện lỗi 1: Attendance `Absent`(`V`) có sẵn → duyệt đơn nghỉ **không** thuộc quỹ phép năm → mã phải thành mã của loại nghỉ đó, không còn `V`.
- Test lỗi 2: Leave Type chưa map → mã để **rỗng**, không bịa; map rồi → ra đúng mã.
- Test phần 2: ghi ngược đúng, đổi mã thì gỡ liên kết cũ, mã sai `maps_to_status` thì `throw`.
- Test phần 3: preview không ghi gì; apply chỉ đổi field hiển thị; kỳ đã chốt vào `skipped`; có vết trong `Attendance Correction Log`.
- **Cổng bất biến payroll**: `payment_days`/`absent_days`/LWP trước-sau không đổi.
