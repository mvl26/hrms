# Plan — Giờ làm linh hoạt + hoàn thiện tuyến chấm công → lương

Spec `spec/flex-shift-and-timekeeping-pipeline.md`. Nhánh `feat/skip-attendance-diag`.
Thứ tự: T1→T12. Mỗi task kết thúc bằng một commit.

**Goal:** ca trượt theo giờ vào + luật đủ-giờ (`X` / `1/2X` / `V`), và bổ sung 3 mắt xích còn thiếu
của tuyến — soát công, chốt công có khoá kỳ, cổng đối soát lương.

**Architecture:** GĐ1 thay lõi `apply_vn_half_day_classifier` (luật giờ thay luật phủ-50%). GĐ2 thêm
một cửa ghi duy nhất `apply_correction` + nhật ký bất biến, UI lưới dùng lại `get_sheet_rows`. GĐ3
khoá kỳ theo Bảng Công Tháng đã chốt. GĐ4 **không sửa công thức lương** — chỉ chặn phiếu khi kỳ chưa
chốt và đối soát số công bằng máy.

## Global Constraints

- **TUYỆT ĐỐI KHÔNG** `bench --site miyano run-tests`. Chạy test qua harness rollback:
  `bash $SCRATCH/run_test.sh "<dotted.path>"` (đã dựng; `frappe.flags.in_test`, monkeypatch
  `frappe.db.commit`, savepoint mỗi test, rollback ở `finally`).
- Lint: ruff qua pre-commit — **tab**, **nháy kép**, dài dòng 110, py310.
- Chỉ `git add` đúng file mình đụng. Conventional Commits, scope `(hr)`.
- Payroll chỉ đọc `status` / `leave_type` / `half_day_status`. Field hiển thị **không được** làm đổi
  số lương.
- Method helper trên Document **không** đặt tên bắt đầu bằng `_` (bị `__getattr__` nuốt → trả None).
- Đổi fixtures phải sửa **cả** JSON **và** bộ lọc `fixtures` trong `hooks.py` (có test bắt).
- Mọi thao tác đụng site production (migrate, đổi Shift Type, bật cờ) → **hỏi trước**, không tự chạy.

---

## GĐ1 — Sinh công đúng

### T1: Fixtures — mã `1/2X`, bỏ `NN`, field cấu hình ca

**Files:**
- Modify: `hrms/fixtures/attendance_code.json` (bỏ `NN`, thêm `1/2X`)
- Modify: `hrms/fixtures/custom_field.json` (thêm 3 field Shift Type, bỏ 2)
- Modify: `hrms/hooks.py:446-450` (bộ lọc `fixtures` cho Shift Type)
- Test: `hrms/hr/doctype/attendance_code/test_attendance_code_fixtures.py`

**Interfaces — Produces:**
- Attendance Code `"1/2X"`: `category="Công"`, `work_fraction=0.5`, `is_paid=1`,
  `maps_to_status="Half Day"`, `leave_type=None`. Dùng bởi T2, T3, T4.
- Shift Type custom fields: `custom_flexible_shift` (Check, default 0),
  `custom_flex_band_minutes` (Int, default 180), `custom_min_work_hours` (Float, default 8).
  Dùng bởi T2.
- Bỏ: `Shift Type-custom_half_day_min_fraction`, `Shift Type-custom_half_day_grace_minutes`.

- [ ] **B1: Sửa test fixtures cho trạng thái mong muốn (đỏ)** — trong `test_attendance_code_fixtures.py`
  đổi dict mã: bỏ khoá `"NN"`, thêm `"1/2X": {"category": "Công", "work_fraction": 0.5, "is_paid": 1,
  "maps_to_status": "Half Day", "leave_type": None}`.
- [ ] **B2: Chạy → phải đỏ.** `bash run_test.sh "hrms.hr.doctype.attendance_code.test_attendance_code_fixtures"`
- [ ] **B3: Sửa 2 file fixtures + `hooks.py`** theo đúng bảng trên.
- [ ] **B4: Chạy lại → xanh**, kèm `hrms.tests.test_setup_vn_defaults` (bắt JSON ↔ hooks khớp nhau).
- [ ] **B5: Commit** `feat(hr): them ma cong 1/2X, bo NN, them field ca linh hoat`

