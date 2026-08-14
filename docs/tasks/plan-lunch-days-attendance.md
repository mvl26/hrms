# Plan — Số buổi ăn trưa trên Attendance (nguồn duy nhất)

Spec `docs/spec/lunch-days-attendance.md`. Nhánh `feat/skip-attendance-diag`. **User commit tay** (không
auto-commit). Test qua rollback harness. Thứ tự: L1→L2→L3→L4→L5→L6→L7→L8.

**Tiến độ 2026-07-25:** L1–L8 ✅ — **62 test xanh** qua harness (gồm gate payroll-invariance L3 +
regression lunch/salary-slip/report/sheet), no-leak đã kiểm. Chưa commit, chưa deploy (gate ask-first).

## L1 — Field `Attendance-custom_lunch` (Check)
- Thêm Custom Field vào `hrms/fixtures/custom_field.json` + tên vào bộ lọc `fixtures` hooks.py.
- AC: fixture có field (Check, dt=Attendance); `test_hooks_fixture_filters_match_fixture_files` xanh.

## L2 — Luật per-ngày + hook cờ trên Attendance
- `lunch.py`: tách `is_lunch_day(status, shift, day_datetimes)`; `count_lunch_days` dùng lại nó.
- `attendance.py`: `set_lunch_flag()` gọi trong `before_validate` (sau bridge) → set `custom_lunch`.
- AC (in-memory): is_lunch_day đúng (đủ vào-ra phủ trưa=1; thiếu=0; status nghỉ=0); hook set cờ đúng
  cho Attendance có/không checkin; `count_lunch_days` cũ vẫn khớp giá trị cũ.

## L3 — Payroll đọc Σ cờ *(CỔNG KÝ)*
- `count_lunch_days_from_attendance(emp, start, end)` = Σ custom_lunch (docstatus=1).
- `salary_slip_hook.apply_mvl`: đổi nguồn lunch_days sang hàm mới (giữ override).
- AC/GATE: `Σ cờ (sau recompute)` == `count_lunch_days` cũ trên cùng data; J/phụ cấp không đổi.

## L4 — Report cột "Số buổi ăn trưa"
- `monthly_attendance_report`: thêm `lunch_days` vào totals + cột.
- AC: get_sheet_rows trả `totals["lunch_days"]` = Σ custom_lunch; report có cột.

## L5 — Bảng Công Tháng (Monthly Attendance Sheet)
- Thêm field `lunch_days` vào `Monthly Attendance Sheet Detail` (JSON); populate cộng custom_lunch;
  print format thêm cột "Ăn trưa".
- AC: populate_from_attendance điền lunch_days đúng; test snapshot.

## L6 — Recompute utility
- `recompute_lunch_flags(month, year, company=None)` (whitelist); Bảng Công Tháng populate gọi trước.
- AC: recompute set lại cờ từ checkin; idempotent.

## L7 — Backfill patch *(ASK-FIRST — code only, không chạy)*
- `hrms/patches/.../backfill_lunch_flags.py` (dry_run, idempotent) + entry patches.txt (chưa chạy prod).
- AC: dry-run trả số ngày sẽ set, không đổi payroll field khác.

## L8 — Docs + memory
- Cập nhật CLAUDE.md (mục payroll/ăn trưa) + [[project-vn-payroll-mvl]]; đánh dấu plan.

## Sau build (GATE ask-first): migrate fixture + field · `bench build` · restart · backfill · sign-off payroll.
