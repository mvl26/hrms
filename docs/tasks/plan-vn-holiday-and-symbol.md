# VN Holiday-List + Symbol Standardization — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended)
> or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

Derived from `docs/spec/vn-holiday-and-symbol-standardization.md`. Branch: `feat/skip-attendance-diag`.

**Goal:** Standardize VN timekeeping display + a real VN Holiday List using existing ERP doctypes:
show rest days as `-`, add code `N` for paid personal leave (marriage/funeral, Art. 115), and ship an
on-demand VN Holiday List generator — all payroll-neutral.

**Architecture:** Additive fixtures (`Leave Type` + `Attendance Code` "N"), two report-marker constant
changes, one new float column on the submittable sheet, and one new idempotent helper
`create_vn_holiday_list`. The existing two-way attendance bridge handles code `N` with **no** controller
change; the payroll-invariance gate is extended to prove it.

**Tech Stack:** Frappe/ERPNext HRMS v15, Python (`frappe.qb`, controllers), fixtures JSON. Tests run via
the **rollback console harness** (never `bench run-tests` on `miyano`).

## Status: ✅ DONE 2026-07-14 (all 6 tasks, `/build auto`)

Built on `feat/skip-attendance-diag`, TDD per task, one commit each, **80 tests green** (46 feature +
5 attendance_code + 29 shift_type regression). Commits: `1967167` (T1 fixtures N + Leave Type) ·
`7d92bae` (T2 invariance) · `bd0263d` (T3 report `-`/`NL`/Việc riêng) · `ed43143` (T4 sheet `viec_rieng`) ·
`41d838b` (T5 Holiday List generator) · this commit (T6 docs). **Not yet done (ask-first):** deploy
fixtures / run `create_vn_holiday_list` on **production**; that is the deliberate deploy step, not autonomous.

## Global Constraints

- **Payroll-invariance GATE:** any change touching attendance/codes must prove Salary Slip
  `payment_days` / `absent_days` / `leave_without_pay` are byte-identical vs native entry. No exceptions.