### T2: Bộ phân loại — ca trượt + luật đủ giờ + chốt ngày nghỉ

**Files:**
- Modify: `hrms/hr/doctype/attendance/attendance.py:106-173` (`apply_vn_half_day_classifier`)
- Test: `hrms/hr/doctype/attendance/test_vn_half_day_classifier.py` (viết lại phần luật)

**Interfaces — Produces:** `apply_vn_half_day_classifier()` đặt `working_hours` (giờ net, 2 chữ số)
và `custom_attendance_code` ∈ {`X`, `1/2X`, `V`, None}. Dùng bởi T3, T4.

Thuật toán thay thế (giữ nguyên mọi chốt chặn cũ, **thêm** chốt ngày nghỉ):

```python
if is_holiday(get_holiday_list_for_employee(self.employee, raise_exception=False), self.attendance_date):
    return  # ngày nghỉ: không tự chấm mã (làm ngày nghỉ không bị quy thành V/nửa công)

offset = timedelta(0)
if cint(cfg.custom_flexible_shift):
    band = timedelta(minutes=cint(cfg.custom_flex_band_minutes) or self.VN_DEFAULT_FLEX_BAND_MINUTES)
    offset = max(-band, min(band, in_t - (midnight + cfg.start_time)))

w_start, w_end = midnight + cfg.start_time + offset, midnight + cfg.end_time + offset
l_start, l_end = midnight + lunch_start, midnight + lunch_end

net = overlap_hours(in_t, out_t, w_start, w_end) - overlap_hours(
    in_t, out_t, max(w_start, l_start), min(w_end, l_end)
)
self.working_hours = round(net, 2)

min_h = flt(cfg.custom_min_work_hours) or self.VN_DEFAULT_MIN_WORK_HOURS  # 8.0
if self.working_hours >= min_h:
    self.custom_attendance_code = "X"
elif self.working_hours > 0:
    self.custom_attendance_code = "1/2X"
else:
    self.custom_attendance_code = "V"
```

Hằng số lớp: bỏ `VN_DEFAULT_MIN_FRACTION` / `VN_DEFAULT_GRACE_MINUTES`, thêm
`VN_DEFAULT_FLEX_BAND_MINUTES = 180`, `VN_DEFAULT_MIN_WORK_HOURS = 8.0`.

- [ ] **B1: Viết lại test (đỏ)** trong `test_vn_half_day_classifier.py`:
  - `test_flex_late_in_late_out_is_full_day` — vào 11:00 ra 20:30 → `working_hours == 8.0`, mã `X`
  - `test_flex_late_in_short_by_an_hour_is_half` — vào 11:00 ra 19:30 → `7.0`, mã `1/2X`
    *(chính ca của user: giờ ghi nhận 7h chứ không phải 5h)*
  - `test_flex_early_in_early_out_is_full_day` — vào 06:30 ra 16:00 → `8.0`, mã `X`
  - `test_flex_band_clamps_beyond_three_hours` — vào 14:00 ra 22:00 → khung kẹp 11:00–20:30 →
    `working_hours == 7.0`, mã `1/2X`
  - `test_exact_minimum_hours_is_full_day` — vào 08:00 ra 17:30 → `8.0`, mã `X`
  - `test_below_minimum_is_half_day_code` — vào 08:00 ra 12:00 → `4.0`, mã `1/2X`
  - `test_no_worked_time_is_absent` — vào 12:15 ra 13:15 (trọn giờ trưa) → `0.0`, mã `V`
  - `test_holiday_is_never_auto_coded` — Attendance ngày T7 có in/out → mã **không** bị đặt
  - `test_flag_off_keeps_fixed_window` — tắt `custom_flexible_shift`: vào 11:00 ra 19:30 →
    `working_hours == 5.0` (khung cứng), mã `1/2X`
  - `test_half_day_code_docks_exactly_half` — sau `insert()`, `1/2X` cho
    `status == "Half Day"`, `leave_type is None`, `half_day_status == "Absent"`,
    `custom_work_credit == 0.5` *(khoá cả 3 chặng: cầu nối → check_leave_record → restore)*
  - Giữ nguyên: `test_manual_code_wins`, `test_gated_off_without_split_shift`,
    `test_a_full_day_of_leave_is_never_reclassified_from_the_clock`,
    `test_half_day_leave_plus_worked_half_keeps_leave_type`
  - Sửa `test_shift_type_config_fields_exist` sang 3 field mới
