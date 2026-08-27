# Attendance Working Hours + Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Thêm cột "Tổng giờ làm thực tế" (trừ 90' nghỉ trưa, gộp theo Tháng/Tuần) vào report Monthly Attendance Sheet và một Dashboard quản lý 2 biểu đồ (xu hướng theo tuần, theo phòng ban).

**Architecture:** Một thư viện lõi `hrms/hr/working_hours.py` chứa toàn bộ logic tính giờ net; report và 2 Dashboard Chart Source đều gọi vào lõi này (không lặp logic). Không thay đổi schema/DB.

**Tech Stack:** Frappe v15 / hrms (Python query builder `frappe.qb`, script report, Dashboard Chart Source, Dashboard — desk JSON records).

## Global Constraints

- Mọi file Python/JS mới mở đầu bằng `# Copyright (c) 2026, Miyano Việt Nam.` (JS dùng `//`).
- Hằng số nghỉ trưa: `LUNCH_BREAK_HOURS = 1.5` (giờ).
- Status được trừ 1.5h (ngày đủ): `("Present", "Work From Home")`. `"Half Day"` → không trừ. Status khác → 0.
- Nguồn giờ/ngày: `out_time − in_time` qua `frappe.utils.time_diff_in_hours(out_time, in_time)`; nếu thiếu in_time hoặc out_time → dùng trường `working_hours`.
- Mọi giá trị giờ hiển thị làm tròn 2 chữ số.
- Không sửa schema, không migration DB. Dashboard đóng gói bằng desk JSON, nạp qua `bench migrate`.
- Chạy test: `bench --site miyano run-tests --module <module.path>`.
- Nhãn cột/biểu đồ bọc trong `_()` (chuẩn Frappe, English source string); bản dịch tiếng Việt để sau, ngoài phạm vi plan này.

---

### Task 1: Lõi — `compute_net_hours`

**Files:**
- Create: `hrms/hr/working_hours.py`
- Test: `hrms/hr/tests/test_working_hours.py`

**Interfaces:**
- Produces: `LUNCH_BREAK_HOURS = 1.5`; `compute_net_hours(status: str, in_time, out_time, working_hours) -> float`

- [ ] **Step 1: Viết test fail** — tạo `hrms/hr/tests/test_working_hours.py`

```python
# Copyright (c) 2026, Miyano Việt Nam.

from frappe.tests.utils import FrappeTestCase

from hrms.hr.working_hours import compute_net_hours


class TestComputeNetHours(FrappeTestCase):
	def test_present_full_day_deducts_lunch(self):
		# 08:00 -> 17:30 = 9.5h gross, trừ 1.5h = 8.0h
		net = compute_net_hours("Present", "2026-03-02 08:00:00", "2026-03-02 17:30:00", 9.5)
		self.assertEqual(net, 8.0)

	def test_work_from_home_deducts_lunch(self):
		net = compute_net_hours("Work From Home", "2026-03-02 08:00:00", "2026-03-02 16:00:00", 8.0)
		self.assertEqual(net, 6.5)

	def test_half_day_no_deduction(self):
		# 08:00 -> 12:00 = 4.0h, Half Day không trừ
		net = compute_net_hours("Half Day", "2026-03-02 08:00:00", "2026-03-02 12:00:00", 4.0)
		self.assertEqual(net, 4.0)

	def test_fallback_to_working_hours_when_no_in_out(self):
		# thiếu in/out -> dùng working_hours rồi trừ 1.5h
		net = compute_net_hours("Present", None, None, 9.0)
		self.assertEqual(net, 7.5)

	def test_floor_at_zero(self):
		# gross 1.0h, trừ 1.5h -> sàn 0
		net = compute_net_hours("Present", "2026-03-02 08:00:00", "2026-03-02 09:00:00", 1.0)
		self.assertEqual(net, 0.0)

	def test_absent_and_leave_are_zero(self):
		self.assertEqual(compute_net_hours("Absent", None, None, 0), 0.0)
		self.assertEqual(compute_net_hours("On Leave", None, None, 0), 0.0)
```

- [ ] **Step 2: Chạy test, xác nhận FAIL**

Run: `bench --site miyano run-tests --module hrms.hr.tests.test_working_hours`
Expected: FAIL — `ModuleNotFoundError` / `ImportError: cannot import name 'compute_net_hours'`

- [ ] **Step 3: Viết `hrms/hr/working_hours.py` (phần lõi)**

```python
# Copyright (c) 2026, Miyano Việt Nam.

import frappe
from frappe import _
from frappe.utils import cint, flt, getdate, time_diff_in_hours

LUNCH_BREAK_HOURS = 1.5
FULL_DAY_STATUSES = ("Present", "Work From Home")


def compute_net_hours(status, in_time, out_time, working_hours):
	"""Giờ làm net của một ngày: gross (out-in hoặc working_hours) trừ nghỉ trưa theo status."""
	if in_time and out_time:
		gross = flt(time_diff_in_hours(out_time, in_time))
	else:
		gross = flt(working_hours)

	if gross <= 0:
		return 0.0

	if status in FULL_DAY_STATUSES:
		return max(round(gross - LUNCH_BREAK_HOURS, 2), 0.0)
	if status == "Half Day":
		return round(gross, 2)
	return 0.0
```