- **Never** edit `status` / `leave_type` / `half_day_status` semantics or Salary Slip logic.
- **Stage only each task's own files** (`git add <paths>`; never `git add -A`) — the working tree carries
  unrelated dirty files (frontend/*, docs/, .claude/).
- **Fixtures additive**; keep the `hooks.py` fixtures export filter in sync with the JSON
  (`test_setup_vn_defaults.py` enforces it).
- **Confirmed symbols (2026-07-14):** `X` = full workday (unchanged) · `-` = rest day (weekly-off /
  post-relieving) · `NL` = public holiday (kept) · `N` = paid personal leave (marriage/funeral). No other
  code renamed → **no code-migration patch this round**.
- **Ask-first (STOP for sign-off):** deploying fixtures / running `create_vn_holiday_list` on **production**
  sites; the deferred payroll "paid-holiday" change (out of scope here). Migrating onto the near-empty dev
  `miyano` is fine.
- **Reversible** via `git revert`; VN labels + ASCII folder/code names; tab indentation; double quotes.

## Running tests (rollback harness — NEVER `bench run-tests` on `miyano`)

Create this reusable runner once (Task 1, Step 0), then every "Run" step calls it:

`scratch/run_test.sh` (in the session scratchpad):
```bash
#!/usr/bin/env bash
# Usage: bash scratch/run_test.sh "<dotted.module.path>[.TestClass.test_method]"
cd /home/miyano/frappe-bench
bench --site miyano console <<PY
import frappe, unittest
frappe.flags.in_test = True
_c = frappe.db.commit
frappe.db.commit = lambda *a, **k: None          # never persist test writes into the live DB
class R(unittest.TextTestResult):
    def startTest(self, t):
        frappe.db.savepoint("tc"); super().startTest(t)
    def stopTest(self, t):
        super().stopTest(t); frappe.db.rollback(save_point="tc")
try:
    s = unittest.TestLoader().loadTestsFromName("$1")
    res = unittest.TextTestRunner(resultclass=R, verbosity=2).run(s)
    print("RESULT:", "OK" if res.wasSuccessful() else "FAIL", "errors", len(res.errors), "fails", len(res.failures))
finally:
    frappe.db.commit = _c
    frappe.db.rollback()
PY
```

---

## Task 1: Fixtures — Leave Type "Nghỉ việc riêng" + Attendance Code "N" + hooks filter

**Files:**
- Modify: `hrms/fixtures/leave_type.json` (append one Leave Type)
- Modify: `hrms/fixtures/attendance_code.json` (append code "N")
- Modify: `hrms/hooks.py:379-397` (add "Nghỉ việc riêng" to the Leave Type export filter)
- Test: `hrms/hr/doctype/attendance_code/test_attendance_code_fixtures.py` (extend the two dicts)

**Interfaces:**
- Produces: Leave Type `"Nghỉ việc riêng"` (`is_lwp=0`, `is_compensatory=0`); Attendance Code `"N"`
  (`category="Việc riêng"`, `work_fraction=0.0`, `is_paid=1`, `maps_to_status="On Leave"`,
  `leave_type="Nghỉ việc riêng"`). Consumed by Tasks 2, 3, 4.

- [x] **Step 0: Create the test runner**

Write `scratch/run_test.sh` with the content from "Running tests" above, then `chmod +x` is optional (call
with `bash`).

- [x] **Step 1: Extend the fixtures test (failing)**

In `test_attendance_code_fixtures.py`, add to `VN_LEAVE_TYPES` (after the `"Nghỉ không lương"` line):

```python
	"Nghỉ việc riêng": {"is_lwp": 0, "is_compensatory": 0},
```

Add to `VN_ATTENDANCE_CODES` (after the `"CT"` line):

```python
	"N": ("Việc riêng", 0.0, 1, "On Leave", "Nghỉ việc riêng"),  # nghỉ việc riêng có lương (cưới/tang)
```

- [x] **Step 2: Run — verify it fails**

Run: `bash scratch/run_test.sh "hrms.hr.doctype.attendance_code.test_attendance_code_fixtures"`
Expected: FAIL — `Missing Leave Type: Nghỉ việc riêng` / `Missing Attendance Code: N`.

- [x] **Step 3: Add the Leave Type fixture**

Append to the array in `hrms/fixtures/leave_type.json` (mirror the existing anchor shape):

```json
 {
  "allocate_on_day": "Last Day",
  "allow_encashment": 0,
  "allow_negative": 0,
  "allow_over_allocation": 0,
  "applicable_after": 0,
  "docstatus": 0,
  "doctype": "Leave Type",
  "earned_leave_frequency": "Monthly",
  "earning_component": null,
  "expire_carry_forwarded_leaves_after_days": 0,
  "fraction_of_daily_salary_per_leave": 0.0,
  "include_holiday": 0,
  "is_carry_forward": 0,
  "is_compensatory": 0,
  "is_earned_leave": 0,
  "is_lwp": 0,
  "is_optional_leave": 0,
  "is_ppl": 0,
  "leave_type_name": "Nghỉ việc riêng",
  "max_continuous_days_allowed": 0,
  "max_encashable_leaves": 0,
  "max_leaves_allowed": 0.0,
  "maximum_carry_forwarded_leaves": 0.0,
  "modified": "2026-07-14 00:00:00.000000",
  "name": "Nghỉ việc riêng",
  "non_encashable_leaves": 0,
  "rounding": ""
 }
```

(Add a comma after the previous last object's closing brace.)

- [x] **Step 4: Add the Attendance Code fixture**

Append to the array in `hrms/fixtures/attendance_code.json`:

```json
 {
  "category": "Việc riêng",
  "code": "N",
  "code_name": "Nghỉ việc riêng có lương",
  "color": null,
  "docstatus": 0,
  "doctype": "Attendance Code",
  "is_paid": 1,
  "leave_type": "Nghỉ việc riêng",
  "maps_to_status": "On Leave",
  "modified": "2026-07-14 00:00:00.000000",
  "name": "N",
  "work_fraction": 0.0
 }
```

(Add a comma after the previous last object's closing brace.)

- [x] **Step 5: Sync the hooks export filter**

In `hrms/hooks.py`, inside the `"Leave Type"` filter `"in"` list (after `"Nghỉ không lương",`) add:

```python
					"Nghỉ việc riêng",
```

- [x] **Step 6: Load fixtures onto dev `miyano`**

Run: `cd /home/miyano/frappe-bench && bench --site miyano migrate`
Expected: clean migrate; fixtures sync creates Leave Type `Nghỉ việc riêng` + Attendance Code `N`.

- [x] **Step 7: Run — verify fixtures test passes + hooks/JSON consistency test passes**

Run: `bash scratch/run_test.sh "hrms.hr.doctype.attendance_code.test_attendance_code_fixtures"`
Run: `bash scratch/run_test.sh "hrms.tests.test_setup_vn_defaults"`
Expected: both `RESULT: OK`.

- [x] **Step 8: Commit**

```bash
git add hrms/fixtures/leave_type.json hrms/fixtures/attendance_code.json hrms/hooks.py \
        hrms/hr/doctype/attendance_code/test_attendance_code_fixtures.py
git commit -m "feat(hr): add code N (nghi viec rieng co luong) + its leave type fixture"
```

---

## Task 2: Prove code "N" flows through the bridge and is payroll-neutral

**Files:**
- Test: `hrms/hr/doctype/attendance/test_attendance_code_bridge.py` (add 2 tests)
- Test: `hrms/payroll/doctype/salary_slip/test_attendance_code_payroll_invariance.py` (add 1 scenario)

**Interfaces:**
- Consumes: Attendance Code `"N"` + Leave Type `"Nghỉ việc riêng"` from Task 1. No controller change is
  expected — the generic bridge in `attendance.py:77-114` already maps any full-day On-Leave code.

- [x] **Step 1: Add bridge tests (forward + reverse) for N**

Append to `class TestAttendanceCodeBridge` in `test_attendance_code_bridge.py`:

```python
	def test_forward_personal_leave(self):
		# N = nghỉ việc riêng có lương -> On Leave, leave_type Nghỉ việc riêng, no worked công
		d = self._bridge(custom_attendance_code="N")
		self.assertEqual(d.status, "On Leave")
		self.assertEqual(d.leave_type, "Nghỉ việc riêng")
		self.assertEqual(d.custom_cong, 0)

	def test_reverse_personal_leave(self):
		# native On-Leave record of that leave type (no code) -> derive display code N
		d = self._bridge(status="On Leave", leave_type="Nghỉ việc riêng")
		self.assertEqual(d.custom_attendance_code, "N")
		self.assertEqual(d.custom_cong, 0)
```

- [x] **Step 2: Run — expected PASS (bridge is generic; no code change)**

Run: `bash scratch/run_test.sh "hrms.hr.doctype.attendance.test_attendance_code_bridge"`
Expected: `RESULT: OK`. (If it FAILS, the bridge is not resolving the new fixture — stop and inspect
`_derive_attendance_code_reverse`; do not weaken the test.)

- [x] **Step 3: Extend the payroll-invariance gate with an N scenario**

In `test_attendance_code_payroll_invariance.py`, add to the `SCENARIOS` list (after the `CT` line):

```python
	(6, "On Leave", "Nghỉ việc riêng", "N"),  # paid personal leave — no deduction
```

- [x] **Step 4: Run — verify payroll figures identical (native vs code) incl. N**

Run: `bash scratch/run_test.sh "hrms.payroll.doctype.salary_slip.test_attendance_code_payroll_invariance"`
Expected: `RESULT: OK` — `payment_days` / `absent_days` / `leave_without_pay` identical; N (is_lwp=0) adds
no LWP.

- [x] **Step 5: Commit**

```bash
git add hrms/hr/doctype/attendance/test_attendance_code_bridge.py \
        hrms/payroll/doctype/salary_slip/test_attendance_code_payroll_invariance.py
git commit -m "test(hr): prove code N bridges + stays payroll-neutral (invariance gate)"
```

---

## Task 3: Report — rest day = "-", new "Việc riêng" totals category

**Files:**
- Modify: `hrms/hr/report/bang_cham_cong_thang/bang_cham_cong_thang.py:27-29,59`
- Test: `hrms/hr/report/bang_cham_cong_thang/test_bang_cham_cong_thang.py` (create if absent)

**Interfaces:**
- Consumes: `get_sheet_rows(filters)` (unchanged signature), `code_map` with the new `N`/`Việc riêng`.
- Produces: display markers — `weekly_off` day → `"-"`, post-`relieving_date` → `"-"`, public holiday →
  `"NL"`; totals include a `"Việc riêng"` category.

- [x] **Step 1: Write the failing report test**

Create/append `test_bang_cham_cong_thang.py` next to the report:

```python
# Copyright (c) 2026, Miyano Việt Nam.
"""Report markers: rest day '-', holiday 'NL', post-relieving '-'."""
from hrms.hr.report.bang_cham_cong_thang.bang_cham_cong_thang import (
	MARKER_HOLIDAY,
	MARKER_TERMINATED,
	MARKER_WEEKLY_OFF,
)


def test_rest_day_marker_is_dash():
	assert MARKER_WEEKLY_OFF == "-"


def test_terminated_marker_is_dash():
	assert MARKER_TERMINATED == "-"


def test_holiday_marker_is_nl():
	assert MARKER_HOLIDAY == "NL"
```

- [x] **Step 2: Run — verify it fails**

Run: `bash scratch/run_test.sh "hrms.hr.report.bang_cham_cong_thang.test_bang_cham_cong_thang"`
Expected: FAIL — `MARKER_WEEKLY_OFF == "CN"`, `MARKER_TERMINATED == "N"`.

- [x] **Step 3: Change the markers**

In `bang_cham_cong_thang.py`, replace lines 27-29:

```python
# display-only markers derived from the calendar, not Attendance Code master records
MARKER_TERMINATED = "-"  # after relieving_date — HR convention: rest day
MARKER_WEEKLY_OFF = "-"  # nghỉ hàng tuần (CN/T7) — HR convention: rest day
MARKER_HOLIDAY = "NL"  # ngày nghỉ lễ có lương — kept distinct so paid holidays are visible
```

- [x] **Step 4: Add "Việc riêng" to the preferred category order**

In `get_categories`, replace the `preferred` list (line 59):

```python
	preferred = ["Công", "Phép", "Việc riêng", "Ốm", "Thai sản", "Tai nạn LĐ", "Nghỉ bù", "Không lương", "Vắng"]
```

- [x] **Step 5: Run — markers test passes + existing report test still green**

Run: `bash scratch/run_test.sh "hrms.hr.report.bang_cham_cong_thang.test_bang_cham_cong_thang"`
Expected: `RESULT: OK`. (If a pre-existing report test asserts a `"CN"` cell or an 8-category count,
update that expectation to `"-"` / 9 categories in the same commit — the derivation is unchanged, only the
symbol/category list.)

- [x] **Step 6: Commit**

```bash
git add hrms/hr/report/bang_cham_cong_thang/bang_cham_cong_thang.py \
        hrms/hr/report/bang_cham_cong_thang/test_bang_cham_cong_thang.py
git commit -m "feat(hr): bang cham cong — rest day '-', keep 'NL', add 'Viec rieng' total"
```

---

## Task 4: Bảng Công Tháng — `viec_rieng` totals column

**Files:**
- Modify: `hrms/hr/doctype/bang_cong_thang_detail/bang_cong_thang_detail.json` (add Float field)
- Modify: `hrms/hr/doctype/bang_cong_thang/bang_cong_thang.py:62-70` (add mapping entry)
- Modify: `hrms/hr/print_format/bang_cong_thang/bang_cong_thang.json` (add column header + cell)
- Test: `hrms/hr/doctype/bang_cong_thang/test_bang_cong_thang.py` (add assertion)

**Interfaces:**
- Consumes: `get_sheet_rows` totals now include `"Việc riêng"`.
- Produces: `Bang Cong Thang Detail.viec_rieng` (Float, read-only, precision 2), populated from the
  `"Việc riêng"` category.

- [x] **Step 1: Write the failing test**

Append to `test_bang_cong_thang.py` a test that seeds one `N` Attendance day for an employee, creates the
sheet, calls `populate_from_attendance()`, and asserts the child row's `viec_rieng == 1.0`. Mirror the
existing populate test in that file (same setup/company/month); the only new assertion is:

```python
		self.assertEqual(row.viec_rieng, 1.0)
```

- [x] **Step 2: Run — verify it fails**

Run: `bash scratch/run_test.sh "hrms.hr.doctype.bang_cong_thang.test_bang_cong_thang"`
Expected: FAIL — `AttributeError: viec_rieng` (field/mapping absent).

- [x] **Step 3: Add the detail field**

In `bang_cong_thang_detail.json`, add a field object mirroring the existing `phep` float
(same properties: `"fieldtype": "Float"`, `"read_only": 1`, `"precision": "2"`), placed after `phep`:

```json
  {
   "fieldname": "viec_rieng",
   "fieldtype": "Float",
   "in_list_view": 1,
   "label": "Việc riêng",
   "precision": "2",
   "read_only": 1
  },
```

Also add `"viec_rieng"` to the doctype's `field_order` array right after `"phep"`.

- [x] **Step 4: Add the category→field mapping**

In `bang_cong_thang.py`, insert into the `category_field` dict (after `"Phép": "phep",`):

```python
			"Việc riêng": "viec_rieng",
```

- [x] **Step 5: Add the print-format column**

In `bang_cong_thang.json` print format HTML, add a `Việc riêng` header cell next to `Phép` and a body cell
`{{ row.viec_rieng or "" }}` in the same position. (Match the surrounding `<th>`/`<td>` markup exactly.)

- [x] **Step 6: Migrate + run — test passes**

Run: `cd /home/miyano/frappe-bench && bench --site miyano migrate` (loads the new field)
Run: `bash scratch/run_test.sh "hrms.hr.doctype.bang_cong_thang.test_bang_cong_thang"`
Expected: `RESULT: OK` (incl. the pre-existing parity/payroll-neutral tests in this module).

- [x] **Step 7: Commit**

```bash
git add hrms/hr/doctype/bang_cong_thang_detail/bang_cong_thang_detail.json \
        hrms/hr/doctype/bang_cong_thang/bang_cong_thang.py \
        hrms/hr/print_format/bang_cong_thang/bang_cong_thang.json \
        hrms/hr/doctype/bang_cong_thang/test_bang_cong_thang.py
git commit -m "feat(hr): bang cong thang — add 'Viec rieng' totals column + print cell"
```

---

## Task 5: WS1 — `create_vn_holiday_list` generator

**Files:**
- Create: `hrms/setup_vn_holiday.py`
- Test: `hrms/tests/test_setup_vn_holiday.py`

**Interfaces:**
- Produces: `create_vn_holiday_list(year, company, weekly_off_days=("Sunday",), name=None) -> str`
  (returns the Holiday List name). Idempotent; on-demand (never auto-run on migrate).

- [x] **Step 1: Write the failing test**

Create `hrms/tests/test_setup_vn_holiday.py`:

```python
# Copyright (c) 2026, Miyano Việt Nam.
"""Tests for the on-demand VN Holiday List generator (weekly-off + solar public holidays;
Tết/Giỗ Tổ are entered manually). Runs via the rollback harness — writes are rolled back."""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import getdate

import erpnext

from hrms.setup_vn_holiday import SOLAR_HOLIDAYS, create_vn_holiday_list


class TestSetupVNHoliday(FrappeTestCase):
	def setUp(self):
		self.company = erpnext.get_default_company() or frappe.get_all("Company", limit=1)[0].name
		self.year = 2027

	def _dates(self, name):
		return {
			getdate(r.holiday_date): r.weekly_off
			for r in frappe.get_all(
				"Holiday",
				filters={"parent": name, "parenttype": "Holiday List"},
				fields=["holiday_date", "weekly_off"],
			)
		}

	def test_creates_weekly_off_and_solar_holidays(self):
		name = create_vn_holiday_list(self.year, self.company, weekly_off_days=("Sunday",))
		dates = self._dates(name)
		# every Sunday of 2027 is a weekly_off row (~52)
		sundays = [d for d, wo in dates.items() if wo]
		self.assertGreaterEqual(len(sundays), 52)
		self.assertTrue(all(d.weekday() == 6 for d in sundays))  # 6 = Sunday
		# the 5 fixed solar public holidays are present, weekly_off = 0
		for mm, dd in SOLAR_HOLIDAYS:
			self.assertIn(getdate(f"{self.year}-{mm:02d}-{dd:02d}"), dates)
			self.assertEqual(dates[getdate(f"{self.year}-{mm:02d}-{dd:02d}")], 0)

	def test_idempotent(self):
		name1 = create_vn_holiday_list(self.year, self.company, weekly_off_days=("Sunday",))
		n1 = len(self._dates(name1))
		name2 = create_vn_holiday_list(self.year, self.company, weekly_off_days=("Sunday",))
		self.assertEqual(name1, name2)
		self.assertEqual(len(self._dates(name2)), n1)  # no duplicate rows

	def test_two_weekly_off_days(self):
		name = create_vn_holiday_list(self.year, self.company, weekly_off_days=("Saturday", "Sunday"))
		wo = [d for d, w in self._dates(name).items() if w]
		self.assertTrue(any(d.weekday() == 5 for d in wo))  # Saturday present
		self.assertTrue(any(d.weekday() == 6 for d in wo))  # Sunday present
```

- [x] **Step 2: Run — verify it fails**

Run: `bash scratch/run_test.sh "hrms.tests.test_setup_vn_holiday"`
Expected: FAIL — `ModuleNotFoundError: hrms.setup_vn_holiday`.

- [x] **Step 3: Implement the generator**

Create `hrms/setup_vn_holiday.py`:

```python
"""On-demand generator for a Vietnamese Holiday List.

Creates ONE Holiday List per (company, year) using the stock Holiday List doctype:
  - weekly-off rows (Chủ nhật, optionally + Thứ 7) via the doctype's own get_weekly_off_dates;
  - the fixed SOLAR public holidays of Điều 112 BLLĐ 2019 (Tết dương, 30/4, 1/5, Quốc khánh ×2).

Tết Âm lịch (5 ngày) + Giỗ Tổ (10/3 âm) shift every year (lunar) → HR enters those by hand.
Idempotent (re-running never duplicates dates). On-demand only — NOT wired to migrate/install,
because creating a Holiday List is creating company data (ask-first on production).

Usage:
  bench --site <s> execute hrms.setup_vn_holiday.create_vn_holiday_list \
        --kwargs "{'year': 2026, 'company': 'Miyano', 'weekly_off_days': ['Sunday']}"
"""

import frappe

# (month, day) of the fixed SOLAR public holidays. Quốc khánh = 2 ngày (01/09 + 02/09).
SOLAR_HOLIDAYS = [
	(1, 1),   # Tết Dương lịch
	(4, 30),  # Ngày Giải phóng miền Nam
	(5, 1),   # Quốc tế Lao động
	(9, 1),   # Quốc khánh (ngày liền kề)
	(9, 2),   # Quốc khánh
]

SOLAR_LABELS = {
	(1, 1): "Tết Dương lịch",
	(4, 30): "Ngày Giải phóng miền Nam",
	(5, 1): "Quốc tế Lao động",
	(9, 1): "Nghỉ Quốc khánh",
	(9, 2): "Quốc khánh",
}


def create_vn_holiday_list(year, company, weekly_off_days=("Sunday",), name=None):
	"""Create/refresh a VN Holiday List for `year`. Returns its name. Idempotent."""
	year = int(year)
	list_name = name or f"VN {company} {year}"

	if frappe.db.exists("Holiday List", list_name):
		doc = frappe.get_doc("Holiday List", list_name)
	else:
		doc = frappe.get_doc(
			{
				"doctype": "Holiday List",
				"holiday_list_name": list_name,
				"from_date": f"{year}-01-01",
				"to_date": f"{year}-12-31",
			}
		)

	# weekly-off rows: get_weekly_off_dates skips dates already present, so looping is idempotent
	for day in weekly_off_days:
		doc.weekly_off = day
		doc.get_weekly_off_dates()

	existing = {frappe.utils.getdate(h.holiday_date) for h in doc.holidays}
	for mm, dd in SOLAR_HOLIDAYS:
		d = frappe.utils.getdate(f"{year}-{mm:02d}-{dd:02d}")
		if d not in existing:
			doc.append(
				"holidays",
				{"holiday_date": d, "description": SOLAR_LABELS[(mm, dd)], "weekly_off": 0},
			)
			existing.add(d)

	doc.save()  # validate() sorts, counts, and rejects duplicate dates
	frappe.msgprint(
		frappe._("Đã tạo {0}. Nhớ nhập tay Tết Âm lịch + Giỗ Tổ (10/3 âm) cho năm {1}.").format(
			list_name, year
		)
	)
	return doc.name
```

- [x] **Step 4: Run — generator tests pass**

Run: `bash scratch/run_test.sh "hrms.tests.test_setup_vn_holiday"`
Expected: `RESULT: OK` (weekly-off count, solar holidays, idempotency, two-weekly-off-days).

- [x] **Step 5: Commit**

```bash
git add hrms/setup_vn_holiday.py hrms/tests/test_setup_vn_holiday.py
git commit -m "feat(hr): on-demand VN Holiday List generator (weekly-off + solar holidays)"
```

---

## Task 6: Holiday-list resolution check + end-to-end verify + docs

**Files:**
- Test: `hrms/tests/test_setup_vn_holiday.py` (add a resolution test)
- Modify: `docs/tasks/plan-vn-holiday-and-symbol.md` (tick boxes), `docs/spec/vn-holiday-and-symbol-standardization.md`
  (mark success criteria)

**Interfaces:** Consumes everything above; no new production code.

- [x] **Step 1: Add a Company-default resolution test**

Append to `test_setup_vn_holiday.py`:

```python
	def test_report_resolves_company_default_list(self):
		# an employee WITHOUT an explicit holiday_list must resolve the company default,
		# so the bảng công report can mark '-' on that employee's rest days.
		from erpnext.setup.doctype.employee.employee import get_holiday_list_for_employee

		name = create_vn_holiday_list(self.year, self.company, weekly_off_days=("Sunday",))
		frappe.db.set_value("Company", self.company, "default_holiday_list", name)
		emp = frappe.get_all("Employee", filters={"company": self.company}, limit=1)
		if not emp:
			self.skipTest("no employee for the default company")
		frappe.db.set_value("Employee", emp[0].name, "holiday_list", None)
		self.assertEqual(get_holiday_list_for_employee(emp[0].name, raise_exception=False), name)
```

- [x] **Step 2: Run the full standardization test set via the harness**

Run each and confirm `RESULT: OK`:
```
bash scratch/run_test.sh "hrms.hr.doctype.attendance_code.test_attendance_code_fixtures"
bash scratch/run_test.sh "hrms.hr.doctype.attendance.test_attendance_code_bridge"
bash scratch/run_test.sh "hrms.payroll.doctype.salary_slip.test_attendance_code_payroll_invariance"
bash scratch/run_test.sh "hrms.hr.report.bang_cham_cong_thang.test_bang_cham_cong_thang"
bash scratch/run_test.sh "hrms.hr.doctype.bang_cong_thang.test_bang_cong_thang"
bash scratch/run_test.sh "hrms.tests.test_setup_vn_holiday"
bash scratch/run_test.sh "hrms.tests.test_setup_vn_defaults"
```

- [x] **Step 3: End-to-end smoke on dev `miyano`**

Run the generator + render the report for a month, confirming `-` / `NL` / `N` render:
```bash
cd /home/miyano/frappe-bench
bench --site miyano execute hrms.setup_vn_holiday.create_vn_holiday_list \
      --kwargs "{'year': 2026, 'company': '<default company>', 'weekly_off_days': ['Sunday']}"
```
Then open the "Bang Cham Cong Thang" report for a month in Desk and visually confirm rest days show `-`,
holidays show `NL`, and any `N` day shows `N`.

- [x] **Step 4: Tick the plan + spec success criteria, commit docs**

Mark the checkboxes in this plan and the `## Success Criteria` in the spec.

```bash
git add docs/tasks/plan-vn-holiday-and-symbol.md docs/spec/vn-holiday-and-symbol-standardization.md \
        hrms/tests/test_setup_vn_holiday.py
git commit -m "docs(hr): VN holiday+symbol standardization done — resolution test + criteria ticked"
```

---

## Self-Review

**Spec coverage:**
- WS1 Holiday List generator → Task 5; resolution review → Task 6 Step 1. ✓
- WS2 symbol `-` (rest/terminated) + keep `NL` → Task 3. ✓
- WS2 code `N` (việc riêng) + Leave Type → Task 1; bridge + invariance → Task 2; sheet total → Task 4. ✓
- Half-day precision → already covered by existing bridge/invariance tests (Task 2 keeps them green; no
  new half-day code introduced this round). ✓
- Deferred (payroll paid-holiday, annual-leave entitlement) → explicitly out of scope. ✓

**Placeholder scan:** every code step shows real content; the only "mirror the existing test" pointers
(Task 4 Step 1, Task 3 Step 5) reference concrete, named existing tests in the same file and add one exact
assertion — acceptable because the surrounding setup is identical and shown in-repo.

**Type consistency:** `create_vn_holiday_list(year, company, weekly_off_days, name)` and `SOLAR_HOLIDAYS`
are used identically in Task 5 impl + Task 5/6 tests. `MARKER_WEEKLY_OFF/TERMINATED/HOLIDAY` names match the
report constants. `viec_rieng` field name matches across detail JSON, mapping, print, and test. `"Việc
riêng"` category string matches fixture, report `preferred`, and `category_field`. ✓

## Open interpretations (confirm during review; low-risk to flip)
1. `-` applies to weekly-off + post-relieving only; public holidays stay `NL`.
2. `N` category = new `"Việc riêng"` (its own total column) rather than folded into `Phép`.
3. Weekly-off default = `Sunday`; pass `("Saturday","Sunday")` for a 5-day week at generation time.
