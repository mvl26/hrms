# Tách lịch làm việc khỏi lịch nghỉ lễ — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: dùng `superpowers:subagent-driven-development`
> (khuyến nghị) hoặc `superpowers:executing-plans` để thực thi từng task. Các bước dùng checkbox
> (`- [ ]`) để theo dõi.

**Goal:** `Holiday List` chỉ còn chứa ngày nghỉ lễ; ngày làm việc trong tuần (T2–T6) và khung giờ
hành chính chuyển sang `Shift Type`; ngày/giờ ngoài lịch được suy ra chứ không lưu, không sinh công,
và log chấm công rơi vào đó được đánh dấu sẵn làm nền cho OT.

**Architecture:** Một module miền duy nhất `hrms/hr/work_schedule.py` trả lời mọi câu hỏi về lịch;
mọi consumer gọi qua nó thay vì gọi thẳng `is_holiday()`. Mẫu số lương được **đặt tuyệt đối** từ lịch
tuần thay vì cộng/trừ delta, nên con số đúng không phụ thuộc vào việc `Holiday List` còn hay đã hết
dòng cuối tuần — **mọi task đều bất biến ở CẢ HAI trạng thái lịch**, và patch di trú (Task 10) trở
thành no-op về mặt số học.

**Tech Stack:** Frappe/ERPNext HRMS v15, Python (`frappe.qb`, `frappe.get_all`), fixtures JSON,
custom field qua fixtures, patch qua `hrms/patches.txt`.

**Spec:** `docs/spec/work-schedule-and-holiday-separation.md`

## Global Constraints

- **Quy ước đặt tên (một phần của spec):** `scheduled_*` = theo lịch tuần, **kể cả ngày lễ** — dùng
  cho **mẫu số lương**. `working_*` = **phải đi làm**, tức đã trừ lễ. Không được dùng lẫn.
- **Nhánh:** `feat/skip-attendance-diag`. Commit sau mỗi task, Conventional Commits scope `(hr)`.
- **Test:** rollback harness trong console. **TUYỆT ĐỐI KHÔNG** `bench --site miyano run-tests`.
- **Mọi test class** phải kế thừa `PerTestRollback` **TRƯỚC** `FrappeTestCase`.
- Style: tab, nháy kép, dòng ≤ 110, ruff qua pre-commit. Fieldname tiếng Anh, label tiếng Việt.
- **Không** đặt tên method có tiền tố `_` trên `Document` (bị `__getattr__` nuốt thành `None`).
- `git add <paths>` đúng file của task — **không bao giờ** `git add -A`.
- **Cổng ký duyệt (STOP, hỏi trước):** Task 7 (sửa cầu nối lương) và Task 10 (patch di trú).
- Mỗi task phải **xanh ở cả hai trạng thái**: `Holiday List` còn dòng `weekly_off` và đã gỡ.

### Lệnh chạy harness (dùng cho mọi task)

```bash
cd /home/miyano/frappe-bench && bench --site miyano console
```

```python
import unittest, frappe
frappe.flags.in_test = True
frappe.db.commit = lambda *a, **k: None          # chặn commit rò ra dữ liệu thật
MODULES = ["hrms.hr.tests.test_work_schedule"]   # đổi theo task
suite = unittest.TestLoader().loadTestsFromNames(MODULES)
try:
    unittest.TextTestRunner(verbosity=2).run(suite)
finally:
    frappe.db.rollback()
```

Cô lập từng test do `PerTestRollback` lo (savepoint ở `_callSetUp`, rollback ở cleanup).

### Số liệu neo (đọc thật trên `miyano` ngày 2026-08-28)

| Mốc | Giá trị |
|---|---|
| Ngày T2–T6 của 07/2026 | **23** |
| `total_working_days` của cả 6 Salary Slip 07/2026 | **23.0** |
| `payment_days` | đúng bằng `23 − leave_without_pay − absent_days` (19.5 / 22.0 / 22.5) |
| `VN Miyano 2026` | 104 dòng `weekly_off=1` + 12 dòng lễ |
| Nhân viên | 6/6 có `default_shift = Ca Hành Chính`, ghim `holiday_list = VN Miyano 2026` |

`23` xuất hiện ở cả hai vế là bằng chứng công thức mới tái tạo đúng con số cũ **theo cấu tạo**:
`31 − 8 ngày cuối tuần = 23`, và hôm nay `31 − (8 + 1 lễ 17/07) + 1 lễ = 23`.

---

### Task 1: Khai báo lịch tuần + lõi luật thuần

**Files:**
- Create: `hrms/hr/work_schedule.py`
- Create: `hrms/hr/tests/test_work_schedule.py`
- Modify: `hrms/fixtures/custom_field.json` (+1 field cho `Shift Type`)
- Modify: `hrms/hr/doctype/work_calendar_settings/work_calendar_settings.json` (+ `default_working_days`)

**Interfaces:**
- Produces:
  - `WEEKDAY_INDEX: dict[str, int]` — `"Monday" → 0` … `"Sunday" → 6`, khớp `date.weekday()`
  - `weekday_set(day_names) -> frozenset[int]`
  - `dates_in_range(start, end) -> Iterator[date]`
  - `scheduled_dates(weekdays: frozenset[int], start, end) -> set[date]`

> **KHÔNG** bỏ `weekly_off_days` khỏi Work Calendar Settings ở task này — `generate_holiday_list`
> vẫn đang gọi `get_weekly_off_days()`. Field đó bị gỡ ở Task 8, khi generator thôi dùng.

- [ ] **Step 1: Viết test đỏ**

```python
# hrms/hr/tests/test_work_schedule.py
# Copyright (c) 2026, Miyano Việt Nam.
"""Lõi luật lịch tuần — thuần, không chạm DB."""

import unittest
from datetime import date

from hrms.hr.work_schedule import dates_in_range, scheduled_dates, weekday_set

MON_TO_FRI = frozenset({0, 1, 2, 3, 4})


class TestWorkScheduleRules(unittest.TestCase):
	def test_weekday_set_maps_english_day_names(self):
		self.assertEqual(weekday_set(["Monday", "Friday"]), frozenset({0, 4}))

	def test_weekday_set_ignores_unknown_names(self):
		"""Tên rác bị bỏ qua chứ không nổ: một dòng hỏng không được làm chết cả kỳ lương."""
		self.assertEqual(weekday_set(["Monday", "", None, "Xyz"]), frozenset({0}))

	def test_dates_in_range_is_inclusive_both_ends(self):
		days = list(dates_in_range("2026-07-01", "2026-07-03"))
		self.assertEqual(days, [date(2026, 7, 1), date(2026, 7, 2), date(2026, 7, 3)])

	def test_july_2026_has_23_scheduled_days(self):
		"""Con số neo: 6 phiếu lương 07/2026 đang có total_working_days = 23.0."""
		got = scheduled_dates(MON_TO_FRI, "2026-07-01", "2026-07-31")
		self.assertEqual(len(got), 23)

	def test_scheduled_dates_excludes_weekend(self):
		got = scheduled_dates(MON_TO_FRI, "2026-07-25", "2026-07-26")  # T7 + CN
		self.assertEqual(got, set())

	def test_every_month_of_2026(self):
		expected = [22, 20, 22, 22, 21, 22, 23, 21, 22, 22, 21, 23]
		for month, want in enumerate(expected, start=1):
			last = 31 if month in (1, 3, 5, 7, 8, 10, 12) else (28 if month == 2 else 30)
			got = scheduled_dates(MON_TO_FRI, f"2026-{month:02d}-01", f"2026-{month:02d}-{last}")
			self.assertEqual(len(got), want, f"tháng {month}")

	def test_empty_weekday_set_yields_no_scheduled_day(self):
		self.assertEqual(scheduled_dates(frozenset(), "2026-07-01", "2026-07-31"), set())
```