- [ ] **Step 4: Chạy test, xác nhận PASS**

Run: `bench --site miyano run-tests --module hrms.hr.tests.test_working_hours`
Expected: PASS (6 test trong `TestComputeNetHours`)

- [ ] **Step 5: Commit**

```bash
git add hrms/hr/working_hours.py hrms/hr/tests/test_working_hours.py
git commit -m "feat(hr): add compute_net_hours core for working hours

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: Lõi — `get_week_buckets`

**Files:**
- Modify: `hrms/hr/working_hours.py`
- Test: `hrms/hr/tests/test_working_hours.py`

**Interfaces:**
- Produces: `get_week_buckets(year, month) -> list[dict]` — mỗi phần tử `{"label": "Week i", "days": [int,...]}`, theo thứ tự thời gian, tuần dương lịch T2–CN, chỉ chứa ngày thuộc tháng.

- [ ] **Step 1: Viết test fail** — thêm class vào `hrms/hr/tests/test_working_hours.py`

```python
from hrms.hr.working_hours import compute_net_hours, get_week_buckets


class TestGetWeekBuckets(FrappeTestCase):
	def test_march_2026_buckets(self):
		# 1/3/2026 là Chủ nhật -> nằm riêng ở tuần đầu (phần đuôi của tuần ISO trước)
		buckets = get_week_buckets(2026, 3)
		self.assertEqual(buckets[0]["days"], [1])
		self.assertIn(2, buckets[1]["days"])

	def test_all_days_covered_once_in_order(self):
		buckets = get_week_buckets(2026, 3)
		all_days = [d for b in buckets for d in b["days"]]
		self.assertEqual(all_days, list(range(1, 32)))  # tháng 3 có 31 ngày, đủ và đúng thứ tự

	def test_labels_are_sequential(self):
		buckets = get_week_buckets(2026, 3)
		labels = [b["label"] for b in buckets]
		self.assertEqual(labels, [f"{_('Week')} {i}" for i in range(1, len(buckets) + 1)])
```

Lưu ý: thêm `from frappe import _` vào đầu file test.

- [ ] **Step 2: Chạy test, xác nhận FAIL**

Run: `bench --site miyano run-tests --module hrms.hr.tests.test_working_hours`
Expected: FAIL — `cannot import name 'get_week_buckets'`

- [ ] **Step 3: Thêm hàm vào `hrms/hr/working_hours.py`**

```python
from calendar import monthrange


def get_week_buckets(year, month):
	"""Chia các ngày trong tháng thành tuần dương lịch (T2-CN, ISO), chỉ giữ ngày thuộc tháng."""
	year, month = cint(year), cint(month)
	total_days = monthrange(year, month)[1]

	buckets = {}
	order = []
	for day in range(1, total_days + 1):
		iso_year, iso_week, _weekday = getdate(f"{year}-{month:02d}-{day:02d}").isocalendar()
		key = (iso_year, iso_week)
		if key not in buckets:
			buckets[key] = []
			order.append(key)
		buckets[key].append(day)

	return [{"label": f"{_('Week')} {i}", "days": buckets[key]} for i, key in enumerate(order, start=1)]
```

- [ ] **Step 4: Chạy test, xác nhận PASS**

Run: `bench --site miyano run-tests --module hrms.hr.tests.test_working_hours`
Expected: PASS (cả `TestComputeNetHours` và `TestGetWeekBuckets`)

- [ ] **Step 5: Commit**

```bash
git add hrms/hr/working_hours.py hrms/hr/tests/test_working_hours.py
git commit -m "feat(hr): add get_week_buckets for weekly aggregation

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Lõi — `get_net_hours_map` + `prepare_filters`

**Files:**
- Modify: `hrms/hr/working_hours.py`
- Test: `hrms/hr/tests/test_working_hours.py`

**Interfaces:**
- Consumes: `compute_net_hours` (Task 1)
- Produces:
  - `get_net_hours_map(filters) -> dict` dạng `{employee: {shift: {day_of_month: net_hours}}}` (shift None → khóa `""`). `filters` cần `companies` (list) hoặc `company`, `month`, `year`, optional `employee`.
  - `prepare_filters(filters) -> frappe._dict` — đảm bảo `month`/`year` mặc định tháng hiện tại và `companies` suy ra từ `company` (+ descendants nếu `include_company_descendants`).

- [ ] **Step 1: Viết test fail** — thêm class vào `hrms/hr/tests/test_working_hours.py`

