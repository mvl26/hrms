# Spec — Tách bạch Đơn xin nghỉ ↔ Yêu cầu chấm công

Trạng thái: **Approved (design)** — 2026-07-25. Nhánh: `feat/skip-attendance-diag`.
Liên quan: [[project-attendance-request-locked]], [[project-leave-single-pool]],
[[project-attendance-code-timekeeping]].

## 1. Vấn đề

Hệ thống đang **lẫn** hai khái niệm khác bản chất, dồn tất vào **Đơn xin nghỉ**:

- **Đơn xin nghỉ phép** (Leave Application) — nhân viên **KHÔNG đi làm**: nghỉ có lương (P/Ô/Cô,
  TS/N/T), không lương (K), nghỉ bù (NB). Trừ quỹ phép hoặc trừ lương.
- **Yêu cầu chấm công** (Attendance Request) — nhân viên **ĐANG làm việc / phải tính có mặt**:
  làm tại nhà (WFH), quên/thiếu chấm công, ra ngoài công việc (on-duty), đi muộn/về sớm có phép.
  **Không trừ quỹ**, tính đủ công.

Nguyên nhân: kênh **Attendance Request** (native Frappe) đã bị **khoá cứng** 2026-07-24
(`block_attendance_request`, gỡ khỏi PWA) vì lúc đó nó thiếu người duyệt → ghi thẳng ra Attendance.
Hệ quả: người WFH / quên chấm công không còn kênh đúng → bị đẩy sang xin nghỉ (sai bản chất, trừ
oan quỹ phép).

## 2. Quyết định (user chốt 2026-07-25)

- Kênh **Yêu cầu chấm công** bao 4 tình huống: **WFH, quên/thiếu chấm công, on-duty, đi muộn/về sớm**.
- **Duyệt bởi quản lý trực tiếp** (leave approver / `reports_to`), KHÔNG phải COO (khác Công Tác).
- Bảng chấm công **hiện mã riêng từng loại**: WFH→**W** (mã mới), on-duty→**CT** (tái dùng mã công tác), quên-chấm & muộn/sớm→**X**.
- Phương án **A**: mở lại native `Attendance Request`, lắp đúng phần nó thiếu (duyệt + mã công + PWA).
  KHÔNG xây DocType mới, KHÔNG gộp vào Công Tác.

## 3. Ranh giới 3 kênh (bất biến)

| | Đơn xin nghỉ | **Yêu cầu chấm công** | Công Tác |
|---|---|---|---|
| Bản chất | KHÔNG đi làm | ĐANG làm / tính có mặt | Chuyến công tác có chi phí |
| Ảnh hưởng | trừ quỹ / không lương | **không trừ quỹ, đủ công** | đủ công + Expense Claim |
| Mã công | P/Ô/Cô/TS/N/T/K/NB | **W / CT / X** | CT |
| Duyệt | quản lý trực tiếp | **quản lý trực tiếp** | COO (workflow) |
| Cơ chế | native + hook single-pool | **native + hook (mở lại)** | DocType Miyano |

## 4. Thiết kế kỹ thuật

### 4.1 Attendance Code mới (fixtures)
- **W** — Làm tại nhà (Work From Home): category `Công`, `maps_to_status = Work From Home`,
  `work_fraction = 1.0`, có lương. (Cùng status với CT nên payroll-neutral; reverse-bridge để CT làm
  mặc định, hook ghi đè W.) **Đây là mã Attendance Code MỚI duy nhất của tính năng này.**
- **On-duty (ra ngoài công việc = công tác)** tái dùng mã **CT** đã có — KHÔNG thêm mã mới.

### 4.2 Mở rộng `reason` (Property Setter → fixture)
Field `Attendance Request.reason` (Select). Options MỚI (giữ nguyên 2 native để logic status của
upstream chạy đúng):
`Work From Home` · `On Duty` · `Quên chấm công` · `Đi muộn/về sớm`.
Native `get_attendance_status`: WFH→*Work From Home*; các reason còn lại→*Present* (quên-chấm &
muộn/sớm ⇒ đủ công). Không đổi controller upstream.

### 4.3 Custom field người duyệt (fixtures/custom_field.json)
- **`Attendance Request.custom_approver`** (Link → User): mặc định = user của leave approver /
  `reports_to` của nhân viên; điền tự động ở `before_insert`/`validate` nếu để trống.

### 4.4 Duyệt bởi quản lý trực tiếp
Module mới `hrms/hr/doctype/attendance_request/attendance_request_miyano.py`:
- `set_default_approver(doc)` — `before_insert`/`validate`: điền `custom_approver` nếu trống.
- `assign_to_approver(doc)` — `after_insert`: giao ToDo cho `custom_approver` (pattern như Công Tác;
  không tạo trùng ToDo Open).
- `guard_submit(doc)` — `before_submit`: chỉ cho submit nếu session user == `custom_approver`
  **hoặc** có role `HR Manager`/`HR User` **hoặc** Administrator. Chặn nhân viên tự duyệt.
  → xoá lỗ hổng "ghi thẳng ra Attendance không qua duyệt".
