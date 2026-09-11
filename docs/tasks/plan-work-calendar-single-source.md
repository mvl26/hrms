# Work Calendar là nguồn duy nhất — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: `superpowers:subagent-driven-development` hoặc
> `superpowers:executing-plans`. Các bước dùng checkbox (`- [ ]`).

**Goal:** Gỡ hết các cửa khai lịch cũ để chỉ còn **một** nguồn, và cho `work_schedule` tính được
**giờ làm việc** chứ không chỉ **ngày làm việc**.

**Architecture:** Không thêm khái niệm mới. Ba việc: (a) khoá `Holiday List` thành bảng chiếu chỉ
đọc, (b) chuyển giờ định mức từ hằng số `8.0` sang suy từ ca qua `work_schedule`, (c) chạy nốt patch
di trú đã chờ sẵn để việc tách thành sự thật trên dữ liệu.

**Tech Stack:** Frappe/ERPNext HRMS v15, Python, Property Setter qua `fixtures`, `vi.csv`,
rollback harness.

**Spec:** `docs/spec/work-calendar-single-source.md`

## Global Constraints

- **Quy ước đặt tên:** `scheduled_*` = theo lịch tuần **kể cả ngày lễ** (mẫu số lương);
  `working_*` = **phải đi làm**, đã trừ lễ. Không dùng lẫn. Giờ định mức dùng `working_*`.
- **Nhánh:** `feat/skip-attendance-diag`. Commit sau mỗi task, Conventional Commits scope `(hr)`.
- **Test:** rollback harness. **TUYỆT ĐỐI KHÔNG** `bench --site miyano run-tests`.
- Mọi test class kế thừa `PerTestRollback` **TRƯỚC** `FrappeTestCase`.
- Dùng lại `hrms/tests/work_calendar_fixture.build_scenario()` — không dựng cảnh mới.
- **Đo baseline trước/sau bằng `git stash`** cho mọi task chạm file dùng chung.
- Style: tab, nháy kép, dòng ≤ 110, ruff. `git add <paths>`, không bao giờ `git add -A`.
- **Cổng ký duyệt (STOP):** Task 6 (chạy patch di trú — xoá dữ liệu, không `git revert` được).

### Lệnh chạy harness

```bash
cd /home/miyano/frappe-bench/sites && ../env/bin/python \
  <scratchpad>/harness.py <module...>
```

Harness: `frappe.flags.in_test = True`, `frappe.db.commit` → no-op, `finally: frappe.db.rollback()`,
kèm đếm bản ghi trước/sau để phát hiện rò rỉ.

### Số liệu neo (site `miyano`, 2026-09-11)

| Mốc | Giá trị |
|---|---|
| `VN Miyano 2026` | **104 dòng `weekly_off` + 12 dòng lễ** (patch chưa chạy) |
| `Ca Hành Chính` | 8:00–17:30, trưa 12:00–13:30 → **8,0h/ngày** |
| Ngày T2–T6 của 07/2026 | 23 → định mức đúng phải là **184h** |
| `total_working_days` cả 6 phiếu 07/2026 | 23.0 |
| Test đang xanh | 442 |

---

### Task 1: `work_schedule` biết tính GIỜ

**Files:**
- Modify: `hrms/hr/work_schedule.py`
- Modify: `hrms/hr/tests/test_work_schedule.py`

**Interfaces:**
- Produces:
  - `working_days_between(employee, start, end) -> set[date]` — ngày **phải đi làm** (scheduled − lễ)
  - `shift_hours_per_day(shift: str | None) -> float` — `(end − start − nghỉ trưa)` của ca
  - `half_day_window(employee, date, period: str) -> tuple | None` — `("morning"|"afternoon")`

- [ ] **Step 1: Viết test đỏ**