```python
import frappe
from dateutil.relativedelta import relativedelta
from frappe.utils import getdate

from erpnext.setup.doctype.employee.test_employee import make_employee

from hrms.hr.doctype.attendance.attendance import mark_attendance
from hrms.hr.working_hours import get_net_hours_map


class TestGetNetHoursMap(FrappeTestCase):
	def setUp(self):
		self.company = "_Test Company"
		self.employee = make_employee("wh_map_test@example.com", company=self.company)
		frappe.db.delete("Attendance", {"employee": self.employee})

	def test_present_day_net_hours_in_map(self):
		date = getdate("2026-03-02")  # ngày 2
		name = mark_attendance(self.employee, date, "Present")
		frappe.db.set_value(
			"Attendance", name,
			{"in_time": "2026-03-02 08:00:00", "out_time": "2026-03-02 17:30:00"},
		)
		filters = frappe._dict(
			company=self.company, companies=[self.company], month=3, year=2026
		)
		hours_map = get_net_hours_map(filters)
		self.assertEqual(hours_map[self.employee][""][2], 8.0)  # 9.5 - 1.5

	def test_fallback_working_hours_when_no_in_out(self):
		date = getdate("2026-03-03")  # ngày 3
		name = mark_attendance(self.employee, date, "Present")
		frappe.db.set_value("Attendance", name, "working_hours", 9.0)
		filters = frappe._dict(
			company=self.company, companies=[self.company], month=3, year=2026
		)
		hours_map = get_net_hours_map(filters)
		self.assertEqual(hours_map[self.employee][""][3], 7.5)  # 9.0 - 1.5
```

- [ ] **Step 2: Chạy test, xác nhận FAIL**

Run: `bench --site miyano run-tests --module hrms.hr.tests.test_working_hours`
Expected: FAIL — `cannot import name 'get_net_hours_map'`

- [ ] **Step 3: Thêm hàm vào `hrms/hr/working_hours.py`**

```python
from frappe.query_builder.functions import Extract
from frappe.utils.nestedset import get_descendants_of


def prepare_filters(filters):
	filters = frappe._dict(filters or {})
	today = getdate()
	filters.month = cint(filters.get("month")) or today.month
	filters.year = cint(filters.get("year")) or today.year

	if not filters.get("companies"):
		company = filters.get("company")
		companies = [company] if company else []
		if company and filters.get("include_company_descendants"):
			companies.extend(get_descendants_of("Company", company))
		filters.companies = companies

	return filters


def get_net_hours_map(filters):
	"""{employee: {shift: {day_of_month: net_hours}}} cho tháng/năm trong filters."""
	companies = filters.get("companies") or ([filters.get("company")] if filters.get("company") else [])

	Attendance = frappe.qb.DocType("Attendance")
	query = (
		frappe.qb.from_(Attendance)
		.select(
			Attendance.employee,
			Attendance.shift,
			Extract("day", Attendance.attendance_date).as_("day_of_month"),
			Attendance.status,
			Attendance.in_time,
			Attendance.out_time,
			Attendance.working_hours,
		)
		.where(
			(Attendance.docstatus == 1)
			& (Attendance.company.isin(companies))
			& (Extract("month", Attendance.attendance_date) == filters.get("month"))
			& (Extract("year", Attendance.attendance_date) == filters.get("year"))
		)
	)
	if filters.get("employee"):
		query = query.where(Attendance.employee == filters.get("employee"))

	hours_map = {}
	for d in query.run(as_dict=True):
		shift = d.shift or ""
		net = compute_net_hours(d.status, d.in_time, d.out_time, d.working_hours)
		hours_map.setdefault(d.employee, {}).setdefault(shift, {})[d.day_of_month] = net

	return hours_map
```

- [ ] **Step 4: Chạy test, xác nhận PASS**

Run: `bench --site miyano run-tests --module hrms.hr.tests.test_working_hours`
Expected: PASS (cả 4 class)

- [ ] **Step 5: Commit**

```bash
git add hrms/hr/working_hours.py hrms/hr/tests/test_working_hours.py
git commit -m "feat(hr): add get_net_hours_map and prepare_filters

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: Lõi — tổng hợp theo tuần & theo phòng ban

**Files:**
- Modify: `hrms/hr/working_hours.py`
- Test: `hrms/hr/tests/test_working_hours.py`

**Interfaces:**
- Consumes: `get_net_hours_map`, `get_week_buckets`, `prepare_filters` (Task 1–3)
- Produces:
  - `get_hours_by_week(filters) -> {"labels": [str], "values": [float]}`
  - `get_hours_by_department(filters) -> {"labels": [str], "values": [float]}`

- [ ] **Step 1: Viết test fail** — thêm class vào `hrms/hr/tests/test_working_hours.py`

```python
from hrms.hr.working_hours import get_hours_by_department, get_hours_by_week


class TestHoursAggregation(FrappeTestCase):
	def setUp(self):
		self.company = "_Test Company"
		self.employee = make_employee("wh_agg_test@example.com", company=self.company)
		frappe.db.delete("Attendance", {"employee": self.employee})
		name = mark_attendance(self.employee, getdate("2026-03-02"), "Present")
		frappe.db.set_value(
			"Attendance", name,
			{"in_time": "2026-03-02 08:00:00", "out_time": "2026-03-02 17:30:00"},
		)
		self.filters = frappe._dict(
			company=self.company, companies=[self.company], month=3, year=2026
		)

	def test_by_week_total_matches(self):
		data = get_hours_by_week(self.filters)
		self.assertEqual(len(data["labels"]), len(data["values"]))
		self.assertEqual(round(sum(data["values"]), 2), 8.0)

	def test_by_department_total_matches(self):
		data = get_hours_by_department(self.filters)
		self.assertEqual(len(data["labels"]), len(data["values"]))
		self.assertEqual(round(sum(data["values"]), 2), 8.0)