- [ ] **Step 2: Chạy harness → FAIL** (`ModuleNotFoundError: hrms.hr.work_schedule`)

- [ ] **Step 3: Cài đặt tối thiểu**

```python
# hrms/hr/work_schedule.py
# Copyright (c) 2026, Miyano Việt Nam.
"""Nguồn duy nhất trả lời "ngày này có phải ngày làm việc không".

Trước module này, cuối tuần và ngày nghỉ lễ là cùng một thứ trong dữ liệu (đều là dòng Holiday,
phân biệt bằng cờ `weekly_off`), nên không nơi nào hỏi được lịch tuần mà không đi vòng qua bảng
ngày lễ, và khái niệm "trong ca / ngoài ca" — nền của OT — không tồn tại.

QUY ƯỚC ĐẶT TÊN, đọc kỹ trước khi dùng:
  scheduled_* = theo LỊCH TUẦN, KỂ CẢ ngày lễ  -> đây là MẪU SỐ LƯƠNG
  working_*   = PHẢI ĐI LÀM, tức đã trừ ngày lễ
Ngày lễ hưởng nguyên lương (Đ.112 BLLĐ; HR chốt 2026-08-04: ngày công chuẩn = ngày đi làm + nghỉ lễ
+ nghỉ có lương) nên nó nằm TRONG mẫu số. Dùng nhầm `working_*` cho mẫu số sẽ hụt đúng bằng số ngày
lễ của tháng — lỗi im lặng, chỉ lộ ở tháng có lễ.
"""

from collections.abc import Iterator
from datetime import date, timedelta

from frappe.utils import getdate

# date.weekday(): 0 = thứ Hai … 6 = Chủ nhật. Tên thứ khớp child doctype `Assignment Rule Day`.
WEEKDAY_INDEX = {
	"Monday": 0,
	"Tuesday": 1,
	"Wednesday": 2,
	"Thursday": 3,
	"Friday": 4,
	"Saturday": 5,
	"Sunday": 6,
}


def weekday_set(day_names) -> frozenset[int]:
	"""Tên thứ → chỉ số `date.weekday()`.

	Bỏ qua tên không nhận ra thay vì nổ: một dòng cấu hình hỏng không được phép làm chết cả kỳ
	lương. Cấu hình rỗng hoàn toàn thì được chuỗi phân giải ở tầng trên xử lý (Task 2).
	"""
	return frozenset(WEEKDAY_INDEX[d] for d in (day_names or []) if d in WEEKDAY_INDEX)


def dates_in_range(start, end) -> Iterator[date]:
	"""Mọi ngày từ `start` tới `end`, bao gồm cả hai đầu."""
	current, last = getdate(start), getdate(end)
	while current <= last:
		yield current
		current += timedelta(days=1)


def scheduled_dates(weekdays: frozenset[int], start, end) -> set[date]:
	"""Ngày nằm trong lịch tuần. KHÔNG xét ngày lễ — thuần luật, không chạm DB."""
	return {d for d in dates_in_range(start, end) if d.weekday() in weekdays}
```

- [ ] **Step 4: Chạy harness → PASS** (7 test)

- [ ] **Step 5: Thêm custom field lịch tuần cho `Shift Type`**

Thêm vào `hrms/fixtures/custom_field.json` (giữ nguyên lối 5 field tách buổi đã có):

```json
{
 "doctype": "Custom Field",
 "dt": "Shift Type",
 "fieldname": "custom_working_days",
 "fieldtype": "Table",
 "label": "Ngày làm việc trong tuần",
 "options": "Assignment Rule Day",
 "insert_after": "custom_min_work_hours",
 "description": "Những thứ trong tuần ca này đi làm. Bỏ trống = dùng mặc định ở Cấu hình lịch làm việc."
}
```

Thêm `default_working_days` vào `work_calendar_settings.json` (Table → `Assignment Rule Day`,
label *"Ngày làm việc mặc định của công ty"*, đặt ở section mới *"Lịch làm việc mặc định"*), và bổ
sung `Shift Type` vào bộ lọc `fixtures` trong `hooks.py` nếu chưa có `custom_working_days`.

- [ ] **Step 6: `bench --site miyano migrate`, kiểm field đã lên form Shift Type**

- [ ] **Step 6b: Khai lịch tuần thật** — `Ca Hành Chính` = T2–T6, và `default_working_days` của Work
      Calendar Settings = T2–T6 (lưới an toàn). Đây là **điều kiện tiên quyết của Task 10**: patch di
      trú sẽ tự abort nếu thiếu.

- [ ] **Step 7: Commit**

```bash
git add hrms/hr/work_schedule.py hrms/hr/tests/test_work_schedule.py \
        hrms/fixtures/custom_field.json hrms/hooks.py \
        hrms/hr/doctype/work_calendar_settings/work_calendar_settings.json
git commit -m "feat(hr): khai bao lich tuan tren Shift Type + loi luat thuan"
```

---

### Task 2: Chuỗi phân giải — ca của nhân viên + Holiday List theo ngày

**Files:**
- Modify: `hrms/hr/work_schedule.py`
- Modify: `hrms/hr/tests/test_work_schedule.py`

**Interfaces:**
- Consumes: `weekday_set`, `scheduled_dates` (Task 1);
  `erpnext.setup.doctype.employee.employee.get_holiday_list_for_employee`;
  `hrms.hr.doctype.shift_assignment.shift_assignment.get_employee_shift`
- Produces:
  - `WorkScheduleNotConfigured(frappe.ValidationError)`
  - `shift_weekdays(shift: str | None) -> frozenset[int] | None` — `None` = ca chưa khai
  - `employee_weekdays(employee: str, date) -> frozenset[int]` — nổ `WorkScheduleNotConfigured`
    nếu cả 3 tầng đều trống
  - `calendar_exceptions(year: int) -> dict[date, str]` — `{ngày: day_type}` từ Work Calendar Settings
  - `holiday_list_for(employee: str, date) -> str | None`
  - `is_scheduled_day(employee, date) -> bool`
  - `is_rest_day(employee, date) -> bool`
  - `is_public_holiday(employee, date) -> bool`
  - `is_working_day(employee, date) -> bool`

- [ ] **Step 1: Viết test đỏ** — thêm class `TestWorkScheduleResolution(PerTestRollback, FrappeTestCase)`:

```python
def test_shift_assignment_wins_over_default_shift(self):
	"""Ca gán theo tháng phải thắng default_shift — nếu không, đổi ca giữa năm là sai mẫu số."""

def test_falls_back_to_default_shift_when_no_assignment(self):
	...

def test_falls_back_to_company_default_when_employee_has_no_shift(self):
	"""NV chưa phân ca vẫn phải có lịch — lưới an toàn ở Work Calendar Settings."""

def test_raises_when_nothing_is_configured(self):
	"""Tầng cuối là CHỦ Ý: nổ lỗi rõ ràng, không âm thầm coi mọi ngày là ngày làm việc."""
	with self.assertRaises(WorkScheduleNotConfigured):
		employee_weekdays(self.employee, "2026-07-01")

def test_saturday_is_rest_day_not_public_holiday(self):
	self.assertTrue(is_rest_day(self.employee, "2026-07-25"))       # T7
	self.assertFalse(is_public_holiday(self.employee, "2026-07-25"))

def test_public_holiday_on_a_scheduled_day(self):
	self.assertTrue(is_public_holiday(self.employee, "2026-07-17"))  # lễ công ty, thứ Sáu
	self.assertTrue(is_scheduled_day(self.employee, "2026-07-17"))
	self.assertFalse(is_working_day(self.employee, "2026-07-17"))    # lễ thì không phải đi làm

def test_holiday_row_on_a_rest_day_is_not_a_public_holiday(self):
	"""PHÒNG THỦ: một dòng lễ nhập nhầm vào Chủ nhật không được cộng khống ngày công."""

def test_holiday_list_resolved_by_date_not_by_employee_link(self):
	"""Mỗi năm một list: đứng ở 2027 hỏi ngày 12/2026 vẫn phải ra lịch 2026."""

def test_make_up_workday_turns_a_saturday_into_a_scheduled_day(self):
	"""Làm bù: T7 29/08/2026 thành ngày công. Thiếu bảng ngoại lệ thì spec này là bước lùi
	so với mô hình cũ (xoá dòng weekly_off của đúng ngày đó là làm được)."""
	self.add_calendar_day(2026, "2026-08-29", "Làm bù", "Làm bù Quốc khánh")
	self.assertTrue(is_scheduled_day(self.employee, "2026-08-29"))
	self.assertFalse(is_rest_day(self.employee, "2026-08-29"))
	self.assertTrue(is_working_day(self.employee, "2026-08-29"))

def test_bridge_day_off_is_a_public_holiday(self):
	"""Nghỉ ghép khai loại "Nghỉ lễ" -> xuống Holiday List -> NL, có lương."""

def test_exception_of_another_year_is_ignored(self):
	"""Lọc theo năm: dòng 2027 không được ảnh hưởng ngày của 2026."""
```

- [ ] **Step 2: Chạy harness → FAIL** (`ImportError: cannot import name 'is_working_day'`)

- [ ] **Step 3: Cài đặt**

```python
import frappe
from frappe import _


class WorkScheduleNotConfigured(frappe.ValidationError):
	"""Không suy được lịch tuần. Nổ thay vì đoán — đoán sai là sai mẫu số lương cả tháng."""


def shift_weekdays(shift: str | None) -> frozenset[int] | None:
	"""Lịch tuần của một ca, hoặc None nếu ca chưa khai (để tầng trên rơi tiếp)."""
	if not shift:
		return None
	rows = frappe.get_all(
		"Assignment Rule Day",
		filters={"parent": shift, "parenttype": "Shift Type", "parentfield": "custom_working_days"},
		pluck="day",
	)
	return weekday_set(rows) or None


def company_default_weekdays() -> frozenset[int] | None:
	settings = frappe.get_cached_doc("Work Calendar Settings")
	return weekday_set(row.day for row in settings.default_working_days) or None


def employee_weekdays(employee: str, date) -> frozenset[int]:
	"""Shift Assignment của ngày đó → Employee.default_shift → mặc định công ty → LỖI."""
	from hrms.hr.doctype.shift_assignment.shift_assignment import get_employee_shift

	shift = (get_employee_shift(employee, getdate(date), consider_default_shift=True) or {}).get(
		"shift_type"
	)
	days = shift_weekdays(shift.name if hasattr(shift, "name") else shift)
	if days is None:
		days = company_default_weekdays()
	if days is None:
		frappe.throw(
			_("Chưa khai ngày làm việc trong tuần cho {0} (ca hoặc Cấu hình lịch làm việc).").format(
				employee
			),
			exc=WorkScheduleNotConfigured,
		)
	return days


def holiday_list_for(employee: str, date) -> str | None:
	"""Holiday List phủ ĐÚNG ngày được hỏi.

	`get_holiday_list_for_employee` của ERPNext mù ngày tháng — trả về đúng một list bất kể hỏi về
	ngày nào. Với mô hình mỗi năm một list, đứng ở 2027 mà xem lại tháng 12/2026 sẽ tra nhầm lịch
	2027 và mất sạch ký hiệu NL. Nên chọn theo khoảng ngày trước, chỉ rơi về hành vi cũ khi không
	list nào phủ.
	"""
	from erpnext.setup.doctype.employee.employee import get_holiday_list_for_employee

	date = getdate(date)
	company = frappe.get_cached_value("Employee", employee, "company")
	covering = frappe.get_all(
		"Holiday List",
		filters={"from_date": ["<=", date], "to_date": [">=", date]},
		pluck="name",
		order_by="from_date desc",
		limit=1,
	)
	if covering:
		return covering[0]
	return get_holiday_list_for_employee(employee, raise_exception=False)


def calendar_exceptions(year: int) -> dict:
	"""{ngày: day_type} của một năm — ngày KHÁC với mẫu tuần (nghỉ ghép / làm bù).

	`custom_working_days` là mẫu tuần lặp lại vô hạn, không nói được "riêng thứ Bảy 29/08 thì đi
	làm". Mô hình cũ nói được (xoá dòng weekly_off của đúng ngày đó) nên thiếu bảng này là một
	bước lùi về khả năng biểu đạt. Xem spec §3b.
	"""
	settings = frappe.get_cached_doc("Work Calendar Settings")
	return {
		getdate(row.holiday_date): row.day_type
		for row in settings.calendar_days
		if row.holiday_date and int(row.year or 0) == int(year)
	}


def is_scheduled_day(employee: str, date) -> bool:
	"""Nằm trong lịch tuần. KHÔNG xét ngày lễ.

	= (thứ có trong mẫu tuần) XOR (ngày có dòng "Làm bù"). Ngoại lệ chỉ cần biết ở ĐÂY; sáu nơi
	tiêu thụ đúng theo mà không phải sửa dòng nào — đó là lợi tức của thiết kế một cửa.
	"""
	date = getdate(date)
	if calendar_exceptions(date.year).get(date) == "Làm bù":
		return True
	return date.weekday() in employee_weekdays(employee, date)


def is_rest_day(employee: str, date) -> bool:
	"""Ngoài lịch tuần (T7/CN) → bảng công hiện `-`."""
	return not is_scheduled_day(employee, date)


def is_public_holiday(employee: str, date) -> bool:
	"""Ngày nghỉ lễ → bảng công hiện `NL`, có lương.

	Giao thêm với lịch tuần: dòng lễ rơi ngoài lịch tuần KHÔNG được tính, nếu không một dòng nhập
	nhầm vào Chủ nhật sẽ cộng khống một ngày công vào lương.
	"""
	if not is_scheduled_day(employee, date):
		return False
	holiday_list = holiday_list_for(employee, date)
	if not holiday_list:
		return False
	return bool(
		frappe.db.exists(
			"Holiday",
			{"parent": holiday_list, "holiday_date": getdate(date), "weekly_off": 0},
		)
	)


def is_working_day(employee: str, date) -> bool:
	"""PHẢI ĐI LÀM = trong lịch tuần VÀ không phải ngày lễ."""
	return is_scheduled_day(employee, date) and not is_public_holiday(employee, date)
```

> `weekly_off: 0` trong filter là bắc cầu cho giai đoạn chuyển tiếp: trước Task 10 danh sách vẫn còn
> 104 dòng cuối tuần, và chúng **không** được lẫn vào ngày lễ. Sau Task 10 điều kiện này vô hại.

- [ ] **Step 4: Chạy harness → PASS**

- [ ] **Step 5: Commit**

```bash
git add hrms/hr/work_schedule.py hrms/hr/tests/test_work_schedule.py
git commit -m "feat(hr): chuoi phan giai lich tuan + Holiday List theo ngay"
```

---

### Task 3: API theo khoảng + bulk + khung giờ ca