```python
def test_working_days_excludes_public_holidays(self):
	"""scheduled_* KỂ CẢ lễ (mẫu số lương); working_* thì KHÔNG (kỳ vọng có mặt)."""
	scheduled = scheduled_days_between(self.employee, "2027-06-01", "2027-06-30")
	working = working_days_between(self.employee, "2027-06-01", "2027-06-30")
	self.assertIn(getdate(COMPANY_HOLIDAY), scheduled)
	self.assertNotIn(getdate(COMPANY_HOLIDAY), working)
	self.assertEqual(len(working), len(scheduled) - 1)

def test_shift_hours_subtract_the_lunch_window(self):
	"""8:00-17:30 trừ trưa 1,5h = 8,0h. Đây là con số mà hằng số 8.0 đang ăn may."""
	self.assertEqual(shift_hours_per_day(self.scenario.shifts["office"]), 8.0)

def test_shift_hours_follow_the_shift_not_a_constant(self):
	"""Ca 8:00-17:00 trừ trưa 1,5h = 7,5h — chính là ca mà hardcode 8.0 nói dối."""
	frappe.db.set_value("Shift Type", shift, "end_time", "17:0:0")
	self.assertEqual(shift_hours_per_day(shift), 7.5)

def test_shift_hours_fall_back_when_the_lunch_window_is_nonsense(self):
	"""Shift Type mới bị Frappe điền GIỜ HIỆN TẠI vào hai ô nghỉ trưa -> khung rộng 0 giây.
	Phải rơi về khung mặc định, nếu không ca đó tính dư 1,5h mỗi ngày."""

def test_half_day_window_splits_at_lunch(self):
	morning = half_day_window(self.employee, TUESDAY, "morning")
	afternoon = half_day_window(self.employee, TUESDAY, "afternoon")
	self.assertEqual(morning[1].hour, 12)
	self.assertEqual(afternoon[0].hour, 13)

def test_half_day_window_is_none_on_a_rest_day(self):
	self.assertIsNone(half_day_window(self.employee, SATURDAY, "morning"))
```

- [ ] **Step 2: Chạy harness → FAIL** (`ImportError: cannot import name 'working_days_between'`)
- [ ] **Step 3: Cài đặt.** `working_days_between` = `scheduled_days_between − public_holidays_between`.
      `shift_hours_per_day` dùng lại `resolve_lunch_window` của `vn_day_classifier` (đừng viết lại
      lớp phòng thủ khung trưa rác). `half_day_window` trả `None` khi `is_rest_day`.
- [ ] **Step 4: Chạy harness → PASS**
- [ ] **Step 5: Commit**

```bash
git add hrms/hr/work_schedule.py hrms/hr/tests/test_work_schedule.py
git commit -m "feat(hr): work_schedule tinh duoc gio lam viec cua ca"
```

---

### Task 2: Giờ định mức suy từ ca, thôi đọc Holiday List ⚠️ CHẠM KPI

> Điểm thứ **9** còn sót — hai đợt rà trước đều lọt. Sau di trú, không sửa chỗ này thì định mức
> tháng 7/2026 nhảy 184h → 240h và **toàn công ty bị báo thiếu giờ**.

**Files:**
- Modify: `hrms/hr/working_hours.py` (`get_standard_hours*`, `_count_holidays_in_month`)
- Modify: `hrms/hr/report/monthly_attendance_sheet/monthly_attendance_sheet.py`
  (`set_standard_and_variance`)
- Create: `hrms/hr/tests/test_standard_hours.py`

**Interfaces:**
- Consumes: `working_days_between`, `shift_hours_per_day` (Task 1)
- Produces: `standard_hours_between(employee, start, end, exclude_leave=True) -> float`

- [ ] **Step 1: Viết test đỏ**