- [ ] **B2: Chạy → đỏ** (`hrms.hr.doctype.attendance.test_vn_half_day_classifier`)
- [ ] **B3: Cài đặt** theo khối code trên; import `is_holiday`, `get_holiday_list_for_employee`.
  Kèm `ShiftType.validate`: bật `custom_split_half_day` mà `custom_min_work_hours` ≤ 0 → throw
  (spec §4.1) — thêm test `test_split_shift_requires_min_work_hours` vào
  `hrms/hr/doctype/shift_type/test_shift_type.py`.
- [ ] **B4: Chạy → xanh** (cả `hrms.hr.doctype.shift_type.test_shift_type`).
- [ ] **B5: Commit** `feat(hr): ca truot theo gio vao + luat du gio X/1-2X/V, bo qua ngay nghi`

### T3: Report + Bảng Công Tháng theo mã mới

**Files:**
- Modify: `hrms/hr/report/monthly_attendance_report/monthly_attendance_report.py:425-432` (chú thích
  `NN` → `1/2X`; **logic giữ nguyên**)
- Test: `hrms/hr/report/monthly_attendance_report/test_monthly_attendance_report.py` (đang dùng `NN`)

**Interfaces — Consumes:** mã `1/2X` từ T1. **Produces:** `get_sheet_rows` trả `1/2X` với
`totals["Công"] += 0.5`, `totals[TOTAL_PAID] += 0.5`, `totals["Vắng"] += 0.5`. Dùng bởi T6, T12.

- [ ] **B1: Đổi test** `_mk(10, custom_attendance_code="NN")` → `"1/2X"`, kỳ vọng `day_10 == "1/2X"`,
  các tổng giữ nguyên con số cũ (0,5 Công + 0,5 Vắng) → chạy phải **đỏ** vì `NN` đã bị gỡ ở T1.
- [ ] **B2: Chạy → đỏ.**
- [ ] **B3: Sửa chú thích trong report; kiểm tra `day_state` vẫn trả `"half"` cho `work_fraction` 0,5.**
- [ ] **B4: Chạy → xanh** cả `test_monthly_attendance_report` lẫn
  `hrms.hr.doctype.monthly_attendance_sheet.test_monthly_attendance_sheet` (nếu có).
- [ ] **B5: Commit** `fix(hr): report/bang cong dung ma 1/2X thay NN`

### T4: Cổng bất biến lương GĐ1 *(CỔNG KÝ)*

**Files:**
- Create: `hrms/tests/test_flex_shift_payroll_gate.py`

**Interfaces — Consumes:** T2, T3.

- [ ] **B1: Viết test cổng** trên **dữ liệu thật T6/T7 của site** (chỉ đọc, chạy trong harness):
  - Nạp mọi Attendance có in/out của T6+T7, chạy lại `apply_vn_half_day_classifier` **trên bản sao
    trong bộ nhớ** (không lưu), so `status` / `leave_type` / `half_day_status` trước–sau.
  - Kỳ vọng: 206 ngày Present giữ nguyên `Present`; 6 ngày `1/2K` (4,0h) → `1/2X` nhưng vẫn
    `Half Day` + trừ 0,5 (leave_type đổi từ "Nghỉ không lương" sang None, `half_day_status` đổi
    `Present`→`Absent` — **cùng mức trừ 0,5**, một bên qua LWP, một bên qua half-absent).
  - Tính lại `payment_days` / `absent_days` / `leave_without_pay` của **12 phiếu lương T6/T7 đang
    submit** và khẳng định **bằng đúng giá trị đang lưu**.
- [ ] **B2: Chạy → phải xanh ngay** (nếu đỏ: luật mới đang ăn mất công của ai đó → dừng, báo user).
- [ ] **B3: Commit** `test(hr): cong bat bien luong cho ca truot + 1/2X tren du lieu that`

---