```

- [ ] **Step 2: Chạy test, xác nhận FAIL**

Run: `bench --site miyano run-tests --module hrms.hr.tests.test_working_hours`
Expected: FAIL — `cannot import name 'get_hours_by_week'`

- [ ] **Step 3: Thêm hàm vào `hrms/hr/working_hours.py`**

```python
def _employee_total(shift_hours):
	return sum(net for days in shift_hours.values() for net in days.values())


def get_hours_by_week(filters):
	filters = prepare_filters(filters)
	hours_map = get_net_hours_map(filters)
	buckets = get_week_buckets(filters.year, filters.month)

	labels, values = [], []
	for bucket in buckets:
		day_set = set(bucket["days"])
		total = 0.0
		for shift_hours in hours_map.values():
			for days in shift_hours.values():
				for day, net in days.items():
					if day in day_set:
						total += net
		labels.append(bucket["label"])
		values.append(round(total, 2))

	return {"labels": labels, "values": values}


def get_hours_by_department(filters):
	filters = prepare_filters(filters)
	hours_map = get_net_hours_map(filters)

	employees = list(hours_map.keys())
	dept_of = {}
	if employees:
		for emp in frappe.get_all(
			"Employee", filters={"name": ["in", employees]}, fields=["name", "department"]
		):
			dept_of[emp.name] = emp.department or _("No Department")

	totals = {}
	for emp, shift_hours in hours_map.items():
		dept = dept_of.get(emp, _("No Department"))
		totals[dept] = totals.get(dept, 0.0) + _employee_total(shift_hours)

	labels = list(totals.keys())
	values = [round(totals[d], 2) for d in labels]
	return {"labels": labels, "values": values}
```

- [ ] **Step 4: Chạy test, xác nhận PASS**

Run: `bench --site miyano run-tests --module hrms.hr.tests.test_working_hours`
Expected: PASS (cả 5 class)

- [ ] **Step 5: Commit**

```bash
git add hrms/hr/working_hours.py hrms/hr/tests/test_working_hours.py
git commit -m "feat(hr): add weekly and department working-hours aggregation

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: Report Monthly Attendance Sheet — filter + cột Tổng giờ làm

**Files:**
- Modify: `hrms/hr/report/monthly_attendance_sheet/monthly_attendance_sheet.py`
- Modify: `hrms/hr/report/monthly_attendance_sheet/monthly_attendance_sheet.js`
- Test: `hrms/hr/report/monthly_attendance_sheet/test_monthly_attendance_sheet.py`

**Interfaces:**
- Consumes: `get_net_hours_map`, `get_week_buckets` từ `hrms.hr.working_hours`
- Produces (nội bộ report): `get_working_hours_columns(filters)`, `set_working_hours_on_row(row, day_hours, filters, week_buckets)`, `_flatten_employee_hours(shift_hours)`; cột mới `total_working_hours` (Float) và (chế độ Week) `week_1..week_N` (Float).

- [ ] **Step 1: Viết test fail** — thêm 2 method vào class `TestMonthlyAttendanceSheet` trong `test_monthly_attendance_sheet.py`

```python
	@set_holiday_list("Salary Slip Test Holiday List", "_Test Company")
	def test_total_working_hours_month_mode(self):
		first = get_first_day_for_prev_month()

		n0 = mark_attendance(self.employee, first, "Present")
		frappe.db.set_value(
			"Attendance", n0,
			{"in_time": f"{first} 08:00:00", "out_time": f"{first} 17:30:00"},
		)  # 9.5 - 1.5 = 8.0
		second = first + relativedelta(days=1)
		n1 = mark_attendance(self.employee, second, "Present")
		frappe.db.set_value(
			"Attendance", n1,
			{"in_time": f"{second} 08:00:00", "out_time": f"{second} 16:00:00"},
		)  # 8.0 - 1.5 = 6.5

		filters = frappe._dict(
			month=first.month, year=first.year, company=self.company,
			working_hours_period="Month",
		)
		report = execute(filters=filters)
		row = next(r for r in report[1] if r.get("employee") == self.employee)
		self.assertEqual(row["total_working_hours"], 14.5)

	@set_holiday_list("Salary Slip Test Holiday List", "_Test Company")
	def test_working_hours_week_mode_columns(self):
		first = get_first_day_for_prev_month()
		n0 = mark_attendance(self.employee, first, "Present")
		frappe.db.set_value(
			"Attendance", n0,
			{"in_time": f"{first} 08:00:00", "out_time": f"{first} 17:30:00"},
		)

		filters = frappe._dict(
			month=first.month, year=first.year, company=self.company,
			working_hours_period="Week",
		)
		report = execute(filters=filters)
		fieldnames = [c["fieldname"] for c in report[0]]
		self.assertIn("total_working_hours", fieldnames)
		self.assertTrue(any(fn.startswith("week_") for fn in fieldnames))

		row = next(r for r in report[1] if r.get("employee") == self.employee)
		week_total = sum(v for k, v in row.items() if k.startswith("week_"))
		self.assertEqual(round(week_total, 2), row["total_working_hours"])
```