```python
def test_standard_hours_for_july_2027(self):
	"""23 ngày phải đi làm x 8,0h = 184h — KHÔNG phải 30 x 8."""

def test_standard_hours_follow_the_shift(self):
	"""Đổi ca sang 8:00-17:00 -> định mức giảm đúng 0,5h mỗi ngày làm việc."""

def test_standard_hours_do_not_count_public_holidays(self):
	"""Ngày lễ có lương nhưng KHÔNG kỳ vọng có mặt -> không vào định mức giờ."""

def test_standard_hours_count_a_make_up_day(self):
	"""Ngày làm bù là ngày phải đi làm -> vào định mức."""

def test_standard_hours_subtract_leave_days(self):
	"""Nghỉ phép 5 ngày -> định mức giảm đúng 5 x giờ ca.
	Không trừ thì người tuân thủ đúng quy định luôn nằm trong danh sách thiếu giờ."""

def test_standard_hours_survive_the_migration(self):
	"""Chốt chặn cho điểm thứ 9: gỡ dòng nghỉ cuối tuần xong, định mức KHÔNG được đổi."""
	before = standard_hours_between(emp, start, end)
	self.drop_weekly_off_rows()
	self.assertEqual(standard_hours_between(emp, start, end), before)

def test_employee_on_a_six_day_shift_has_more_standard_hours(self):
	"""Hai người cùng Holiday List, khác ca -> khác định mức. Chứng minh định mức đi theo CA."""
```

- [ ] **Step 2: Chạy harness → FAIL**
- [ ] **Step 3: Cài đặt.** `get_standard_hours_map` gọi `standard_hours_between`; xoá
      `_count_holidays_in_month`; `STANDARD_HOURS_PER_DAY` chỉ còn là fallback khi ca không khai giờ,
      docstring nói rõ nó là fallback **chứ không phải chính sách**.
      `set_standard_and_variance` nhận `employee` thay vì `holidays`.
- [ ] **Step 4: Chạy harness → PASS**; baseline `test_working_hours` +
      `test_monthly_attendance_sheet` trước/sau bằng `git stash`
- [ ] **Step 5: Chạy cổng bất biến lương + đối soát 6 phiếu thật** → phải vẫn 0 lệch
- [ ] **Step 6: Commit**

```bash
git add hrms/hr/working_hours.py hrms/hr/report/monthly_attendance_sheet/ hrms/hr/tests/test_standard_hours.py
git commit -m "feat(hr): gio dinh muc suy tu ca va tru ngay nghi, thoi hardcode 8h"
```

---

### Task 3: Khoá `Holiday List` thành bảng chiếu chỉ đọc

**Files:**
- Create: `hrms/hr/holiday_list_guard.py`
- Modify: `hrms/hooks.py` (`doc_events["Holiday List"]` + fixtures filter)
- Create/Modify: `hrms/fixtures/property_setter.json`
- Modify: `hrms/setup_vn_holiday.py` (bật cờ quanh `doc.save()`)
- Create: `hrms/tests/test_work_calendar_single_source.py`

**Interfaces:**
- Produces: `guard_generated_only(doc, method=None)`; `frappe.flags.generating_work_calendar`

- [ ] **Step 1: Viết test đỏ**

```python
def test_saving_a_holiday_list_by_hand_is_blocked(self):
	"""Dòng chữ 'đừng sửa tay' là lời khuyên, không phải rào chắn — lịch sử đã chứng minh:
	17/07/2026 từng bị nhập tay, kèm nguyên HTML của trình soạn thảo."""
	hl = frappe.get_doc("Holiday List", self.scenario.holiday_list)
	hl.append("holidays", {"holiday_date": "2027-03-10", "description": "tay"})
	with self.assertRaises(frappe.ValidationError):
		hl.save()

def test_the_generator_can_still_save(self):
	create_vn_holiday_list(2027, self.company, name=self.scenario.holiday_list)  # không throw

def test_a_list_nobody_uses_is_not_blocked(self):
	"""Chặn danh sách rác của test chỉ làm phiền, không bảo vệ gì."""

def test_weekly_off_fields_are_hidden(self):
	for field in ("weekly_off", "get_weekly_off_dates", "clear_table"):
		self.assertTrue(is_hidden("Holiday List", field), field)

def test_shift_type_holiday_list_is_hidden(self):
	"""Field chết: không dòng code nào đọc nó, để lại là bẫy."""
	self.assertTrue(is_hidden("Shift Type", "holiday_list"))
```

- [ ] **Step 2: Chạy harness → FAIL**
- [ ] **Step 3: Cài đặt.** `guard_generated_only` chặn khi `not frappe.flags.get(
      "generating_work_calendar")` **và** danh sách đang được Company/Employee trỏ tới.
      Property Setter ẩn 6 field lối cũ của Holiday List + `Shift Type.holiday_list`.
      Generator bọc `doc.save()` trong `try/finally` bật-tắt cờ.
