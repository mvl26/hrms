# Spec — Số buổi ăn trưa ghi nhận trên Attendance (nguồn duy nhất)

Trạng thái: **Approved (design)** 2026-07-25 ("chạy tiếp"). Nhánh `feat/skip-attendance-diag`.
Liên quan: [[project-vn-payroll-mvl]], [[project-attendance-code-timekeeping]].

## 1. Vấn đề / hiện trạng

Phụ cấp ăn trưa (component **J**) trên phiếu lương **đã tự động** — engine đọc `count_lunch_days`
([lunch.py](../hrms/vn_payroll/lunch.py)) suy từ **checkin + chấm công**: ngày tính ăn khi là ngày
công (status Present/Half Day) VÀ checkin phủ giờ nghỉ trưa của ca (vào < lunch_start, ra ≥ lunch_end;
mặc định 12:00–13:30). Nhưng **số buổi ăn trưa chỉ lưu trên Salary Slip** (`custom_lunch_days`, tính
tại lúc lập phiếu) — **không ghi vào từng Attendance, không có trong report chấm công**.

## 2. Mục tiêu (user chốt)

Ghi số buổi ăn trưa thành **cờ per-Attendance**, làm **NGUỒN DUY NHẤT**: report chấm công, Bảng Công
Tháng (bản in ký), và phiếu lương đều **đếm từ cờ này** — một chỗ tính, khớp tuyệt đối, kiểm toán được.

**Giữ luật hiện tại:** ngày WFH / công tác / on-duty / quên chấm công (không có checkin phủ giờ trưa)
→ **không tính ăn** (ăn trưa = có mặt thực tế tại công ty). Override tay per-NV vẫn còn
(`custom_lunch_days_override` trên Salary Structure Assignment).

## 3. Thiết kế

### 3.1 Field trên Attendance
`Attendance-custom_lunch` (Check 0/1, nhãn "Ăn trưa") — fixture Custom Field + đồng bộ bộ lọc
`fixtures` trong hooks.py. Thuần dữ liệu; KHÔNG đụng `status`/`leave_type`/`half_day_status`.

### 3.2 Tính cờ (một luật)
Tách [lunch.py](../hrms/vn_payroll/lunch.py):
- `is_lunch_day(status, shift, day_checkin_datetimes) -> bool` — luật per-ngày (đúng luật hiện có).
- Attendance controller: method `set_lunch_flag()` gọi trong `before_validate` (sau bridge, khi status
  đã có) → đọc Employee Checkin của ngày đó → set `self.custom_lunch`. Tự chạy khi
  `process_auto_attendance` tạo/cập nhật Attendance và khi sửa tay.
- `count_lunch_days` cũ (quét checkin theo kỳ) → giữ làm **engine recompute** (dùng lại `is_lunch_day`).

### 3.3 Payroll đọc từ Attendance *(chạm lương — CỔNG KÝ)*
`count_lunch_days_from_attendance(employee, start, end)` = `Σ custom_lunch` (Attendance docstatus=1
trong kỳ). `apply_mvl`: `lunch_days = custom_lunch_days_override or count_lunch_days_from_attendance(...)`.
**GATE bắt buộc:** test bất biến — với cùng dữ liệu, `Σ cờ` (sau recompute) == `count_lunch_days` cũ
== `custom_lunch_days` trên 12 phiếu đã submit → phụ cấp J không đổi.

### 3.4 Report Bảng chấm công
`monthly_attendance_report.get_sheet_rows`: thêm `lunch_days` vào `totals` mỗi NV (Σ custom_lunch của
Attendance ngày công). Thêm cột "Số buổi ăn trưa" vào report.

### 3.5 Bảng Công Tháng (Monthly Attendance Sheet)
Thêm field `lunch_days` vào `Monthly Attendance Sheet Detail`; `populate_from_attendance` cộng
`custom_lunch`; print format ký thêm cột "Ăn trưa".

### 3.6 Làm mới khi checkin về muộn
Cờ tính lại mỗi lần Attendance lưu (validate hook — phủ luồng process_auto_attendance). Cho checkin
về muộn sau khi Attendance đã chốt: tiện ích `recompute_lunch_flags(month, year, company=None)`
(whitelist + bench execute) tính lại `custom_lunch` từ checkin (db_set, update_modified=False) — chạy
TRƯỚC khi chốt lương. **KHÔNG** gọi từ Bảng Công Tháng (giữ nguyên tắc "sheet không bao giờ ghi
Attendance"); report/sheet/payroll đều đọc cùng cờ đã lưu nên nhất quán tại thời điểm đọc.
`compute_lunch_flags_for_period` (thuần, không ghi) tách riêng để test.

### 3.7 Backfill *(data-migration — ASK-FIRST, không tự chạy)*
`hrms.vn_payroll.lunch.backfill_lunch_flags(dry_run=1)` set `custom_lunch` cho MỌI Attendance đã
submit từ checkin — chạy qua `bench execute` (KHÔNG đưa vào patches.txt để tránh auto-run khi migrate
việc khác). Idempotent, mặc định dry_run. Chỉ chạy trên `miyano` sau sign-off.

## 4. Cổng & phi mục tiêu
- **Payroll GATE** (§3.3): số buổi ăn trưa bất biến trước/sau — bắt buộc xanh.
- Test qua **rollback harness** (KHÔNG run-tests trên miyano); cờ test in-memory (bẫy DDL Custom Field).
- **Không tự deploy**: migrate fixture + `bench build` + restart + backfill = ask-first. Build+test trên nhánh.
- Không đánh dấu từng ô ngày trên lưới (user không chọn); chỉ tổng ở report + Bảng Công Tháng.