**Files:**
- Modify: `hrms/hr/work_schedule.py`
- Modify: `hrms/hr/tests/test_work_schedule.py`

**Interfaces:**
- Produces:
  - `scheduled_days_between(employee, start, end) -> set[date]` — **MẪU SỐ LƯƠNG**, kể cả lễ
  - `public_holidays_between(employee, start, end) -> set[date]`
  - `non_working_days_between(employee, start, end) -> set[date]` — nghỉ tuần ∪ lễ, đã khử trùng
  - `scheduled_days_map(employees: list[str], start, end) -> dict[str, dict[int, str]]` —
    `{employee: {day_of_month: "scheduled" | "rest" | "holiday"}}`
  - `shift_window(employee, date) -> tuple[datetime, datetime] | None`

- [ ] **Step 1: Viết test đỏ**

```python
def test_scheduled_days_between_includes_public_holidays(self):
	"""MẪU SỐ: 07/2026 = 23 ngày, ngày lễ 17/07 NẰM TRONG đó."""
	got = scheduled_days_between(self.employee, "2026-07-01", "2026-07-31")
	self.assertEqual(len(got), 23)
	self.assertIn(getdate("2026-07-17"), got)

def test_non_working_days_is_union_without_double_counting(self):
	"""Hợp của nghỉ tuần và lễ; ngày lễ rơi vào T7 chỉ được đếm một lần."""

def test_scheduled_days_map_matches_single_day_api(self):
	"""Bulk và API lẻ không được phép nói khác nhau — đây là bẫy N+1 kinh điển."""

def test_shift_window_returns_none_on_a_rest_day(self):
	self.assertIsNone(shift_window(self.employee, "2026-07-25"))
```

- [ ] **Step 2: Chạy harness → FAIL**

- [ ] **Step 3: Cài đặt**

```python
def scheduled_days_between(employee: str, start, end) -> set[date]:
	"""MẪU SỐ LƯƠNG: ngày theo lịch tuần trong khoảng, KỂ CẢ ngày lễ.

	Ngày lễ hưởng nguyên lương nên nó nằm TRONG mẫu số. Đừng đổi thành `working_*` — sẽ hụt đúng
	bằng số ngày lễ của tháng, và chỉ lộ ở tháng có lễ.
	"""
	return scheduled_dates(employee_weekdays(employee, start), start, end)


def public_holidays_between(employee: str, start, end) -> set[date]:
	"""Ngày lễ trong khoảng, ĐÃ giao với lịch tuần (phòng dòng lễ nhập nhầm vào T7/CN)."""
	holiday_list = holiday_list_for(employee, start)
	if not holiday_list:
		return set()
	rows = frappe.get_all(
		"Holiday",
		filters={
			"parent": holiday_list,
			"parenttype": "Holiday List",
			"holiday_date": ["between", [getdate(start), getdate(end)]],
			"weekly_off": 0,
		},
		pluck="holiday_date",
	)
	return {getdate(d) for d in rows} & scheduled_days_between(employee, start, end)


def non_working_days_between(employee: str, start, end) -> set[date]:
	"""Ngày KHÔNG phải đi làm = ngoài lịch tuần ∪ ngày lễ. Đã khử trùng.

	Là tập thay thế cho `get_holiday_dates_between` ở mọi chỗ tiêu thụ. Trong giai đoạn chuyển tiếp
	(Holiday List còn 104 dòng cuối tuần) tập này bằng ĐÚNG tập cũ, nên các task đổi consumer đều
	bất biến — đó là lý do thứ tự deploy không quan trọng.
	"""
	all_days = set(dates_in_range(start, end))
	return (all_days - scheduled_days_between(employee, start, end)) | public_holidays_between(
		employee, start, end
	)
```

`scheduled_days_map` gom nhân viên theo (ca, khoảng) để chỉ tra `employee_weekdays` một lần cho mỗi
nhóm và một query `Holiday` cho mỗi Holiday List — **không** vòng lặp gọi API lẻ (bẫy N+1: bảng công
là 31 ngày × N nhân viên). `shift_window` đọc `start_time`/`end_time` của ca đã phân giải, trả `None`
khi `is_rest_day`.

- [ ] **Step 4: Chạy harness → PASS**

- [ ] **Step 5: Commit**

```bash
git add hrms/hr/work_schedule.py hrms/hr/tests/test_work_schedule.py
git commit -m "feat(hr): API lich theo khoang + bulk + khung gio ca"
```

---

### Task 4: Báo cáo & Bảng Công Tháng đọc nguồn mới

**Files:**
- Modify: `hrms/hr/report/monthly_attendance_report/monthly_attendance_report.py:348-369` (`get_holidays`)
- Modify: `hrms/hr/report/monthly_attendance_report/monthly_attendance_report.py:469,481-525`
  (nhánh dựng ô trong `get_sheet_rows`)
- Test: `hrms/hr/report/monthly_attendance_report/test_monthly_attendance_report.py` (mở rộng)

**Interfaces:**
- Consumes: `scheduled_days_map` (Task 3)
- Produces: `get_holidays` bị thay bằng `get_day_kinds(employees, start, end) -> dict[str, dict[int, str]]`
  với giá trị `"rest" | "holiday" | "scheduled"`. `MARKER_WEEKLY_OFF` / `MARKER_HOLIDAY` giữ nguyên.

Đây là **task chỉ đọc** — không ghi gì, nên an toàn để đi trước và làm chỗ dựng dàn giáo kiểm chứng.

- [ ] **Step 1: Viết test đỏ — bất biến hiển thị**

```python
def test_markers_identical_before_and_after_switching_source(self):
	"""Ô của cả tháng 07/2026 phải y hệt khi đọc từ cờ weekly_off và khi đọc từ lịch tuần.
	Đây là test bắc cầu: nó chạy được vì lúc này Holiday List VẪN còn dòng cuối tuần."""

def test_rest_day_shows_dash_and_holiday_shows_NL(self):
	rows = get_sheet_rows({"year": 2026, "month": 7, "company": self.company})
	days = rows[0]["days"]
	self.assertEqual(days[25], "-")    # T7
	self.assertEqual(days[17], "NL")   # lễ công ty, thứ Sáu

def test_public_holiday_still_counts_into_tong_cong(self):
	"""Quyết định HR 2026-08-04: ngày lễ vào Tổng công. Không được đổi."""
```

- [ ] **Step 2: Chạy harness → FAIL**
- [ ] **Step 3: Thay `get_holidays` bằng `get_day_kinds`; nhánh `elif day in emp_hol` đổi thành
      `elif kind == "rest"` / `elif kind == "holiday"`.** Ký hiệu, màu, `day_state`, cột tổng,
      `TOTAL_PAID` **không đổi một chữ**.
- [ ] **Step 4: Chạy harness → PASS** (gồm cả bộ test màu `test_day_state_*` đang có)
- [ ] **Step 5: Chạy lại `hrms.hr.tests.test_attendance_review` + test Bảng Công Tháng** — hai nơi
      này đọc lại `get_sheet_rows`, phải xanh không sửa gì.
- [ ] **Step 6: Commit**

```bash
git add hrms/hr/report/monthly_attendance_report/
git commit -m "feat(hr): bang cong doc lich tuan va ngay le tu hai nguon tach bach"
```

---

### Task 5: Đường sinh công hỏi lịch tuần