- [ ] **Step 4: Chạy harness → PASS**
- [ ] **Step 5: `bench --site miyano migrate`** để nạp Property Setter; mở form kiểm bằng mắt
- [ ] **Step 6: Commit**

```bash
git add hrms/hr/holiday_list_guard.py hrms/hooks.py hrms/fixtures/property_setter.json \
        hrms/setup_vn_holiday.py hrms/tests/test_work_calendar_single_source.py
git commit -m "feat(hr): Holiday List thanh bang chieu chi doc, chan sua tay"
```

---

### Task 4: Nói rõ hai tầng lịch tuần

**Files:**
- Modify: `hrms/fixtures/custom_field.json` (nhãn + mô tả `custom_working_days`)
- Modify: `hrms/hr/doctype/work_calendar_settings/work_calendar_settings.json`
- Modify: `hrms/translations/vi.csv`

- [ ] **Step 1: Đổi nhãn + mô tả** theo bảng §3 của spec — ca **thắng**, công ty là **lưới an toàn**.
      Cập nhật khối HTML giới thiệu trên Work Calendar Settings cho khớp mô hình mới.
- [ ] **Step 2: `bench --site miyano migrate`**, kiểm bằng mắt trên hai form
- [ ] **Step 3: Chạy `test_setup_vn_defaults`** (nó gác đồng bộ fixtures ↔ bộ lọc `hooks.py`)
- [ ] **Step 4: Commit**

```bash
git add hrms/fixtures/custom_field.json hrms/hr/doctype/work_calendar_settings/ hrms/translations/vi.csv
git commit -m "feat(hr): noi ro hai tang lich tuan tren giao dien"
```

---

### Task 5: Report "Lịch hiệu lực của nhân viên"

**Files:**
- Create: `hrms/hr/report/employee_work_calendar/` (`__init__.py`, `.py`, `.json`, `.js`,
  `test_employee_work_calendar.py`)
- Modify: `hrms/translations/vi.csv`

**Interfaces:**
- Consumes: `scheduled_days_map`, `working_days_between`, `shift_hours_per_day`,
  `standard_hours_between`, `employee_shift`
- Produces: `execute(filters) -> (columns, data)`; cột **Nguồn lịch tuần** = `Ca` /
  `Mặc định công ty`

- [ ] **Step 1: Viết test đỏ**

```python
def test_reports_the_shift_and_where_the_weekly_pattern_came_from(self):
	"""Cột này chính là thứ làm tan cảm giác 'trùng setting': nhìn một dòng là biết
	người này theo lịch nào và VÌ SAO."""
	row = self.row_for("A")
	self.assertEqual(row["schedule_source"], "Ca")
	self.assertEqual(self.row_for("C")["schedule_source"], "Mặc định công ty")

def test_counts_working_days_rest_days_holidays_and_make_up_days(self):
	...

def test_standard_hours_match_the_shift(self):
	self.assertEqual(self.row_for("A")["standard_hours"], 23 * 8.0)

def test_a_six_day_shift_shows_more_working_days(self):
	...
```

- [ ] **Step 2: Chạy harness → FAIL**
- [ ] **Step 3: Cài đặt** report (Script Report). **Tên report ASCII** — bẫy đã ghi:
      Script Report tên có dấu thì không chạy và test không bắt. Nhãn VN qua `vi.csv`.
- [ ] **Step 4: Chạy harness → PASS**; thêm link vào workspace HR
- [ ] **Step 5: Commit**

```bash
git add hrms/hr/report/employee_work_calendar/ hrms/translations/vi.csv
git commit -m "feat(hr): report lich hieu luc cua nhan vien"
```

---

### Task 6: Chạy patch di trú ⚠️ CỔNG KÝ DUYỆT

> Patch `remove_weekly_off_from_holiday_list` đã viết, 8 test xanh, đã diễn tập trên dữ liệu thật
> (0 lệch) từ 2026-08-30 — chỉ còn thiếu một dòng trong `patches.txt` và một cái gật.
> **Không `git revert` được.**

