# Hoàn thiện tích hợp lịch làm việc — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: `superpowers:subagent-driven-development` hoặc
> `superpowers:executing-plans`. Các bước dùng checkbox (`- [ ]`).

**Goal:** Đóng 6 điểm còn đọc thẳng `Holiday List` và 3 khoảng trống logic, để việc gỡ dòng nghỉ cuối
tuần khỏi `Holiday List` không còn là một bước nhảy vào chỗ tối.

**Architecture:** Không thêm khái niệm mới. Mọi thay đổi là chuyển câu hỏi về lịch sang
`hrms/hr/work_schedule.py`, cộng đúng **một** quy tắc mới ở lớp bảng công: *ngày ngoài lịch tuần chỉ
hiển thị ký hiệu, không vào cột tổng*.

**Tech Stack:** Frappe/ERPNext HRMS v15, Python, `hrms/translations/vi.csv`, rollback harness.

**Spec:** `docs/spec/work-schedule-integration-hardening.md`
(rà soát nguồn: `docs/audit-work-schedule-integration-2026-08-30.md`)

## Global Constraints

- **Quy ước đặt tên:** `scheduled_*` = theo lịch tuần **kể cả ngày lễ** (mẫu số lương);
  `working_*` = phải đi làm, đã trừ lễ. Không dùng lẫn.
- **Nhánh:** `feat/skip-attendance-diag`. Commit sau mỗi task, Conventional Commits scope `(hr)`.
- **Test:** rollback harness. **TUYỆT ĐỐI KHÔNG** `bench --site miyano run-tests`.
- Mọi test class kế thừa `PerTestRollback` **TRƯỚC** `FrappeTestCase`.
- Style: tab, nháy kép, dòng ≤ 110, ruff. Fieldname tiếng Anh, label tiếng Việt.
- `git add <paths>` đúng file của task — cây làm việc đang có phiên khác cùng sửa.
- **Không đụng** `api/roster.py` và `roster/` (ngoài phạm vi).
- **Đo baseline trước/sau bằng `git stash`** cho mọi task chạm file dùng chung — cách này đã bắt được
  3 hồi quy thật ở đợt trước, đừng bỏ.
- Mỗi task phải xanh ở **cả hai** trạng thái: `Holiday List` còn dòng `weekly_off` và đã gỡ.

### Lệnh chạy harness

```bash
cd /home/miyano/frappe-bench/sites && ../env/bin/python \
  /tmp/claude-1000/-home-miyano-frappe-bench-apps-hrms/<session>/scratchpad/harness.py <module...>
```

Harness: `frappe.flags.in_test = True`, `frappe.db.commit` → no-op, `finally: frappe.db.rollback()`,
kèm đếm số bản ghi trước/sau để phát hiện rò rỉ.

### Số liệu neo (site `miyano`, 2026-08-30)

| Mốc | Giá trị |
|---|---|
| Ngày T2–T6 của 07/2026 | 23 |
| `total_working_days` cả 6 phiếu 07/2026 | 23.0 |
| `VN Miyano 2026` | 104 dòng `weekly_off` + 12 dòng lễ |
| Test đang xanh | 406 |

---

### Task 1: Bộ dựng cảnh test dùng chung

**Files:**
- Create: `hrms/tests/work_calendar_fixture.py`
- Create: `hrms/tests/test_work_calendar_fixture.py`

**Interfaces:**
- Produces:
  - `build_scenario(year: int = 2027) -> frappe._dict` với các khoá:
    `company`, `shifts: {"office","six_day","all_week"}`, `employees: {"A","B","C","D","E"}`,
    `holiday_list`, `bridge_same_month: (off_date, make_up_date)`,
    `bridge_cross_month: (off_date, make_up_date)`
  - `set_company_weekdays(days: list[str])`, `set_calendar_days(rows)` — hai helper mà mọi bộ test
    hiện đang chép lại của nhau

- [ ] **Step 1: Viết test đỏ cho chính bộ dựng cảnh**