**Files:**
- Modify: `hrms/hr/doctype/shift_type/shift_type.py:281-289` (`get_dates_for_attendance`)
- Modify: `hrms/hr/doctype/attendance/attendance.py:148-151` (`falls_on_holiday` → `falls_on_non_working_day`)
- Modify: `hrms/hr/attendance_exempt.py:63-69,154` (`is_exempt_working_day`, `plan_for_day`)
- Modify: `hrms/hr/doctype/business_trip/business_trip.py:91-99`
- Modify: `hrms/hr/doctype/attendance_request/attendance_request.py:140-141,224`
- Test: `hrms/hr/doctype/shift_type/test_shift_type.py`, `hrms/hr/tests/test_attendance_exempt.py`,
  `hrms/hr/doctype/attendance/test_attendance.py` (mở rộng)

**Interfaces:**
- Consumes: `non_working_days_between`, `is_working_day` (Task 2–3)

- [ ] **Step 1: Viết test đỏ**

```python
def test_no_absent_marked_on_saturday_or_sunday(self):
	"""Cốt tử: không sửa chỗ này thì sau Task 10 sẽ chấm V mọi thứ Bảy."""
	dates = shift.get_dates_for_attendance(self.employee)
	self.assertNotIn(getdate("2026-07-25"), [getdate(d) for d in dates])

def test_exempt_employee_gets_no_X_on_rest_day(self):
	"""Miễn chấm công vẫn nghỉ T7/CN — cả công ty đều nghỉ."""

def test_business_trip_skips_rest_days(self):
	...

def test_attendance_request_rejects_rest_day_without_include_holidays(self):
	...
```

- [ ] **Step 2: Chạy harness → FAIL**
- [ ] **Step 3: Thay lần lượt 5 chỗ.** `get_holiday_dates_between(holiday_list, …)` →
      `non_working_days_between(employee, …)`; `is_holiday(employee, d, …)` → `not is_working_day(employee, d)`.
      Đổi tên `falls_on_holiday` → `falls_on_non_working_day` **và** cập nhật chỗ gọi ở
      `attendance.py:176`.
- [ ] **Step 4: Chạy harness → PASS** (gồm 29 test regression `test_shift_type` đang có)
- [ ] **Step 5: Commit**

```bash
git add hrms/hr/doctype/shift_type/ hrms/hr/doctype/attendance/ hrms/hr/attendance_exempt.py \
        hrms/hr/doctype/business_trip/ hrms/hr/doctype/attendance_request/ hrms/hr/tests/
git commit -m "feat(hr): duong sinh cong hoi lich tuan thay vi hoi Holiday List"
```

---

### Task 6: Đơn nghỉ đếm ngày theo lịch tuần

**Files:**
- Modify: `hrms/hr/doctype/leave_application/leave_application.py:1249-1261` (`get_holidays`)
- Modify: `hrms/hr/doctype/leave_application/leave_application.py:251-270` (sinh Attendance)
- Test: `hrms/hr/doctype/leave_application/test_leave_application.py` (mở rộng)

**Interfaces:**
- Consumes: `non_working_days_between` (Task 3)

- [ ] **Step 1: Viết test đỏ**

```python
def test_leave_spanning_a_weekend_still_costs_two_days(self):
	"""T6 2026-07-24 → T2 2026-07-27 = 2 ngày phép, không phải 4.
	Không sửa get_holidays thì sau Task 10 nhân viên bị ăn oan 2 ngày."""
	self.assertEqual(
		get_number_of_leave_days(self.employee, "Nghỉ phép năm", "2026-07-24", "2026-07-27"), 2
	)

def test_no_attendance_created_on_rest_days_inside_a_leave(self):
	...
```

- [ ] **Step 2: Chạy harness → FAIL** (hiện đang trả 2 nhờ dòng `weekly_off`; test thứ hai bắt
      đúng đường mới) — nếu cả hai cùng xanh sẵn thì **vẫn giữ test**: nó là lưới chặn cho Task 10.
- [ ] **Step 3: `get_holidays` trả `len(non_working_days_between(employee, from_date, to_date))`;
      `holiday_dates` trong `create_or_update_attendance` đổi sang cùng nguồn.**
- [ ] **Step 4: Chạy harness → PASS**
- [ ] **Step 5: Commit**

```bash
git add hrms/hr/doctype/leave_application/
git commit -m "feat(hr): don nghi dem ngay theo lich tuan"
```

---

### Task 7: Payroll — đặt mẫu số tuyệt đối ⚠️ CỔNG KÝ DUYỆT

> **STOP.** Đây là sửa **cầu nối lương**. Trình bày kết quả cổng bất biến và **xin ký duyệt** trước
> khi commit. Không tự ý đi tiếp.

**Files:**
- Modify: `hrms/vn_payroll/salary_slip_hook.py:146-211` (`add_paid_holidays` → `set_working_days`)
- Modify: `hrms/hooks.py:143-149` (thứ tự hook `Salary Slip.validate`)
- Create: `hrms/payroll/doctype/salary_slip/test_working_days_invariance.py`

**Interfaces:**
- Consumes: `scheduled_days_between` (Task 3)
- Produces: `set_working_days(doc, method=None) -> None` — thay chỗ `add_paid_holidays` ở **vị trí
  thứ nhất**, vẫn chạy **trước** `sheet_gate.gate` rồi mới tới `apply_mvl`.

- [ ] **Step 1: Viết CỔNG bất biến (test đỏ)**

```python
# hrms/payroll/doctype/salary_slip/test_working_days_invariance.py
# Copyright (c) 2026, Miyano Việt Nam.
"""CỔNG: mẫu số lương phải giống hệt trước và sau khi tách lịch.

Chạy ở CẢ HAI trạng thái Holiday List (còn dòng cuối tuần / đã gỡ). Vì `set_working_days` ĐẶT
tuyệt đối chứ không cộng trừ delta, hai trạng thái phải cho cùng con số — nếu lệch thì hoặc lịch
tuần khai sai, hoặc công thức sai. KHÔNG được nới lỏng test này để "cho xanh".
"""

FIELDS = ("total_working_days", "payment_days", "absent_days", "leave_without_pay")


class TestWorkingDaysInvariance(PerTestRollback, FrappeTestCase):
	def numbers(self, slip):
		slip.run_method("validate")
		return {f: flt(slip.get(f)) for f in FIELDS}

	def test_july_2026_denominator_is_23(self):
		"""Neo bằng dữ liệu thật: cả 6 phiếu 07/2026 trên site đang là 23.0."""
		self.assertEqual(self.numbers(self.slip)["total_working_days"], 23.0)

	def test_identical_with_and_without_weekly_off_rows(self):
		before = self.numbers(self.make_slip())
		self.drop_weekly_off_rows()          # mô phỏng Task 10 trong savepoint
		after = self.numbers(self.make_slip())
		self.assertEqual(before, after)

	def test_payment_days_formula(self):
		"""23 − lwp − absent_days, khớp đúng 3 giá trị thật: 19.5 / 22.0 / 22.5."""

	# 8 ca biên bắt buộc, mỗi ca một test:
	# kỳ thường · kỳ có ngày lễ · có ngày vắng · có nửa ngày · vào làm giữa kỳ ·
	# nghỉ việc giữa kỳ · kỳ toàn ngày nghỉ (tránh chia 0) · lwp ≥ base (nhánh clamp = 0)
```

- [ ] **Step 2: Chạy harness → FAIL**

- [ ] **Step 3: Cài đặt `set_working_days`**