**Files:**
- Modify: `hrms/patches.txt` (+1 dòng ở `[post_model_sync]`)

- [ ] **Step 1: Diễn tập lại trên dữ liệu HÔM NAY** (savepoint, rollback) — dữ liệu đã đổi 12 ngày
      so với lần trước, không được dùng lại kết quả cũ. In bảng: số dòng trước/sau, 4 con số của mọi
      Salary Slip, **và giờ định mức trước/sau** (mới thêm ở Task 2).
- [ ] **Step 2: STOP — trình bảng đối soát, xin ký duyệt.**
- [ ] **Step 3: Nối `patches.txt` + `bench --site miyano migrate`**
- [ ] **Step 4: Đối soát ngay sau khi chạy** — 6 phiếu lương, giờ định mức, bảng công 07/2026.
- [ ] **Step 5: Commit**

```bash
git add hrms/patches.txt
git commit -m "feat(hr): noi patch go dong nghi cuoi tuan vao patches.txt"
```

---

### Task 7: Nghiệm thu

**Files:**
- Modify: `docs/spec/work-calendar-single-source.md` (tick + STATUS)
- Modify: `docs/tasks/plan-work-calendar-single-source.md` (tick)

- [ ] **Step 1: Chạy TOÀN BỘ** bộ test của nhánh (mốc hiện tại: 442 xanh) + các module mới.
- [ ] **Step 2: Kiểm tiêu chí "một cửa"**

```bash
grep -rn "is_holiday\|get_holiday_dates_between\|get_holiday_list_for_employee\|_count_holidays" \
  hrms/ --include=*.py | grep -v __pycache__ | grep -v "hrms/hr/work_schedule.py" \
  | grep -v "/test_" | grep -v "hrms/patches/" | grep -v "^hrms/tests/"
```

Kết quả phải khớp đúng danh sách ngoại lệ đã ghi (`api/roster.py`, `hr/utils.py`,
`compensatory_leave_request`, `daily_work_summary_group`, `payroll_period`,
`employee_benefit_application`, `employee_reminders`, `employee_boarding_controller` nhánh
không-có-nhân-viên). Mục nào ngoài danh sách → hoặc sửa, hoặc ghi lý do vào spec.

- [ ] **Step 3: Đối soát 6 phiếu lương thật** → 0 lệch.
- [ ] **Step 4: Kiểm rò rỉ dữ liệu** — đếm lại Attendance / Holiday / Salary Slip / Shift Type.
- [ ] **Step 5: Kiểm bằng mắt trên Desk** — Holiday List không còn nút tự sinh; Shift Type không còn
      ô Holiday List; Work Calendar Settings nói rõ hai tầng; report lịch hiệu lực; KPI giờ.
- [ ] **Step 6: Cập nhật spec + plan, commit.**

---

## Thứ tự và vì sao

```
1  work_schedule biết tính giờ        (thuần thêm mới, chưa ai dùng)
   ↓
2 ⚠️ giờ định mức suy từ ca            <- điểm thứ 9 còn sót; PHẢI xong TRƯỚC Task 6,
   ↓                                     nếu không chạy patch là KPI giờ vỡ ngay
3  khoá Holiday List chỉ đọc          ─┐
4  nhãn hai tầng                       │  ba task độc lập, đổi thứ tự thoải mái
5  report lịch hiệu lực               ─┘
   ↓
6 ⚠️ chạy patch di trú (ký duyệt)      <- bước làm việc "tách" thành sự thật trên dữ liệu
   ↓
7  nghiệm thu
```

**Task 2 phải xong trước Task 6.** Đây là ràng buộc cứng, không phải sở thích: patch gỡ 104 dòng
nghỉ cuối tuần, mà `get_standard_hours_map` đang đếm ngày nghỉ bằng cách đọc thẳng `Holiday List` —
chạy patch trước là định mức tháng 7/2026 nhảy từ 184h lên 240h và toàn công ty bị báo thiếu giờ.

Task 3 nên xong trước Task 6 nữa: khoá cửa cũ **trước** khi dọn nhà thì không ai vô tình dựng lại
104 dòng vừa xoá.