```python
def test_three_shifts_have_the_expected_weekly_patterns(self):
	s = build_scenario()
	self.assertEqual(len(shift_weekdays(s.shifts["office"])), 5)
	self.assertEqual(len(shift_weekdays(s.shifts["six_day"])), 6)
	self.assertEqual(len(shift_weekdays(s.shifts["all_week"])), 7)

def test_employee_c_falls_back_to_the_company_default(self):
	"""Tầng 3 của chuỗi phân giải phải có người thật đi qua, không chỉ có test riêng."""
	s = build_scenario()
	self.assertIsNone(frappe.db.get_value("Employee", s.employees["C"], "default_shift"))
	self.assertTrue(is_scheduled_day(s.employees["C"], monday_of(2027)))

def test_the_same_month_bridge_keeps_the_denominator(self):
	"""Nghỉ ghép + làm bù CÙNG tháng -> số ngày công của tháng đó không đổi."""
	s = build_scenario()
	off, make_up = s.bridge_same_month
	self.assertEqual(getdate(off).month, getdate(make_up).month)
	self.assertEqual(len(scheduled_days_between(s.employees["A"], *month_range(off))), baseline(off))

def test_the_cross_month_bridge_moves_two_denominators(self):
	"""Bù khác tháng -> tháng nghỉ giảm 1, tháng bù tăng 1. Đây là cái bẫy spec đã cảnh báo."""

def test_scenario_is_idempotent(self):
	"""Gọi hai lần không nhân đôi ca / nhân viên / dòng lịch."""
```

- [ ] **Step 2: Chạy harness → FAIL** (`ModuleNotFoundError: hrms.tests.work_calendar_fixture`)
- [ ] **Step 3: Cài đặt `build_scenario`** — 3 ca, 5 nhân viên, Holiday List 2027, 2 cặp nghỉ
      ghép/làm bù. Chỉ dựng dữ liệu, **không assert**. Idempotent (`frappe.db.exists` trước khi tạo).
- [ ] **Step 4: Chạy harness → PASS**
- [ ] **Step 5: Commit**

```bash
git add hrms/tests/work_calendar_fixture.py hrms/tests/test_work_calendar_fixture.py
git commit -m "test(hr): bo dung canh lich lam viec dung chung"
```

---

### Task 2: Ngày ngoài lịch có bản ghi — hiện ký hiệu, không cộng tổng ⚠️ CHẠM SỐ BẢNG CÔNG

> Task duy nhất của đợt này đụng tới con số. Kèm cổng đối soát bảng ↔ phiếu.

**Files:**
- Modify: `hrms/hr/report/monthly_attendance_report/monthly_attendance_report.py` (nhánh `if att:`)
- Modify: `hrms/hr/report/monthly_attendance_report/test_monthly_attendance_report.py`
- Create: `hrms/tests/test_manual_attendance_on_rest_day.py`

**Interfaces:**
- Consumes: `scheduled_days_map` (đã có `kind` cho từng ngày — dùng lại, không query thêm)
- Produces: không đổi chữ ký hàm nào; chỉ thêm điều kiện cộng tổng

- [ ] **Step 1: Viết test đỏ — cổng bảng ↔ phiếu**

```python
def test_a_manual_workday_on_a_saturday_does_not_break_the_reconciliation(self):
	"""Defect cụ thể: +1 vào Tổng công nhưng không vào payment_days -> reconcile_with_sheet
	chặn SẠCH mọi phiếu lương của tháng đó."""
	self.mark_present("2026-07-25")  # thứ Bảy
	sheet_total = paid_days_in_sheet(self.sheet_row())
	slip = self.payroll()
	self.assertEqual(sheet_total, slip["payment_days"], "bảng công và phiếu lương phải khớp")

def test_the_symbol_still_shows_on_a_rest_day(self):
	"""Không giấu ngày đó đi — HR phải thấy có người đi làm thứ Bảy."""
	self.mark_present("2026-07-25")
	self.assertEqual(self.sheet_row()["days"][25], "X")

def test_a_rest_day_record_adds_to_no_total(self):
	before = self.sheet_row()["totals"]
	self.mark_present("2026-07-25")
	self.assertEqual(self.sheet_row()["totals"], before)

def test_an_absent_row_on_a_rest_day_does_not_dock_anything(self):
	"""Chiều ngược lại: V ghi nhầm vào CN không được trừ Vắng."""

def test_a_make_up_day_counts_normally(self):
	"""Ngày Làm bù LÀ ngày làm việc -> vẫn cộng tổng như thường."""

def test_working_on_a_public_holiday_counts_normally(self):
	"""Ngày lễ nằm TRONG lịch tuần -> không thuộc quy tắc này."""
```

- [ ] **Step 2: Chạy harness → FAIL** (Tổng công lệch `payment_days` đúng 1.0)
- [ ] **Step 3: Cài đặt** — trong `get_sheet_rows`, nhánh `if att:` bọc phần cộng tổng bằng
      `if emp_kinds.get(d) != "rest":`. Ký hiệu vẫn gán như cũ. Thêm chú thích nêu **vì sao**:
      chưa có chính sách trả công ngày nghỉ, cộng vào Tổng công là hứa trả tiền mà phiếu không trả.