```python
def set_working_days(doc, method=None) -> None:
	"""ĐẶT mẫu số lương từ lịch tuần. Thay hẳn `add_paid_holidays`.

	Vì sao ĐẶT TUYỆT ĐỐI thay vì cộng/trừ delta: con số đúng không được phụ thuộc vào việc
	Holiday List còn hay đã hết dòng cuối tuần. Nhờ vậy mỗi bước triển khai độc lập, deploy lệch
	nhau không sao, và patch di trú trở thành no-op về số học.

	`days − (cuối tuần ∪ lễ) + lễ` rút gọn đúng bằng `số ngày theo lịch tuần`, nên đặt thẳng con số
	đó vừa ngắn hơn vừa nói đúng ý định thay vì hai phép trừ–cộng triệt tiêu nhau. Ngày lễ NẰM
	TRONG mẫu số (Đ.112; HR chốt 2026-08-04) → dùng `scheduled_*`, KHÔNG phải `working_*`.

	Chạy cho MỌI Salary Slip — bỏ điều kiện `salary_type_of` của `add_paid_holidays` cũ: sau di trú
	không phiếu nào còn lấy được cuối tuần từ Holiday List, phiếu ngoài MVL bị bỏ sót sẽ ra mẫu số
	31. Trên site cả 5 cấu trúc đều là MVL nên đây không đổi hành vi thực tế.

	Nhánh clamp sao chép Y NGUYÊN ERPNext (`if base > lwp … else 0`) để bất biến kể cả ở ca biên.
	`doc.absent_days` đã gộp `half_absent_days × 0.5`, nên chỉ trừ đúng hai giá trị trên doc.
	"""
	from hrms.hr.work_schedule import scheduled_days_between

	doc.total_working_days = len(scheduled_days_between(doc.employee, doc.start_date, doc.end_date))

	base = len(scheduled_days_between(doc.employee, doc.actual_start_date, doc.actual_end_date))
	lwp = flt(doc.leave_without_pay)
	doc.payment_days = (base - lwp - flt(doc.absent_days)) if base > lwp else 0
```

`hooks.py` — thay đúng một dòng, giữ nguyên khối chú thích thứ tự ba bước:

```python
"Salary Slip": {
    "validate": [
        "hrms.vn_payroll.salary_slip_hook.set_working_days",   # was: add_paid_holidays
        "hrms.vn_payroll.sheet_gate.gate",
        "hrms.vn_payroll.salary_slip_hook.apply_mvl",
    ]
},
```

- [ ] **Step 4: Chạy harness → PASS** (cổng + `test_attendance_code_payroll_invariance` +
      `test_payroll_gate` + `test_flex_shift_payroll_gate` đang có)

- [ ] **Step 5: Đối soát trên dữ liệu thật (rollback harness, chỉ đọc–tính, không commit)** — tính
      lại cả 6 phiếu 07/2026 và so với baseline `23.0 / 19.5 / 22.0 / 22.5`. In bảng so sánh.

- [ ] **Step 6: STOP — trình kết quả, xin ký duyệt.** Chỉ commit sau khi được đồng ý.

- [ ] **Step 7: Commit**

```bash
git add hrms/vn_payroll/salary_slip_hook.py hrms/hooks.py \
        hrms/payroll/doctype/salary_slip/test_working_days_invariance.py
git commit -m "feat(hr): dat mau so luong tu lich tuan thay vi tru theo Holiday List"
```

---

### Task 8: Generator + Work Calendar Settings — mọi ngày lễ khai một cửa

**Files:**
- Rename: `hrms/hr/doctype/lunar_holiday/` → `hrms/hr/doctype/work_calendar_day/` (+ cột `day_type`)
- Create: `hrms/patches/v15_0/rename_lunar_holiday_doctype.py` (**pre_model_sync**)
- Modify: `hrms/patches.txt` (+1 dòng ở `[pre_model_sync]`)
- Modify: `hrms/setup_vn_holiday.py` (bỏ sinh cuối tuần, bỏ tham số `weekly_off_days`)
- Modify: `hrms/hr/doctype/work_calendar_settings/work_calendar_settings.py`
  (bỏ `get_weekly_off_days`; `lunar_holidays` → `calendar_days`; validate trùng ngày + kỳ đã khoá;
  `working_days_preview` cho bảng xem trước)
- Modify: `hrms/hr/doctype/work_calendar_settings/work_calendar_settings.json`
  (bỏ `weekly_off_days`, bảng ngoại lệ *"Ngày đặc biệt trong năm"*)
- Modify: `hrms/hr/doctype/work_calendar_settings/work_calendar_settings.js` (bảng xem trước)
- Modify: `hrms/setup_vn_defaults.py` (self-heal `Ca Hành Chính` = T2–T6)
- Test: `hrms/tests/test_setup_vn_holiday.py`, `.../test_work_calendar_settings.py` (mở rộng)

**Interfaces:**
- Consumes: `is_scheduled_day` (Task 2)
- Produces: `create_vn_holiday_list(year, company, name=None, extra_holidays=None) -> str`
  (**đã bỏ** tham số `weekly_off_days`)

- [ ] **Step 1: Viết test đỏ**

```python
def test_generated_list_has_no_weekly_off_rows(self):
	name = create_vn_holiday_list(2027, self.company)
	self.assertEqual(frappe.db.count("Holiday", {"parent": name, "weekly_off": 1}), 0)

def test_holiday_falling_on_a_rest_day_becomes_a_compensatory_day(self):
	"""Đ.112 kh.3 giữ nguyên, chỉ đổi chỗ hỏi: hỏi lịch tuần thay vì cờ weekly_off.
	01/05/2022 rơi Chủ nhật → nghỉ bù thứ Hai 02/05."""

def test_compensatory_day_never_swallows_another_holiday(self):
	"""Giữ mẹo `scheduled_holidays`: 30/4/2028 rơi CN, ngày bù không được nuốt 1/5."""

def test_manual_holidays_from_settings_are_generated(self):
	"""Lễ âm, lễ riêng công ty VÀ nghỉ ghép đều khai ở Work Calendar Settings."""

def test_make_up_workdays_never_reach_the_holiday_list(self):
	"""Ngày "Làm bù" là ngày LÀM VIỆC — nhét vào bảng ngày nghỉ là sai từ tên gọi."""
	self.set_policy(calendar_days=((2026, "2026-08-29", "Làm bù", "Bù QK"),))
	name = generate_holiday_list(year=2026, company=self.company)
	self.assertFalse(frappe.db.exists("Holiday", {"parent": name, "holiday_date": "2026-08-29"}))

def test_same_date_cannot_be_both_types(self):
	with self.assertRaises(frappe.ValidationError):
		self.set_policy(calendar_days=(
			(2026, "2026-08-29", "Làm bù", "Bù"), (2026, "2026-08-29", "Nghỉ lễ", "Nghỉ"),
		))

def test_cannot_edit_calendar_for_a_locked_period(self):
	"""Bảng Công Tháng đã ký mà đổi lịch quá khứ thì bảng và phiếu lương lệch trong im lặng."""

def test_working_days_preview_shows_before_and_after(self):
	"""Bắt lỗi "khai làm bù mà quên khai nghỉ ghép" — vốn im lặng đổi lương."""
	preview = frappe.get_single("Work Calendar Settings").working_days_preview(2026)
	self.assertEqual(preview[7]["before"], 23)

def test_existing_manual_rows_survive_regeneration(self):
	...
```

- [ ] **Step 2: Chạy harness → FAIL**
- [ ] **Step 3a: Đổi tên child doctype** — `git mv` thư mục + đổi `name`/class, thêm cột
      `day_type` (Select `Nghỉ lễ` / `Làm bù`, mặc định `Nghỉ lễ`), rồi patch **pre_model_sync**:

```python
# hrms/patches/v15_0/rename_lunar_holiday_doctype.py
import frappe


def execute():
	"""Lunar Holiday -> Work Calendar Day. pre_model_sync để bảng đổi tên TRƯỚC khi JSON mới
	sync. Tên cũ đã sai từ lúc bảng nhận thêm lễ riêng công ty, sai nặng hơn khi nhận cả ngày làm bù."""
	if frappe.db.exists("DocType", "Lunar Holiday") and not frappe.db.exists(
		"DocType", "Work Calendar Day"
	):
		frappe.rename_doc("DocType", "Lunar Holiday", "Work Calendar Day", force=True)

	if frappe.db.table_exists("Work Calendar Day"):
		frappe.db.sql(
			"UPDATE `tabWork Calendar Day` SET parenttype = 'Work Calendar Settings', "
			"parentfield = 'calendar_days' WHERE parentfield = 'lunar_holidays'"
		)
```

- [ ] **Step 3b: Generator thôi sinh cuối tuần** — bỏ vòng
      `for day in weekly_off_days: doc.get_weekly_off_dates()`; thay tập `weekly_off_dates` bằng
      `not is_scheduled_day(...)`; bỏ tham số `weekly_off_days` khỏi chữ ký và khỏi
      `generate_holiday_list`. **Chỉ dòng loại `Nghỉ lễ` mới xuống Holiday List** — dòng `Làm bù`
      là ngày làm việc, không phải ngày nghỉ.

- [ ] **Step 3c: Validate + xem trước** — chặn trùng ngày giữa hai loại; chặn sửa ngày thuộc kỳ đã
      khoá (`period_lock.is_period_locked`); cảnh báo khi `Làm bù` rơi vào ngày vốn đã trong mẫu
      tuần; `working_days_preview(year) -> {tháng: {"before": n, "after": n}}` hiện trên form.
- [ ] **Step 4: Chạy harness → PASS**
- [ ] **Step 5: Khai ngược ngày lễ đang có vào Work Calendar Settings** — 6 dòng lễ âm 2026 đã có,
      **thêm** `2026-07-17 "Nghỉ lễ công ty"` để lần sinh sau không mất nó.
- [ ] **Step 6: Commit**

```bash
git add hrms/setup_vn_holiday.py hrms/hr/doctype/work_calendar_settings/ \
        hrms/hr/doctype/work_calendar_day/ hrms/patches/v15_0/rename_lunar_holiday_doctype.py \
        hrms/patches.txt hrms/setup_vn_defaults.py hrms/tests/test_setup_vn_holiday.py
git commit -m "feat(hr): Holiday List chi con ngay le, moi ngay le khai o Work Calendar Settings"
```

---

### Task 9: Đánh dấu check-in ngoài lịch — nền cho OT

**Files:**
- Modify: `hrms/fixtures/custom_field.json` (+2 field `Employee Checkin`)
- Modify: `hrms/hr/doctype/employee_checkin/employee_checkin.py` (`before_validate`)
- Create: `hrms/hr/doctype/employee_checkin/test_outside_schedule.py`

**Interfaces:**
- Consumes: `is_working_day`, `shift_window` (Task 2–3)
- Produces: `Employee Checkin.custom_outside_schedule` (Check),
  `Employee Checkin.custom_outside_reason` (Select: `""` / `Ngày nghỉ` / `Ngoài giờ`)

- [ ] **Step 1: Viết test đỏ**

```python
def test_checkin_on_saturday_is_flagged_as_rest_day(self):
	"""Dữ liệu thật: HR-EMP-00006 chấm 2 lượt vào T7 25/07/2026 mà không sinh công nào."""
	log = make_checkin(self.employee, "2026-07-25 09:00:00")
	self.assertEqual(log.custom_outside_schedule, 1)
	self.assertEqual(log.custom_outside_reason, "Ngày nghỉ")

def test_checkin_after_shift_end_on_a_working_day_is_flagged_as_overtime_window(self):
	log = make_checkin(self.employee, "2026-07-21 20:30:00")
	self.assertEqual(log.custom_outside_reason, "Ngoài giờ")

def test_checkin_inside_shift_is_not_flagged(self):
	...

def test_flag_is_inert_for_attendance(self):
	"""CỐT TỬ: cờ không được chạm vào mã công. Chấm một ngày làm việc bình thường, bật cờ tay,
	chạy lại đường sinh công → mã công và giờ y hệt."""
```

- [ ] **Step 2: Chạy harness → FAIL**
- [ ] **Step 3: Thêm 2 custom field + gắn cờ trong `before_validate`.** Chỉ ghi hai field này, không
      đụng `skip_auto_attendance` (đang là đối tượng chẩn đoán của `skip_attendance_diag.py`).
      Bọc `try/except WorkScheduleNotConfigured` → để trống cờ: một log chấm công **không bao giờ**
      được fail vì lỗi cấu hình lịch.
- [ ] **Step 4: Chạy harness → PASS**
- [ ] **Step 5: `bench --site miyano migrate`**
- [ ] **Step 6: Commit**

```bash
git add hrms/fixtures/custom_field.json hrms/hr/doctype/employee_checkin/
git commit -m "feat(hr): danh dau check-in ngoai lich lam viec lam nen cho OT"
```

---

### Task 10: Patch di trú ⚠️ CỔNG KÝ DUYỆT

> **STOP.** Data migration, **không `git revert` được**. Chạy trên site chỉ sau khi được ký duyệt.

**Files:**
- Create: `hrms/patches/v15_0/remove_weekly_off_from_holiday_list.py`
- Modify: `hrms/patches.txt` (+1 dòng, kèm ngày như các dòng khác)
- Create: `hrms/tests/test_holiday_separation_migration.py`

**Interfaces:**
- Produces: `execute()` — idempotent, tự abort nếu phát hiện lệch

- [ ] **Step 1: Viết test đỏ**

```python
def test_patch_aborts_when_a_shift_has_no_working_days(self):
	"""Chặn TRƯỚC: chưa khai lịch tuần mà xoá dòng cuối tuần là phá mẫu số cả công ty."""

def test_patch_keeps_public_holiday_rows(self):
	"""12 dòng lễ 2026 còn nguyên, kể cả 2 dòng nghỉ bù và dòng nhập tay 17/07."""

def test_patch_leaves_the_test_holiday_list_alone(self):
	"""`Salary Slip Test Holiday List` không thuộc đường chạy thật — đụng vào chỉ làm nhiễu."""

def test_patch_is_idempotent(self):
	...

def test_salary_numbers_identical_after_patch(self):
	"""Chụp 4 con số của mọi Salary Slip trước/sau → giống hệt từng phiếu."""
```

- [ ] **Step 2: Chạy harness → FAIL**
- [ ] **Step 3: Viết patch**