- [ ] **Step 2: Chạy test, xác nhận FAIL**

Run: `bench --site miyano run-tests --module hrms.hr.report.monthly_attendance_sheet.test_monthly_attendance_sheet`
Expected: FAIL — `KeyError: 'total_working_hours'`

- [ ] **Step 3a: Thêm import** ở đầu `monthly_attendance_sheet.py` (sau các import frappe hiện có)

```python
from hrms.hr.working_hours import get_net_hours_map, get_week_buckets
```

- [ ] **Step 3b: Cuối hàm `get_columns`** — ngay trước `return columns`, chèn:

```python
	columns.extend(get_working_hours_columns(filters))
```

- [ ] **Step 3c: Thêm hàm `get_working_hours_columns`** (đặt ngay sau `get_columns`)

```python
def get_working_hours_columns(filters: Filters) -> list[dict]:
	columns = []
	if filters.get("working_hours_period") == "Week":
		week_buckets = get_week_buckets(filters.year, filters.month)
		for idx in range(1, len(week_buckets) + 1):
			columns.append(
				{"label": f"{_('Week')} {idx}", "fieldname": f"week_{idx}", "fieldtype": "Float", "width": 90}
			)
		columns.append(
			{"label": _("Total (Month)"), "fieldname": "total_working_hours", "fieldtype": "Float", "width": 110}
		)
	else:
		columns.append(
			{"label": _("Total Working Hours"), "fieldname": "total_working_hours", "fieldtype": "Float", "width": 130}
		)
	return columns
```

- [ ] **Step 3d: Sửa `get_data`** — nạp map và truyền xuống. Thay thân hàm `get_data`:

```python
def get_data(filters: Filters, attendance_map: dict) -> list[dict]:
	employee_details, group_by_param_values = get_employee_related_details(filters)
	holiday_map = get_holiday_map(filters)
	net_hours_map = get_net_hours_map(filters)
	data = []

	if filters.group_by:
		group_by_column = frappe.scrub(filters.group_by)

		for value in group_by_param_values:
			if not value:
				continue

			records = get_rows(employee_details[value], filters, holiday_map, attendance_map, net_hours_map)

			if records:
				data.append({group_by_column: value})
				data.extend(records)
	else:
		data = get_rows(employee_details, filters, holiday_map, attendance_map, net_hours_map)

	return data
```

- [ ] **Step 3e: Sửa `get_rows`** — thêm tham số `net_hours_map`, gắn giờ vào mỗi dòng. Thay thân hàm `get_rows`:

```python
def get_rows(
	employee_details: dict, filters: Filters, holiday_map: dict, attendance_map: dict, net_hours_map: dict
) -> list[dict]:
	records = []
	default_holiday_list = frappe.get_cached_value("Company", filters.company, "default_holiday_list")
	week_buckets = (
		get_week_buckets(filters.year, filters.month)
		if filters.get("working_hours_period") == "Week"
		else None
	)

	for employee, details in employee_details.items():
		emp_holiday_list = details.holiday_list or default_holiday_list
		holidays = holiday_map.get(emp_holiday_list)

		if filters.summarized_view:
			attendance = get_attendance_status_for_summarized_view(
				employee, filters, holidays, details.joined_in_current_period, details.joined_date
			)
			if not attendance:
				continue

			leave_summary = get_leave_summary(employee, filters)
			entry_exits_summary = get_entry_exits_summary(employee, filters)

			row = {"employee": employee, "employee_name": details.employee_name}
			set_defaults_for_summarized_view(filters, row)
			row.update(attendance)
			row.update(leave_summary)
			row.update(entry_exits_summary)

			emp_day_hours = _flatten_employee_hours(net_hours_map.get(employee, {}))
			set_working_hours_on_row(row, emp_day_hours, filters, week_buckets)

			records.append(row)
		else:
			employee_attendance = attendance_map.get(employee)
			if not employee_attendance:
				continue

			attendance_for_employee = get_attendance_status_for_detailed_view(
				employee, filters, employee_attendance, holidays
			)
			# set employee details in the first row
			for record in attendance_for_employee:
				shift_key = record.get("shift") or ""
				day_hours = net_hours_map.get(employee, {}).get(shift_key, {})
				set_working_hours_on_row(record, day_hours, filters, week_buckets)
				record.update({"employee": employee, "employee_name": details.employee_name})

			records.extend(attendance_for_employee)

	return records
```

- [ ] **Step 3f: Thêm 2 helper** (đặt ngay sau `get_rows`)

```python
def _flatten_employee_hours(shift_hours: dict) -> dict:
	day_hours = {}
	for days in shift_hours.values():
		for day, net in days.items():
			day_hours[day] = day_hours.get(day, 0.0) + net
	return day_hours


def set_working_hours_on_row(row: dict, day_hours: dict, filters: Filters, week_buckets) -> None:
	if filters.get("working_hours_period") == "Week" and week_buckets:
		total = 0.0
		for idx, bucket in enumerate(week_buckets, start=1):
			week_total = round(sum(day_hours.get(day, 0.0) for day in bucket["days"]), 2)
			row[f"week_{idx}"] = week_total
			total += week_total
		row["total_working_hours"] = round(total, 2)
	else:
		row["total_working_hours"] = round(sum(day_hours.values()), 2)
```

