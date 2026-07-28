# Plan — Yêu cầu chấm công (mở lại Attendance Request có duyệt)

Spec: `spec/attendance-request-vs-leave.md`. Nhánh: `feat/skip-attendance-diag`.
Commit: **user commit thủ công** (không auto-commit từng task). Test qua rollback harness.

Thứ tự phụ thuộc: T1 → T2 → T3 → T4 → T5 → T6 → T7. T7 (PWA) độc lập backend, làm cuối.

**Tiến độ 2026-07-25:** T1–T6 ✅ (26 test xanh qua harness, payroll-invariance gate T5 xanh). T7 (PWA)
đang làm. Chưa commit (user commit thủ công). Chưa deploy prod (gate ask-first).

---

## T1 — Attendance Code W (fixtures); on-duty tái dùng CT
- **Làm:** thêm 1 code MỚI vào `hrms/fixtures/attendance_code.json`: W (Công, Work From Home, wf 1.0).
  On-duty (ra ngoài công việc = công tác) tái dùng mã **CT** đã có. Xác nhận `attendance_code` đã nằm
  trong bộ lọc `fixtures` của hooks.py.
- **AC:** JSON hợp lệ; W.maps_to_status="Work From Home", category "Công", wf 1.0; CT vẫn có; không còn CV.
- **Đụng:** `hrms/fixtures/attendance_code.json` (+ test).

## T2 — Custom field `custom_approver` + Property Setter `reason`
- **Làm:** thêm `Attendance Request-custom_approver` (Link User) vào `hrms/fixtures/custom_field.json`;
  thêm Property Setter mở rộng options `Attendance Request.reason`; đăng ký cả hai + W vào bộ lọc
  `fixtures` trong `hooks.py` (thêm "Property Setter" filter theo doc_type nếu chưa có).
- **AC:** `test_setup_vn_defaults` (fixtures ↔ hooks filter) xanh; fixture JSON hợp lệ; options reason
  chứa đủ 4 giá trị. KHÔNG insert field trong test (bẫy DDL) — kiểm bằng đọc JSON + filter list.
- **Đụng:** `hrms/fixtures/custom_field.json`, `hrms/hooks.py` (thêm phụ gia, không đụng dòng WIP).

## T3 — Duyệt bởi quản lý trực tiếp (gỡ khoá + guard)
- **Làm:** module `attendance_request_miyano.py`: `set_default_approver`, `assign_to_approver`,
  `guard_submit`. Gỡ wiring `block_attendance_request` trong hooks.py; wire before_insert/validate →
  set_default_approver, after_insert → assign_to_approver, before_submit → guard_submit. Cập nhật
  `TestAttendanceRequestBlocked` → `TestAttendanceRequestApproval` trong test_business_trip.py (hoặc
  test riêng cạnh module).
- **AC (test in-memory + harness):** approver mặc định suy từ reports_to/leave approver; submit bởi
  non-approver (không HR role) → throw; submit bởi approver/HR Manager/Administrator → OK; 10 test
  upstream của Attendance Request vẫn xanh.
- **Đụng:** module mới + `hrms/hooks.py` + test.

## T4 — Cầu nối mã công `set_attendance_request_code`
- **Làm:** hàm trong `attendance_request_miyano.py`; wire `Attendance Request.on_submit`. Map
  reason→mã (WFH→W, On Duty→CT, quên/muộn→X); nửa ngày tách morning/afternoon; ghi qua
  `db.set_value(update_modified=False)` chỉ các field hiển thị.
- **AC:** sau submit, Attendance có `custom_attendance_code` đúng theo 4 reason; nửa ngày tách đúng
  buổi; `status`/`leave_type`/`half_day_status` KHÔNG đổi.
- **Đụng:** `attendance_request_miyano.py` + `hrms/hooks.py` + test.

## T5 — GATE payroll-invariance
- **Làm:** test so Salary Slip `payment_days`/`absent_days`/LWP giữa (a) ngày Present native và
  (b) ngày tạo qua Attendance Request cho từng reason (WFH/On Duty/quên/muộn).
- **AC:** cả 4 reason → 3 field payroll GIỐNG HỆT ngày Present; is_lwp=0. Nếu lệch → dừng, báo user.
- **Đụng:** test.

## T6 — Đồng bộ tài liệu + ensure_defaults note
- **Làm:** cập nhật `setup_vn_defaults.py` cảnh báo (không tạo) nếu thiếu W; cập nhật CLAUDE.md /
  spec ghi chú 3-kênh; đánh dấu plan.
- **AC:** ensure_defaults chạy không lỗi; không tạo master data mới ngoài cảnh báo.
- **Đụng:** `hrms/setup_vn_defaults.py`, docs.

## T7 — PWA bật lại self-service
- **Làm:** khôi phục route/tile/dashboard đã gỡ (2026-07-24); form thêm ô `reason` 4 loại; `yarn
  build-pwa`.
- **AC:** build PWA thành công; route `/attendance-requests` có lại; grep thấy "attendance-requests"
  trong bundle .js thực thi. (Verify trình duyệt = thủ công, ghi chú.)
- **Đụng:** `frontend/src/router/attendance.js`, `views/Home.vue`, `views/attendance/Dashboard.vue`,
  `views/attendance/AttendanceRequestForm.vue`.

---

## Sau khi build xong (GATE ask-first — KHÔNG tự làm)
migrate fixture + Property Setter · restart gunicorn · deploy prod. Bàn giao user.