- [ ] **Step 4: Chạy harness → PASS**, gồm cả `test_monthly_attendance_sheet`, `test_attendance_review`
- [ ] **Step 5: Chạy cổng bất biến lương + đối soát 6 phiếu thật** → phải vẫn 0 lệch
- [ ] **Step 6: Thêm dòng chú giải màu** cho ô "đi làm ngoài lịch" (`attendance_legend`)
- [ ] **Step 7: Commit**

```bash
git add hrms/hr/report/monthly_attendance_report/ hrms/tests/test_manual_attendance_on_rest_day.py
git commit -m "feat(hr): ngay ngoai lich co ban ghi - hien ky hieu, khong cong tong"
```

---

### Task 3: PWA + calendar trên Desk đọc lịch tuần

**Files:**
- Modify: `hrms/api/__init__.py` (`get_holidays_for_calendar`, `get_holidays_for_employee`)
- Modify: `hrms/hr/doctype/attendance/attendance.py` (`add_holidays`)
- Test: `hrms/tests/test_work_calendar_integration.py` (tạo ở task này, dùng lại ở Task 4–5)

**Interfaces:**
- Consumes: `non_working_days_between`, `public_holidays_between`, `holiday_list_for`

- [ ] **Step 1: Viết test đỏ**

```python
def test_pwa_calendar_marks_weekends_after_the_migration(self):
	self.drop_weekly_off_rows()
	days = get_holidays_for_calendar(self.employee, "2026-07-01", "2026-07-31")
	self.assertIn(getdate("2026-07-25"), [getdate(d) for d in days])

def test_upcoming_holidays_still_lists_only_public_holidays(self):
	"""Ngữ nghĩa GIỮ NGUYÊN: đây là 'ngày lễ sắp tới', không phải 'ngày nghỉ sắp tới'."""

def test_upcoming_holidays_reads_the_list_of_the_right_year(self):
	"""Mỗi năm một list -> phải đi qua holiday_list_for, không phải link trên Employee."""

def test_desk_attendance_calendar_shows_rest_days(self):
	self.drop_weekly_off_rows()
	events = get_events("2026-07-01", "2026-07-31", employee=self.employee)
	self.assertTrue(any(getdate(e["attendance_date"]) == getdate("2026-07-25") for e in events))
```

- [ ] **Step 2: Chạy harness → FAIL**
- [ ] **Step 3: Cài đặt.** `get_holidays_for_calendar` → `non_working_days_between`.
      `add_holidays` → `non_working_days_between`, tiêu đề `Ngày nghỉ` hoặc `Nghỉ lễ` tuỳ loại.
      `get_holidays_for_employee` giữ ngữ nghĩa "chỉ ngày lễ" nhưng qua `holiday_list_for`.
- [ ] **Step 4: Chạy harness → PASS**; đo baseline `test_attendance` trước/sau bằng `git stash`
- [ ] **Step 5: Commit**

```bash
git add hrms/api/__init__.py hrms/hr/doctype/attendance/attendance.py hrms/tests/test_work_calendar_integration.py
git commit -m "feat(hr): lich cham cong PWA va Desk doc ngay nghi tu lich tuan"
```

---

### Task 4: Mark Attendance + upload template thôi gợi ý ngày nghỉ

**Files:**
- Modify: `hrms/hr/doctype/attendance/attendance.py` (`get_unmarked_days`)
- Modify: `hrms/hr/doctype/upload_attendance/upload_attendance.py`
- Test: `hrms/tests/test_work_calendar_integration.py` (mở rộng)

- [ ] **Step 1: Viết test đỏ**

```python
def test_unmarked_days_excludes_rest_days_after_the_migration(self):
	"""Không sửa thì hộp thoại Mark Attendance CHỦ ĐỘNG gợi ý T7/CN -> HR chấm nhầm."""
	self.drop_weekly_off_rows()
	days = get_unmarked_days(self.employee, "2026-07-01", "2026-07-31", exclude_holidays=1)
	self.assertNotIn(getdate("2026-07-25"), [getdate(d) for d in days])

def test_unmarked_days_includes_a_make_up_day(self):
	"""Ngày làm bù PHẢI xuất hiện — nó là ngày công, thiếu bản ghi là thiếu thật."""

def test_upload_template_marks_rest_days(self):
	...
```