- [ ] **Step 3g: Thêm filter vào `.js`** — trong mảng `filters`, ngay sau object `summarized_view`, thêm:

```javascript
		{
			fieldname: "working_hours_period",
			label: __("Working Hours By"),
			fieldtype: "Select",
			options: ["Month", "Week"],
			default: "Month",
		},
```

- [ ] **Step 4: Chạy test, xác nhận PASS**

Run: `bench --site miyano run-tests --module hrms.hr.report.monthly_attendance_sheet.test_monthly_attendance_sheet`
Expected: PASS (gồm cả test cũ và 2 test mới). Nếu test cũ dùng `report[1][1].get("shift")` vẫn pass vì ta chỉ THÊM key, không đổi thứ tự dòng.

- [ ] **Step 5: Commit**

```bash
git add hrms/hr/report/monthly_attendance_sheet/monthly_attendance_sheet.py \
        hrms/hr/report/monthly_attendance_sheet/monthly_attendance_sheet.js \
        hrms/hr/report/monthly_attendance_sheet/test_monthly_attendance_sheet.py
git commit -m "feat(hr): add total working hours column to monthly attendance sheet

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: Dashboard "Working Hours" — 2 chart source + 2 chart + dashboard

**Files:**
- Create: `hrms/hr/dashboard_chart_source/working_hours_by_week/__init__.py`
- Create: `hrms/hr/dashboard_chart_source/working_hours_by_week/working_hours_by_week.py`
- Create: `hrms/hr/dashboard_chart_source/working_hours_by_week/working_hours_by_week.js`
- Create: `hrms/hr/dashboard_chart_source/working_hours_by_week/working_hours_by_week.json`
- Create: `hrms/hr/dashboard_chart_source/working_hours_by_department/__init__.py`
- Create: `hrms/hr/dashboard_chart_source/working_hours_by_department/working_hours_by_department.py`
- Create: `hrms/hr/dashboard_chart_source/working_hours_by_department/working_hours_by_department.js`
- Create: `hrms/hr/dashboard_chart_source/working_hours_by_department/working_hours_by_department.json`
- Create: `hrms/hr/dashboard_chart/working_hours_by_week/working_hours_by_week.json`
- Create: `hrms/hr/dashboard_chart/working_hours_by_department/working_hours_by_department.json`
- Create: `hrms/hr/hr_dashboard/working_hours/working_hours.json`

**Interfaces:**
- Consumes: `get_hours_by_week`, `get_hours_by_department`, `prepare_filters` từ `hrms.hr.working_hours`
- Produces: Dashboard Chart Source "Working Hours by Week" / "Working Hours by Department"; Dashboard "Working Hours".

Đây là task đóng gói desk JSON — không theo TDD; deliverable kiểm chứng bằng `bench migrate` + truy vấn DB.

- [ ] **Step 1: Tạo Chart Source "by week"**

`hrms/hr/dashboard_chart_source/working_hours_by_week/__init__.py`: file rỗng.

`hrms/hr/dashboard_chart_source/working_hours_by_week/working_hours_by_week.py`:

```python
# Copyright (c) 2026, Miyano Việt Nam.

import frappe
from frappe import _
from frappe.utils.dashboard import cache_source

from hrms.hr.working_hours import get_hours_by_week, prepare_filters


@frappe.whitelist()
@cache_source
def get_data(
	chart_name=None,
	chart=None,
	no_cache=None,
	filters=None,
	from_date=None,
	to_date=None,
	timespan=None,
	time_interval=None,
	heatmap_year=None,
) -> dict[str, list]:
	filters = frappe.parse_json(filters) if filters else {}
	filters = prepare_filters(filters)
	data = get_hours_by_week(filters)
	return {
		"labels": data["labels"],
		"datasets": [{"name": _("Working Hours"), "values": data["values"]}],
	}
```

`hrms/hr/dashboard_chart_source/working_hours_by_week/working_hours_by_week.js`:

```javascript
frappe.provide("frappe.dashboards.chart_sources");