## GĐ2 — Soát công

### T5: Doctype `Attendance Correction Log`

**Files:**
- Create: `hrms/hr/doctype/attendance_correction_log/` (`.json`, `.py`, `__init__.py`, `test_*.py`)

**Interfaces — Produces:** doctype không submittable, `read_only` sau khi tạo. Field: `attendance`
(Link Attendance), `employee` (Link), `attendance_date` (Date), `old_code`/`new_code` (Data),
`old_status`/`new_status` (Data), `old_half_day_status`/`new_half_day_status` (Data),
`old_leave_type`/`new_leave_type` (Data), `reason` (Small Text, reqd), `corrected_by` (Link User),
`corrected_on` (Datetime). Dùng bởi T7.

- [ ] **B1: Test (đỏ)** — tạo log thiếu `reason` → `frappe.exceptions.MandatoryError`; tạo đủ → đọc lại
  đúng giá trị; sửa log đã tạo → chặn.
- [ ] **B2: Chạy → đỏ.** **B3: Tạo doctype.** **B4: Chạy → xanh.**
- [ ] **B5: Commit** `feat(hr): doctype nhat ky dieu chinh cong`

### T6: Cờ bất thường + lưới soát

**Files:**
- Create: `hrms/hr/attendance_review.py`
- Test: `hrms/hr/test_attendance_review.py`

**Interfaces — Produces:**
- `anomaly_flags(employee, date, att_row, checkin_count, is_holiday_day) -> list[str]` ⊂
  `{"SINGLE_PUNCH", "SHORT_HOURS", "NO_RECORD", "CHECKIN_ON_HOLIDAY", "ABSENT"}`
- `get_review_grid(filters) -> {"rows": [...], "flags": {employee: {day: [flag]}}}` — dựng trên
  `get_sheet_rows(filters)`, **không** dựng logic suy diễn thứ hai. Dùng bởi T8.

- [ ] **B1: Test (đỏ)** cho từng cờ, mỗi cờ một test; và `get_review_grid` trả đúng số hàng bằng
  `get_sheet_rows`.
- [ ] **B2: Chạy → đỏ.** **B3: Cài đặt.** **B4: Chạy → xanh.**
- [ ] **B5: Commit** `feat(hr): co bat thuong + luoi soat cong`

### T7: `apply_correction` — cửa ghi duy nhất

**Files:**
- Modify: `hrms/hr/attendance_review.py`
- Test: `hrms/hr/test_attendance_review.py`

**Interfaces — Produces:**
`apply_correction(attendance: str, code: str, reason: str) -> dict` (whitelist, quyền HR User/HR
Manager): nạp doc → đặt `custom_attendance_code` → chạy `apply_attendance_code_bridge()` →
`db_set` các field phái sinh → ghi `Attendance Correction Log`. `apply_corrections_bulk(rows)`.

- [ ] **B1: Test (đỏ)**: sửa `V` → `X` thì `status` thành `Present` và log ghi đủ cũ/mới; thiếu
  `reason` → throw; mã không tồn tại → throw; user không quyền → `PermissionError`;
  **payroll field đổi đúng theo mã** (bảng tham số hoá cho `X` / `1/2X` / `P`).
- [ ] **B2: Chạy → đỏ.** **B3: Cài đặt.** **B4: Chạy → xanh.**
- [ ] **B5: Commit** `feat(hr): api dieu chinh cong mot cua co ghi vet`

### T8: Trang soát công (desk page)

**Files:**
- Create: `hrms/hr/page/attendance_review/` (`.json`, `.js`)

- [ ] **B1: Dựng page** — bộ lọc tháng/năm/công ty/phòng ban; lưới NV × ngày; ô có cờ tô đỏ kèm
  tooltip tên cờ; click ô → chọn mã + nhập lý do; nút "Lưu tất cả" gọi `apply_corrections_bulk`.
- [ ] **B2: `bench build --app hrms`**, tự kiểm bằng ảnh chụp màn hình trên `http://miyano:8080`.
- [ ] **B3: Commit** `feat(hr): trang soat cong thang`

---

## GĐ3 — Chốt công có hiệu lực

### T9: Khoá kỳ theo bảng đã chốt

