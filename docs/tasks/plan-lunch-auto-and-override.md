# Kế hoạch — Tự chấm ăn trưa + chọn tay per-ngày

Spec: [`docs/spec/lunch-days-attendance.md`](../spec/lunch-days-attendance.md) §5 (2026-08-27).
Nhánh: `feat/skip-attendance-diag`. Chạy test qua **harness rollback** (KHÔNG `run-tests` trên miyano).

## Bối cảnh cần nhớ khi làm

- `custom_lunch` (Check, read_only) là **kết quả cuối**, mọi nơi đếm đều Σ field này — **không đổi
  vai trò của nó**, nếu không phải sửa report + Bảng Công Tháng + phiếu lương.
- `apply_correction` dùng `frappe.db.set_value` ⇒ **không chạy** `before_validate`. Mọi field cần
  cập nhật ở đường soát công phải được liệt kê tường minh.
- Đổi fixtures phải sửa **cả** `hrms/fixtures/custom_field.json` **và** bộ lọc `fixtures` trong
  `hooks.py` — `hrms/tests/test_setup_vn_defaults.py` bắt lệch.
- Bẫy đã biết: harness rollback **có thể rò** khi có câu DDL (thêm Custom Field). Test phải dựng cờ
  **in-memory**, không tạo Custom Field thật trong test.

## T1 — Luật tính, thuần hàm (TDD trước tiên)

`hrms/vn_payroll/lunch.py`: thêm

```python
NO_LUNCH_CODES = ("CT", "W")
LUNCH_OVERRIDE_YES, LUNCH_OVERRIDE_NO = "Có", "Không"

def effective_lunch_flag(status, code, shift, day_datetimes, override=None) -> int
```

Luật đúng §5.4. `is_lunch_day` cũ giữ nguyên chữ ký (đang có test bám vào), gọi lại từ hàm mới cho
nhánh ≥2 lần chấm.

**Test** (`hrms/vn_payroll/tests/test_lunch.py`, class mới `TestEffectiveLunchFlag`):
1. Present, 0 lần chấm → 1
2. Present, 1 lần chấm → 1
3. Present, 2 lần chấm nhưng ra lúc 11:00 → 0
4. Present, 2 lần chấm phủ giờ trưa → 1
5. Half Day, 0 lần chấm → 0
6. Half Day, 2 lần chấm phủ giờ trưa → 1 *(không đổi so với hiện tại)*
7. Mã `CT` / `W` → 0 kể cả Present + checkin phủ giờ trưa
8. `On Leave` → 0
9. override `Có` → 1 kể cả On Leave / không chấm
10. override `Không` → 0 kể cả checkin phủ giờ trưa

- [ ] Đỏ trước, xanh sau, chạy harness.

## T2 — Field `custom_lunch_override`

- [ ] `hrms/fixtures/custom_field.json`: `Attendance-custom_lunch_override`, Select
      `Tự động\nCó\nKhông`, default `Tự động`, `insert_after: custom_lunch`, nhãn **Ăn trưa**,
      description nói rõ `Tự động` = suy từ chấm công + checkin.
- [ ] Đổi `description` của `custom_lunch` thành "Kết quả cuối (chỉ đọc) — xem ô Ăn trưa để chỉnh tay".
- [ ] Thêm tên field vào bộ lọc `fixtures` trong `hooks.py`.
- [ ] `hrms/tests/test_setup_vn_defaults.py` phải vẫn xanh (nó bắt lệch JSON ↔ hooks).

## T3 — `Attendance.set_lunch_flag()` dùng luật mới

`hrms/hr/doctype/attendance/attendance.py`:

- [ ] Đọc `self.custom_lunch_override` (guard `has_field`, site chưa migrate thì coi như `Tự động`).
- [ ] Gọi `effective_lunch_flag(...)` với mã công của ngày (`custom_attendance_code`).
- [ ] `lunch_flag_for_attendance` trong `lunch.py` nhận thêm `code` + `override`.

**Test** (`hrms/hr/doctype/attendance/`): lưu Attendance chấm tay Present không checkin → `custom_lunch`
= 1; đặt override `Không` rồi **lưu lại 2 lần** → vẫn 0 *(regression cho bug "máy đè lại")*.

## T4 — Vá đường soát công

`hrms/hr/attendance_review.py::apply_correction`:

- [ ] Tính lại cờ theo mã mới rồi **thêm `custom_lunch` vào dict `db_set`**.
- [ ] Tôn trọng override đã đặt trên bản ghi.

**Test** (`hrms/hr/tests/test_attendance_review.py`): ngày `X` có checkin (cờ 1) → sửa sang `P` →
cờ về **0** *(regression cho bug đang sai tiền trên dữ liệu thật)*; sửa `P` → `X` không checkin → cờ lên 1.

## T5 — `recompute_lunch_flags` tôn trọng override

- [ ] `compute_lunch_flags_for_period` đọc thêm `custom_attendance_code` + `custom_lunch_override`,
      dùng `effective_lunch_flag`.
- [ ] Test: bản ghi override `Có` không bị lượt recompute đưa về 0.

## T6 — Cổng bất biến số công

- [ ] Test: sau mọi thay đổi trên, `payment_days` / `absent_days` / `status` / `leave_type` /
      `half_day_status` của Attendance và Salary Slip **không đổi** — chỉ `custom_lunch` đổi.

## T7 — Chốt

- [ ] Toàn bộ test lương + chấm công xanh qua harness, `HARNESS_NO_LEAK`.
- [ ] `pre-commit run --files ...` sạch.
- [ ] Commit (Conventional Commits, scope `(hr)`), nêu rõ đây là đảo quyết định §2 của spec cũ.

## T8 — Deploy *(cổng ký riêng)*

- [ ] `bench --site miyano migrate` — nạp Custom Field mới.
- [ ] **HỎI TRƯỚC** rồi mới `recompute_lunch_flags(7, 2026)` trên dữ liệu thật (đổi tiền: ròng +1 buổi).
- [ ] Báo lại số bản ghi đổi + đối chiếu lại phụ cấp J trên 6 phiếu 7/2026.