- [ ] **Step 2: Chạy harness → FAIL**
- [ ] **Step 3: Cài đặt** — cả hai chỗ đổi `get_holiday_dates_for_employee` →
      `non_working_days_between`.
- [ ] **Step 4: Chạy harness → PASS**; baseline `test_attendance` + `test_upload_attendance`
- [ ] **Step 5: Commit**

```bash
git add hrms/hr/doctype/attendance/attendance.py hrms/hr/doctype/upload_attendance/ hrms/tests/
git commit -m "feat(hr): Mark Attendance va template upload bo qua ngay ngoai lich"
```

---

### Task 5: Báo cáo "đi làm ngày ngoài lịch" + lịch onboarding

**Files:**
- Modify: `hrms/hr/report/employees_working_on_a_holiday/employees_working_on_a_holiday.py`
- Modify: `hrms/hr/report/employees_working_on_a_holiday/employees_working_on_a_holiday.json` (nhãn)
- Modify: `hrms/controllers/employee_boarding_controller.py`
- Create: `hrms/hr/report/employees_working_on_a_holiday/test_employees_working_on_a_holiday.py`

**Interfaces:**
- Produces: report thêm cột `day_kind` (`Nghỉ tuần` / `Nghỉ lễ`)

- [ ] **Step 1: Viết test đỏ**

```python
def test_the_report_finds_someone_working_on_a_saturday(self):
	"""Sau di trú, nếu report chỉ quét ngày lễ thì nó mất đúng công dụng chính:
	trả lời 'ai đang đi làm cuối tuần'."""
	self.drop_weekly_off_rows()
	self.mark_present("2026-07-25")
	rows = execute({"month": 7, "year": 2026})[1]
	self.assertTrue(any(getdate(r[2]) == getdate("2026-07-25") for r in rows))

def test_the_report_labels_the_kind_of_day(self):
	...

def test_onboarding_tasks_skip_rest_days(self):
	...
```

- [ ] **Step 2: Chạy harness → FAIL**
- [ ] **Step 3: Cài đặt.** Report quét `non_working_days_between` thay vì dòng Holiday; thêm cột
      *Loại ngày*; đổi nhãn report sang "Đi làm ngày ngoài lịch" qua `vi.csv`.
      `employee_boarding_controller` đổi `is_holiday` → `not is_working_day`.
- [ ] **Step 4: Chạy harness → PASS**
- [ ] **Step 5: Commit**

```bash
git add hrms/hr/report/employees_working_on_a_holiday/ hrms/controllers/employee_boarding_controller.py hrms/translations/vi.csv
git commit -m "feat(hr): bao cao di lam ngay ngoai lich + lich onboarding theo lich tuan"
```

---

### Task 6: Hai nhãn nói đúng nghĩa + chốt kỳ đã khoá

**Files:**
- Modify: `hrms/hr/doctype/attendance_request/attendance_request.json`
- Modify: `hrms/hr/doctype/shift_type/shift_type.json`
- Modify: `hrms/translations/vi.csv`
- Modify: `hrms/hr/doctype/work_calendar_settings/work_calendar_settings.py`
- Modify: `hrms/hr/doctype/work_calendar_settings/test_work_calendar_settings.py`

- [ ] **Step 1: Viết test đỏ**

```python
def test_editing_a_locked_period_is_blocked_even_for_another_department(self):
	"""Chốt cũ đi vòng qua MỘT nhân viên đại diện nên lọt khi bảng đã chốt thuộc phòng ban khác.
	Lịch là chính sách toàn công ty -> câu hỏi đúng là 'có kỳ nào đã chốt phủ ngày này không'."""
	self.submit_sheet_for_department("Phòng khác", month=7)
	with self.assertRaises(frappe.ValidationError):
		self.set_calendar_days([(2026, "2026-07-25", "Làm bù", "Làm bù")])

def test_editing_an_open_period_is_allowed(self):
	...
```

- [ ] **Step 2: Chạy harness → FAIL**
- [ ] **Step 3: Cài đặt** — `validate_period_not_locked` hỏi thẳng `Monthly Attendance Sheet`
      `docstatus=1` phủ ngày bị sửa; đổi hai nhãn + thêm dòng dịch.
- [ ] **Step 4: Chạy harness → PASS**
- [ ] **Step 5: `bench --site miyano migrate`** để nhãn lên form (chỉ đổi label, không đổi schema)
- [ ] **Step 6: Commit**