frappe.dashboards.chart_sources["Working Hours by Week"] = {
	method: "hrms.hr.dashboard_chart_source.working_hours_by_week.working_hours_by_week.get_data",
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_user_default("Company"),
		},
		{
			fieldname: "month",
			label: __("Month"),
			fieldtype: "Select",
			options: [
				{ value: 1, label: __("Jan") }, { value: 2, label: __("Feb") },
				{ value: 3, label: __("Mar") }, { value: 4, label: __("Apr") },
				{ value: 5, label: __("May") }, { value: 6, label: __("June") },
				{ value: 7, label: __("July") }, { value: 8, label: __("Aug") },
				{ value: 9, label: __("Sep") }, { value: 10, label: __("Oct") },
				{ value: 11, label: __("Nov") }, { value: 12, label: __("Dec") },
			],
			default: frappe.datetime.str_to_obj(frappe.datetime.get_today()).getMonth() + 1,
		},
		{
			fieldname: "year",
			label: __("Year"),
			fieldtype: "Int",
			default: frappe.datetime.str_to_obj(frappe.datetime.get_today()).getFullYear(),
		},
	],
};
```

`hrms/hr/dashboard_chart_source/working_hours_by_week/working_hours_by_week.json`:

```json
{
 "creation": "2026-06-30 00:00:00.000000",
 "docstatus": 0,
 "doctype": "Dashboard Chart Source",
 "idx": 0,
 "modified": "2026-06-30 00:00:00.000000",
 "modified_by": "Administrator",
 "module": "HR",
 "name": "Working Hours by Week",
 "owner": "Administrator",
 "source_name": "Working Hours by Week",
 "timeseries": 0
}
```

- [ ] **Step 2: Tạo Chart Source "by department"** — giống Step 1, đổi tên/hàm.

`hrms/hr/dashboard_chart_source/working_hours_by_department/__init__.py`: file rỗng.

`hrms/hr/dashboard_chart_source/working_hours_by_department/working_hours_by_department.py`:

```python
# Copyright (c) 2026, Miyano Việt Nam.

import frappe
from frappe import _
from frappe.utils.dashboard import cache_source

from hrms.hr.working_hours import get_hours_by_department, prepare_filters


@frappe.whitelist()
@cache_source
def get_data(
	chart_name=None,
	chart=None,
	no_cache=None,
	filters=None,
	from_date=None,
	to_date=None,
	timespan=None,
	time_interval=None,
	heatmap_year=None,
) -> dict[str, list]:
	filters = frappe.parse_json(filters) if filters else {}
	filters = prepare_filters(filters)
	data = get_hours_by_department(filters)
	return {
		"labels": data["labels"],
		"datasets": [{"name": _("Working Hours"), "values": data["values"]}],
	}
```

`hrms/hr/dashboard_chart_source/working_hours_by_department/working_hours_by_department.js`: giống file `.js` ở Step 1 nhưng đổi khóa và method:

```javascript
frappe.provide("frappe.dashboards.chart_sources");