- Gỡ wiring `block_attendance_request` (before_insert); thay bằng 3 hook trên.

### 4.5 Cầu nối mã công (bất biến lương)
`set_attendance_request_code(doc)` — wired `Attendance Request.on_submit` (chạy **sau**
`create_attendance_records` của upstream). Với mỗi Attendance mang `attendance_request == doc.name`,
ghi `custom_attendance_code` theo `reason` qua `frappe.db.set_value(..., update_modified=False)`:

Kênh này sinh ra **ĐÚNG BA mã: W, CT, X** — cả ba đều là ngày ĐI LÀM, đủ công (HR chốt 2026-08-05).
Nghỉ đi đường Đơn xin nghỉ, không phải đường này.

**Giá trị LƯU là tiếng Anh, người dùng chỉ thấy tiếng Việt** (chốt 2026-08-05) — dịch ở lớp hiển thị
qua `translations/vi.csv`, không lưu tiếng Việt xuống DB.

| reason (giá trị lưu) | nhãn tiếng Việt | mã công | ghi chú |
|---|---|---|---|
| `Work From Home` | Làm việc tại nhà | **W** | mã Attendance Code MỚI duy nhất của tính năng |
| `On Duty` | Đi công tác | **CT** | ra ngoài công việc — tái dùng mã CT sẵn có |
| `Remote Work` | Làm việc từ xa | **X** | làm ở ngoài, không cố định một nơi (vd chiều đi gặp khách) — vẫn là ngày công thường, KHÔNG phải W |
| `Missed Punch` | Quên chấm công | **X** | tức "xin chấm công bù" — không có mã riêng |
| `Late Or Early Leave` | Đi muộn/về sớm | **X** | |

Reason lạ / trống → `DEFAULT_CODE = X`. Ba nguồn phải khớp nhau: Property Setter `reason-options`
(fixtures) ↔ `REASON_TO_CODE` ↔ `vi.csv`; `test_every_reason_option_on_the_form_has_a_code` chặn
trôi — thêm lý do mà quên map thì ngày đó âm thầm rơi về X.

**Hệ quả cần biết:** ba lý do cuối cùng đều ra `X` nên **bảng chấm công không phân biệt được** làm
việc từ xa / quên chấm công / đi muộn-về sớm; lý do chỉ còn nằm trên chính phiếu Yêu cầu chấm công.
Muốn tách trên bảng thì phải thêm Attendance Code mới (quyết định của HR, không phải của code).

Nửa ngày (half_day): buổi được yêu cầu mang mã theo reason, buổi còn lại suy TỪ `half_day_status`
native — `Present` → `X` (đủ công cả ngày), `Absent` → `K` (nửa kia không lương). Buổi nào được yêu
cầu do người nộp chọn ở `custom_half_day_session` (Sáng/Chiều). **THUẦN HIỂN THỊ**: không đụng
`status`/`leave_type`/`half_day_status` → lương bất biến. Vá luôn lỗ "db_set bỏ qua bridge".

### 4.6 PWA (bật lại self-service)
- Khôi phục 3 route `/attendance-requests` (list/new/detail) trong `frontend/src/router/attendance.js`.
- Tile "Yêu cầu chấm công" ở `Home.vue` + mục "Recent Attendance Requests" ở `attendance/Dashboard.vue`.
- Form `AttendanceRequestForm.vue`: ô chọn `reason` (5 loại), tách hẳn khỏi màn Xin nghỉ. Nhãn VN do
  `FormField.vue` dịch (`label: __(option)`, `value` giữ tiếng Anh); danh sách lấy từ meta nên không
  hardcode ở frontend. `AttendanceRequestItem.vue` cũng phải bọc `__()` — thiếu là màn danh sách hiện
  thẳng giá trị tiếng Anh (sửa 2026-08-13).
- `yarn build-pwa`.

## 5. Cổng bắt buộc & phi mục tiêu

- **Payroll-invariance GATE**: test chứng minh Salary Slip `payment_days`/`absent_days`/LWP **giống hệt**
  trước/sau, cho cả 4 reason (so với ngày Present native). Bắt buộc trước khi coi §4.5 xong.
- **Fixtures filter sync**: thêm `custom_approver`, Attendance Code W (mới), Property Setter `reason` vào
  bộ lọc `fixtures` trong `hooks.py` — `test_setup_vn_defaults` bắt buộc khớp JSON.
- Test qua **rollback harness** (KHÔNG `run-tests` trên miyano). Bẫy **DDL rò rỉ**: test hook bằng
  thuộc tính in-memory trên doc, KHÔNG insert Custom Field/Property Setter trong test.
- Giữ upstream mergeable: additive, `git revert`-able, KHÔNG fork hành vi upstream đã test
  (guard tha HR Manager/Administrator để 10 test upstream của Attendance Request còn xanh).

**Phi mục tiêu / gate ask-first (KHÔNG tự làm):** migrate fixture + Property Setter lên site; restart
gunicorn; deploy prod. Build + test trên nhánh; dừng trước deploy, bàn giao.