```bash
git add hrms/hr/doctype/attendance_request/attendance_request.json hrms/hr/doctype/shift_type/shift_type.json \
        hrms/translations/vi.csv hrms/hr/doctype/work_calendar_settings/
git commit -m "feat(hr): sua hai nhan noi sai + chot ky da khoa hoi thang bang cong"
```

---

### Task 7: Ghi rõ vì sao nghỉ bù đang bất khả dụng

**Files:**
- Modify: `hrms/hr/doctype/compensatory_leave_request/compensatory_leave_request.py` (chỉ docstring)

- [ ] **Step 1: Viết docstring lớp** nêu **hai** lý do độc lập làm doctype này không dùng được
      (đòi Attendance `Present` trên ngày auto-attendance không tạo; đòi mọi ngày là dòng Holiday mà
      sau di trú T7/CN không còn là dòng Holiday), trỏ sang `docs/spec/overtime-registration.md`.
      Không sửa logic — quyết định 1 của spec.
- [ ] **Step 2: Commit**

```bash
git add hrms/hr/doctype/compensatory_leave_request/compensatory_leave_request.py
git commit -m "docs(hr): ghi ro vi sao Compensatory Leave Request dang bat kha dung"
```

---

### Task 8: Ma trận tích hợp + nghiệm thu

**Files:**
- Modify: `hrms/tests/test_work_calendar_integration.py` (hoàn thiện ma trận)
- Modify: `docs/spec/work-schedule-integration-hardening.md` (tick + STATUS)
- Modify: `docs/tasks/plan-work-schedule-integration-hardening.md` (tick)

- [ ] **Step 1: Ma trận trên bộ dựng cảnh** — 8 nhóm của tài liệu rà soát, mỗi khẳng định chạy ở
      **cả hai** trạng thái lịch: phân giải · chấm công · đơn nghỉ · check-in · bảng công · lương ·
      tích hợp cũ · ghi tay.
- [ ] **Step 2: Chạy TOÀN BỘ** bộ test của nhánh (mốc hiện tại: 406 xanh) + các module mới.
- [ ] **Step 3: Kiểm tiêu chí "một cửa"**

```bash
grep -rn "is_holiday\|get_holiday_dates_between\|get_holiday_list_for_employee" hrms/ --include=*.py \
  | grep -v __pycache__ | grep -v "hrms/hr/work_schedule.py" | grep -v "/test_" | grep -v "hrms/patches/"
```

Kết quả phải khớp đúng danh sách ngoại lệ của spec §2 + quyết định 4 (`api/roster.py`,
`hr/utils.py`, `compensatory_leave_request`, `daily_work_summary_group`, `payroll_period`,
`employee_benefit_application`, `monthly_attendance_sheet`, `leave_application` phần calendar).
Có mục nào ngoài danh sách → hoặc sửa, hoặc ghi lý do vào spec. Không im lặng bỏ qua.

- [ ] **Step 4: Đối soát 6 phiếu lương thật** ở cả hai trạng thái lịch → 0 lệch.
- [ ] **Step 5: Kiểm rò rỉ dữ liệu** — đếm lại Attendance / Holiday / Salary Slip / Shift Type.
- [ ] **Step 6: Kiểm bằng mắt trên Desk + PWA** — bảng công 07/2026; hộp thoại Mark Attendance;
      *Upcoming Holidays*; báo cáo đi làm ngoài lịch.
- [ ] **Step 7: Cập nhật spec + plan, commit.**

---

## Thứ tự và vì sao

```
1  bộ dựng cảnh (thuần thêm mới)
   ↓
2 ⚠️ ngày ngoài lịch không cộng tổng   <- task DUY NHẤT chạm số, đi sớm để mọi task sau
   ↓                                      chạy trên hành vi đã đúng
3  PWA + calendar Desk        ─┐
4  Mark Attendance + upload    │  ba task độc lập nhau, đổi thứ tự thoải mái
5  report + onboarding        ─┘
   ↓
6  nhãn + chốt kỳ khoá
7  docstring nghỉ bù
   ↓
8  ma trận + nghiệm thu
```

Task 2 đi trước vì nó sửa **hành vi**, còn 3–5 chỉ sửa **nơi đọc dữ liệu**. Làm ngược lại thì ma trận
ở Task 8 phải chạy hai lần trên hai hành vi khác nhau.

Cả 8 task đều **không** chạm patch di trú — nó vẫn nằm ngoài `patches.txt`, chờ ký duyệt riêng.