frappe.dashboards.chart_sources["Working Hours by Department"] = {
	method: "hrms.hr.dashboard_chart_source.working_hours_by_department.working_hours_by_department.get_data",
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_user_default("Company"),
		},
		{
			fieldname: "month",
			label: __("Month"),
			fieldtype: "Select",
			options: [
				{ value: 1, label: __("Jan") }, { value: 2, label: __("Feb") },
				{ value: 3, label: __("Mar") }, { value: 4, label: __("Apr") },
				{ value: 5, label: __("May") }, { value: 6, label: __("June") },
				{ value: 7, label: __("July") }, { value: 8, label: __("Aug") },
				{ value: 9, label: __("Sep") }, { value: 10, label: __("Oct") },
				{ value: 11, label: __("Nov") }, { value: 12, label: __("Dec") },
			],
			default: frappe.datetime.str_to_obj(frappe.datetime.get_today()).getMonth() + 1,
		},
		{
			fieldname: "year",
			label: __("Year"),
			fieldtype: "Int",
			default: frappe.datetime.str_to_obj(frappe.datetime.get_today()).getFullYear(),
		},
	],
};
```

`hrms/hr/dashboard_chart_source/working_hours_by_department/working_hours_by_department.json`:

```json
{
 "creation": "2026-06-30 00:00:00.000000",
 "docstatus": 0,
 "doctype": "Dashboard Chart Source",
 "idx": 0,
 "modified": "2026-06-30 00:00:00.000000",
 "modified_by": "Administrator",
 "module": "HR",
 "name": "Working Hours by Department",
 "owner": "Administrator",
 "source_name": "Working Hours by Department",
 "timeseries": 0
}
```

- [ ] **Step 3: Tạo 2 Dashboard Chart (type Custom)**

`hrms/hr/dashboard_chart/working_hours_by_week/working_hours_by_week.json`:

```json
{
 "chart_name": "Working Hours by Week",
 "chart_type": "Custom",
 "creation": "2026-06-30 00:00:00.000000",
 "custom_options": "{\n\t\"type\": \"line\"\n}",
 "docstatus": 0,
 "doctype": "Dashboard Chart",
 "dynamic_filters_json": "{\"company\":\"frappe.defaults.get_user_default(\\\"Company\\\")\",\"month\":\"frappe.datetime.str_to_obj(frappe.datetime.get_today()).getMonth() + 1\",\"year\":\"frappe.datetime.str_to_obj(frappe.datetime.get_today()).getFullYear()\"}",
 "filters_json": "{}",
 "idx": 0,
 "is_public": 1,
 "is_standard": 1,
 "module": "HR",
 "name": "Working Hours by Week",
 "owner": "Administrator",
 "roles": [],
 "source": "Working Hours by Week",
 "timeseries": 0,
 "type": "Line",
 "use_report_chart": 0
}
```

`hrms/hr/dashboard_chart/working_hours_by_department/working_hours_by_department.json`:

```json
{
 "chart_name": "Working Hours by Department",
 "chart_type": "Custom",
 "creation": "2026-06-30 00:00:00.000000",
 "custom_options": "{\n\t\"type\": \"bar\"\n}",
 "docstatus": 0,
 "doctype": "Dashboard Chart",
 "dynamic_filters_json": "{\"company\":\"frappe.defaults.get_user_default(\\\"Company\\\")\",\"month\":\"frappe.datetime.str_to_obj(frappe.datetime.get_today()).getMonth() + 1\",\"year\":\"frappe.datetime.str_to_obj(frappe.datetime.get_today()).getFullYear()\"}",
 "filters_json": "{}",
 "idx": 0,
 "is_public": 1,
 "is_standard": 1,
 "module": "HR",
 "name": "Working Hours by Department",
 "owner": "Administrator",
 "roles": [],
 "source": "Working Hours by Department",
 "timeseries": 0,
 "type": "Bar",
 "use_report_chart": 0
}
```

- [ ] **Step 4: Tạo Dashboard**

`hrms/hr/hr_dashboard/working_hours/working_hours.json`:

```json
{
 "cards": [],
 "charts": [
  {
   "chart": "Working Hours by Week",
   "width": "Full"
  },
  {
   "chart": "Working Hours by Department",
   "width": "Full"
  }
 ],
 "creation": "2026-06-30 00:00:00.000000",
 "dashboard_name": "Working Hours",
 "docstatus": 0,
 "doctype": "Dashboard",
 "idx": 0,
 "is_default": 0,
 "is_standard": 1,
 "modified": "2026-06-30 00:00:00.000000",
 "modified_by": "Administrator",
 "module": "HR",
 "name": "Working Hours",
 "owner": "Administrator"
}
```

- [ ] **Step 5: Nạp vào DB qua migrate**

Run: `bench --site miyano migrate`
Expected: chạy xong không lỗi.

- [ ] **Step 6: Xác minh đã nạp**

Run:
```bash
bench --site miyano mariadb -N -e "SELECT name FROM \`tabDashboard Chart Source\` WHERE name LIKE 'Working Hours%'; SELECT name, chart_type, source FROM \`tabDashboard Chart\` WHERE name LIKE 'Working Hours%'; SELECT name FROM tabDashboard WHERE name='Working Hours';"
```
Expected: 2 Chart Source, 2 Dashboard Chart (Custom), 1 Dashboard "Working Hours".

- [ ] **Step 7: Smoke test get_data của chart source** (không lỗi runtime)

Run:
```bash
bench --site miyano execute hrms.hr.dashboard_chart_source.working_hours_by_week.working_hours_by_week.get_data --kwargs "{'filters': '{\"company\": \"_Test Company\", \"month\": 3, \"year\": 2026}'}"
```
Expected: in ra dict `{'labels': [...], 'datasets': [{'name': 'Working Hours', 'values': [...]}]}` (values có thể toàn 0 nếu chưa có attendance — vẫn hợp lệ).

- [ ] **Step 8: Commit**

```bash
git add hrms/hr/dashboard_chart_source/working_hours_by_week \
        hrms/hr/dashboard_chart_source/working_hours_by_department \
        hrms/hr/dashboard_chart/working_hours_by_week \
        hrms/hr/dashboard_chart/working_hours_by_department \
        hrms/hr/hr_dashboard/working_hours
git commit -m "feat(hr): add Working Hours management dashboard

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Self-Review (đã thực hiện khi viết plan)

**1. Spec coverage:**
- Cột Tổng giờ làm + trừ 90' → Task 1, 5. ✓
- Gộp Tháng/Tuần qua filter → Task 2, 5 (filter `working_hours_period`). ✓
- Nguồn out−in, fallback working_hours → Task 1, 3. ✓
- WFH như Present, Half Day không trừ → Task 1 (FULL_DAY_STATUSES, test). ✓
- Dashboard 2 biểu đồ (tuần + phòng ban) → Task 4, 6. ✓
- Lõi dùng chung → `working_hours.py` (Task 1–4), report & dashboard gọi vào. ✓
- Test → mỗi task có test/verify. ✓

**2. Placeholder scan:** Không có TBD/TODO; mọi step có code/lệnh cụ thể. ✓

**3. Type consistency:** Tên hàm khớp xuyên suốt: `compute_net_hours`, `get_week_buckets`, `get_net_hours_map`, `prepare_filters`, `get_hours_by_week`, `get_hours_by_department`, `get_working_hours_columns`, `set_working_hours_on_row`, `_flatten_employee_hours`. Khóa shift None → `""` nhất quán giữa map và report. Cột `total_working_hours` / `week_{idx}` dùng giống nhau ở columns và row-setter. ✓

## Lưu ý khi thực thi
- Site `miyano` chưa có bản ghi Attendance; test tự tạo `_Test Company` + employee + attendance nên không phụ thuộc dữ liệu sẵn có.
- Sau Task 5/6 nên `bench build --app hrms` để JS filter/chart source mới được bundle khi kiểm thử trên giao diện.
- Nhãn cột đang là English trong `_()`; muốn hiển thị tiếng Việt thì bổ sung bản dịch (ngoài phạm vi).