```python
# hrms/patches/v15_0/remove_weekly_off_from_holiday_list.py
# Copyright (c) 2026, Miyano Việt Nam.
"""Gỡ dòng nghỉ cuối tuần khỏi Holiday List — lịch tuần nay ở Shift Type.

Không `git revert` được (xoá dữ liệu), nên tự chặn và tự đối soát: chỉ chạy khi lịch tuần đã khai
đủ, và abort nếu bất kỳ con số lương nào lệch. Idempotent: chạy lại khi đã sạch là no-op.
"""

import re

import frappe
from frappe import _
from frappe.utils import flt

FIELDS = ("total_working_days", "payment_days", "absent_days", "leave_without_pay")
HTML_TAG = re.compile(r"<[^>]+>")


def live_holiday_lists() -> list[str]:
	"""Chỉ những list đang được Company hoặc Employee trỏ tới.

	Danh sách rác của test (`Salary Slip Test Holiday List`) KHÔNG đụng tới — nó không thuộc đường
	chạy thật, sửa nó chỉ làm nhiễu chẩn đoán sau này.
	"""
	names = set(frappe.get_all("Company", pluck="default_holiday_list")) | set(
		frappe.get_all("Employee", pluck="holiday_list")
	)
	return sorted(n for n in names if n)


def snapshot() -> dict:
	return {
		s.name: {f: flt(s.get(f)) for f in FIELDS}
		for s in frappe.get_all("Salary Slip", fields=["name", *FIELDS])
	}


def recomputed(slip_name: str) -> dict:
	doc = frappe.get_doc("Salary Slip", slip_name)
	doc.run_method("validate")
	return {f: flt(doc.get(f)) for f in FIELDS}


def execute():
	lists = live_holiday_lists()
	if not lists:
		return

	# (1) CHẶN TRƯỚC: chưa khai lịch tuần mà xoá dòng cuối tuần là phá mẫu số của cả công ty.
	from hrms.hr.work_schedule import company_default_weekdays, shift_weekdays

	shifts = frappe.get_all("Shift Type", pluck="name")
	if not company_default_weekdays():
		missing = [s for s in shifts if shift_weekdays(s) is None]
		if missing:
			frappe.throw(
				_("Chưa khai ngày làm việc trong tuần cho ca: {0}. Khai xong rồi migrate lại.").format(
					", ".join(missing)
				)
			)

	before = snapshot()  # (2) chụp số

	# (3) xoá dòng nghỉ cuối tuần
	frappe.db.delete("Holiday", {"parent": ("in", lists), "weekly_off": 1})

	# (4) gỡ ghim Employee.holiday_list -> chỉ còn MỘT chỗ phải trỏ lại mỗi năm (Company default)
	frappe.db.set_value("Employee", {"holiday_list": ("in", lists)}, "holiday_list", None)

	# (6) dọn HTML ql-editor lẫn trong description của dòng lễ nhập tay
	for row in frappe.get_all(
		"Holiday", filters={"parent": ("in", lists)}, fields=["name", "description"]
	):
		if row.description and "<" in row.description:
			clean = HTML_TAG.sub("", row.description).strip()
			frappe.db.set_value("Holiday", row.name, "description", clean, update_modified=False)

	for hl in lists:
		frappe.get_doc("Holiday List", hl).save()  # cập nhật total_holidays
	frappe.clear_cache()

	# (5) ĐỐI SOÁT: lệch một số là abort, không để lại trạng thái nửa vời
	for name, want in before.items():
		got = recomputed(name)
		if got != want:
			frappe.db.rollback()
			frappe.throw(_("Phiếu {0} lệch sau di trú: {1} -> {2}").format(name, want, got))
```

Thêm vào cuối `hrms/patches.txt`:

```
hrms.patches.v15_0.remove_weekly_off_from_holiday_list #2026-08-28
```
- [ ] **Step 4: Chạy harness → PASS**
- [ ] **Step 5: Diễn tập trong savepoint trên dữ liệu thật** — chạy patch, in bảng so sánh 6 phiếu,
      rollback. Không commit gì.
- [ ] **Step 6: STOP — trình bảng so sánh, xin ký duyệt chạy thật.**
- [ ] **Step 7: Commit** (chạy `bench migrate` trên site là bước riêng, sau ký duyệt)

```bash
git add hrms/patches/v15_0/remove_weekly_off_from_holiday_list.py hrms/patches.txt \
        hrms/tests/test_holiday_separation_migration.py
git commit -m "feat(hr): patch go dong cuoi tuan khoi Holiday List, co cong doi soat"
```

---

### Task 11: E2E + nghiệm thu

**Files:**
- Create: `hrms/tests/test_holiday_separation_e2e.py`
- Modify: `docs/spec/work-schedule-and-holiday-separation.md` (tick Success Criteria + STATUS)
- Modify: `docs/tasks/plan-work-schedule-and-holiday-separation.md` (tick, ghi kết quả)

- [ ] **Step 1: Viết E2E một tháng đầy đủ** — checkin → auto attendance → bảng công → phiếu lương,
      chạy ở **cả hai** trạng thái Holiday List, so toàn bộ: mã công từng ngày, cột tổng, và 4 con số
      lương. Gồm một tháng **có lễ** (07/2026 có 17/07) và một tháng **có lễ trùng cuối tuần**
      (02/2026: Tết mùng 5 rơi T7 → nghỉ bù 23/02).
- [ ] **Step 2: Chạy toàn bộ bộ test liên quan** — `test_work_schedule`, `test_shift_type`,
      `test_attendance_exempt`, `test_attendance_review`, `test_monthly_attendance_report`,
      `test_working_days_invariance`, `test_attendance_code_payroll_invariance`, `test_payroll_gate`,
      `test_flex_shift_payroll_gate`, `test_setup_vn_holiday`, `test_work_calendar_settings`,
      `test_leave_application`, `test_outside_schedule`, `test_timekeeping_e2e`.
- [ ] **Step 2b: Kiểm success criterion "cửa duy nhất"** — không còn lời gọi `is_holiday` /
      `get_holiday_dates_between` nào trong code Miyano ngoài chính `work_schedule.py`:

```bash
grep -rn "is_holiday\|get_holiday_dates_between\|get_holiday_list_for_employee" hrms/ --include=*.py \
  | grep -v "hrms/hr/work_schedule.py" | grep -v "/test_" | grep -v "hrms/patches/"
```

Kết quả mong đợi: chỉ còn các chỗ thuộc đường ERPNext gốc chưa nằm trong phạm vi spec (nếu có, liệt
kê ra và ghi lý do vào phần nghiệm thu — không im lặng bỏ qua).

- [ ] **Step 3: Kiểm rò rỉ dữ liệu** — sau khi chạy, đếm lại Attendance / Holiday / Salary Slip so
      với trước; DDL có thể huỷ savepoint nên phải kiểm bằng mắt (bẫy đã ghi trong
      `miyano-test-baseline`).
- [ ] **Step 4: Kiểm bằng mắt trên Desk** — form Shift Type có bảng ngày làm việc; bảng công 07/2026
      còn nguyên `-`/`NL`/màu; PWA *Upcoming Holidays* nay chỉ còn ngày lễ thật.
- [ ] **Step 5: Cập nhật spec + plan, commit**

```bash
git add hrms/tests/test_holiday_separation_e2e.py docs/spec/ docs/tasks/
git commit -m "test(hr): E2E tach lich lam viec khoi lich nghi le + nghiem thu"
```

---

## Thứ tự và vì sao nó an toàn

```
1 → 2 → 3        API lịch (thêm mới, chưa ai dùng — không đổi hành vi)
      ↓
4                chỉ đọc: báo cáo/bảng công  ─┐
5                sinh công                    │  mỗi task đều BẤT BIẾN ở CẢ HAI
6                đơn nghỉ                     │  trạng thái Holiday List, nên
7 ⚠️              payroll (ký duyệt)          │  thứ tự deploy không quan trọng
      ↓                                       │  và migration là no-op số học
8                generator thôi sinh cuối tuần┘
9                cờ ngoài lịch (độc lập, có thể chen bất cứ đâu sau Task 3)
      ↓
10 ⚠️             patch di trú (ký duyệt)
11               E2E + nghiệm thu
```

Tasks 4–7 **phải** xong trước 8/10. Nếu đảo, sẽ có một quãng mà dòng cuối tuần đã biến mất nhưng
consumer vẫn hỏi Holiday List → V mọi thứ Bảy và mẫu số lương nhảy 23 → 31.