**Files:**
- Create: `hrms/hr/period_lock.py`
- Modify: `hrms/hooks.py` (`doc_events["Attendance"]`)
- Test: `hrms/hr/test_period_lock.py`

**Interfaces — Produces:** `is_period_locked(employee, date) -> str | None` (trả tên bảng chốt);
`guard_period_not_locked(doc, method=None)` — throw nếu bị khoá.

- [ ] **B1: Test (đỏ)**: có bảng chốt phủ ngày → sửa/huỷ Attendance bị chặn; huỷ bảng chốt → cho
  phép lại; bảng nháp (docstatus 0) → không khoá; ngày ngoài kỳ → không khoá; `apply_correction`
  trong kỳ khoá → throw.
- [ ] **B2: Chạy → đỏ.** **B3: Cài đặt + nối `doc_events`.** **B4: Chạy → xanh.**
- [ ] **B5: Commit** `feat(hr): chot cong khoa ky sua chua cham cong`

### T10: Bảng Công Tháng cảnh báo cờ tồn đọng

**Files:**
- Modify: `hrms/hr/doctype/monthly_attendance_sheet/monthly_attendance_sheet.py`
- Test: `hrms/hr/doctype/monthly_attendance_sheet/test_monthly_attendance_sheet.py`

- [ ] **B1: Test (đỏ)**: submit khi còn ô `NO_RECORD`/`ABSENT` → có `msgprint` cảnh báo, vẫn cho chốt.
- [ ] **B2–B4: đỏ → cài đặt → xanh.**
- [ ] **B5: Commit** `feat(hr): canh bao co bat thuong ton dong khi chot cong`

---

## GĐ4 — Cổng lương

### T11: Chặn phiếu lương khi kỳ chưa chốt

**Files:**
- Create: `hrms/vn_payroll/sheet_gate.py`
- Modify: `hrms/hooks.py` (`doc_events["Salary Slip"]["validate"]`)
- Test: `hrms/vn_payroll/test_sheet_gate.py`

**Interfaces — Produces:** `require_submitted_sheet(doc, method=None)`.

- [ ] **B1: Test (đỏ)**: kỳ chưa có bảng chốt → tạo Salary Slip bị throw; có bảng chốt phủ đủ → qua.
- [ ] **B2–B4: đỏ → cài đặt → xanh.**
- [ ] **B5: Commit** `feat(hr): chan phieu luong khi ky cham cong chua chot`

### T12: Đối soát bảng chốt ↔ phiếu lương *(CỔNG KÝ)*

**Files:**
- Modify: `hrms/vn_payroll/sheet_gate.py`
- Test: `hrms/vn_payroll/test_sheet_gate.py`

**Interfaces — Produces:** `reconcile_with_sheet(doc, method=None)` — so số công của NV trong bảng
chốt với `payment_days` / `absent_days`; lệch → throw kèm bảng so sánh.

- [ ] **B1: Cố định công thức bằng dữ liệu thật** — viết test chạy trên **12 phiếu lương T6/T7 đang
  submit** + 2 bảng chốt tương ứng; suy ra ánh xạ (`work_days` + phần có lương của các loại nghỉ ↔
  `payment_days`) sao cho **cả 12 phiếu khớp tuyệt đối**. Ghi công thức chốt được vào docstring.
- [ ] **B2: Test lệch**: sửa một ô trong bảng chốt (bản sao trong bộ nhớ) → đối soát phải throw.
- [ ] **B3: Chạy → xanh.**
- [ ] **B4: Commit** `feat(hr): doi soat phieu luong voi bang cong da chot`

---

## Sau khi code xong — các cổng deploy *(HỎI TRƯỚC, không tự chạy)*

1. `bench --site miyano migrate` (doctype + custom field mới).
2. Đồng bộ fixtures (bỏ `NN`, thêm `1/2X`, đổi field Shift Type).
3. `Ca Hành Chính`: `begin_check_in_before_shift_start_time` 60 → 180.
4. `Ca Hành Chính`: bật `custom_flexible_shift`, `custom_min_work_hours = 8`.
5. Bật khoá kỳ (T9) + cổng lương (T11/T12) sau khi đối soát chạy sạch trên T6/T7.
