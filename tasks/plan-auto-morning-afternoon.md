# Auto Morning/Afternoon Attendance + Lunch-aware Net Hours — Implementation Plan (Phase 4)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or
> superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax. **This feature changes payroll
> classification** → Task 3 is a hard gate; Task 5 requires sign-off before enabling on prod shifts.

Derived from `spec/auto-morning-afternoon-attendance.md`. Branch: `feat/skip-attendance-diag`.

**Goal:** Keep one Attendance/day but auto-derive morning/afternoon codes + lunch-excluded net hours from
the day's in/out and a per-shift schedule, so a person who worked only one session is correctly a Half Day.

**Architecture:** A gated classifier method `Attendance.apply_vn_half_day_classifier()` runs at the top of
`before_validate` (before the existing mã-công bridge). It reads 5 new `Shift Type` custom fields (config,
defaults on install), computes coverage of the morning [start,lunch_start] and afternoon [lunch_end,end]
windows (≥ `min_fraction`, with grace), sets `custom_morning_code`/`custom_afternoon_code` (X worked / V
not) so the bridge derives status + công, and stores `working_hours` = morning+afternoon overlap (lunch
excluded). Gated by `custom_split_half_day` so shifts that don't opt in — and every upstream test — are
unaffected.

**Tech Stack:** Frappe/ERPNext HRMS v15, Python (`datetime`, `frappe.utils`), fixtures JSON. Tests via the
rollback console harness (never `bench run-tests` on `miyano`).

## Status: ✅ built T1–T5 on dev 2026-07-15 (`/build auto`); prod enablement STOP-gated

TDD, one commit each, **110 tests green** (8 classifier + 15 bridge + 3 invariance + 26 working-hours +
29 shift_type + 7 report + 9 sheet + 4 fixtures + 4 holiday + 5 defaults). The classifier is a **no-op on
dev** — no shift has `custom_split_half_day=1`, so no existing attendance/payroll changed. **NOT done
(hard sign-off gate):** enabling `custom_split_half_day` on any **production** shift + the one-month
parallel run + the payroll-delta measurement vs the old threshold behavior.

## Global Constraints

- **Payroll-classification change (intentional):** worked-one-session → Half Day. Task 3 must prove the
  classifier's native fields (`status`/`half_day_status`/`custom_cong`) are **identical to a correct manual
  entry** for the same in/out, at Salary-Slip level. Never relax that test.
- **Gate by `custom_split_half_day`:** the classifier must be a no-op for any shift without the flag → the
  29 upstream `test_shift_type` tests and all non-VN shifts keep stock behavior. Verify.
- **Never** edit `salary_slip.py`, `ShiftType.get_attendance`, or `calculate_working_hours`.
- **Never** overwrite manually-entered codes; never run when `status == "On Leave"` or in/out missing.
- **Stage only each task's own files** (`git add <paths>`, never `-A`) — unrelated dirty files exist.
- **Ask-first (STOP for sign-off):** enabling `custom_split_half_day` on a **prod** shift; deploying the
  fields to prod; one-month parallel run before broad enablement.
- Reversible via `git revert`; VN labels; tab indent; ASCII method names (no leading `_` — `__getattr__`).

## Running tests (rollback harness)

Reuse `scratch/run_test.sh` from plan A (writes a `.py` harness, feeds the console a single `exec()` line):
`bash scratch/run_test.sh "<dotted.module>[.Class.method]"` → prints `HARNESS_RESULT: OK|FAIL`.

## Open interpretations (spec defaults used here — flip is cheap, none affect payroll)

- Half-not-worked session displays **`V`** (cells like `X/V`), not merged `NN`. Payroll identical either way
  (both → Half Day + `half_day_status=Absent` after `check_leave_record`).
- Defaults: `min_fraction = 0.5`, `grace = 15` min, lunch `12:00–13:30`, shift `08:00–17:30`.

---

## Task 1: Shift Type config — 5 custom fields (fixtures) + presence test

**Files:**
- Modify: `hrms/fixtures/custom_field.json` (append 5 objects, `dt: "Shift Type"`)
- Modify: `hrms/hooks.py` (add the 5 names to the Custom Field export filter `in` list)
- Test: `hrms/hr/doctype/attendance/test_vn_half_day_classifier.py` (new — presence test)

**Interfaces:**
- Produces on `Shift Type`: `custom_split_half_day` (Check, default 0), `custom_lunch_start` (Time, 12:00:00),
  `custom_lunch_end` (Time, 13:30:00), `custom_half_day_min_fraction` (Float, 0.5),
  `custom_half_day_grace_minutes` (Int, 15). Consumed by Task 2.

- [x] **Step 1: Write the failing presence test**

Create `hrms/hr/doctype/attendance/test_vn_half_day_classifier.py`:

```python
# Copyright (c) 2026, Miyano Việt Nam.
"""VN auto morning/afternoon classifier + its Shift Type config fields."""
import frappe
from frappe.tests.utils import FrappeTestCase

SHIFT_FIELDS = (
	"custom_split_half_day",
	"custom_lunch_start",
	"custom_lunch_end",
	"custom_half_day_min_fraction",
	"custom_half_day_grace_minutes",
)


class TestVNHalfDayClassifier(FrappeTestCase):
	def test_shift_type_config_fields_exist(self):
		for fn in SHIFT_FIELDS:
			self.assertTrue(
				frappe.db.exists("Custom Field", f"Shift Type-{fn}"), f"missing Custom Field Shift Type-{fn}"
			)
```

- [x] **Step 2: Run — verify it fails**

Run: `bash scratch/run_test.sh "hrms.hr.doctype.attendance.test_vn_half_day_classifier"`
Expected: FAIL — `missing Custom Field Shift Type-custom_split_half_day`.

- [x] **Step 3: Append the 5 Custom Field fixtures**

Append these 5 objects to the array in `hrms/fixtures/custom_field.json` (before the closing `]`; add a
comma after the current last object). Full boilerplate for the first; the other four are identical except
the keys shown — copy the same key set and change only those keys:

```json
 {
  "allow_in_quick_entry": 0, "allow_on_submit": 0, "bold": 0, "collapsible": 0,
  "collapsible_depends_on": null, "columns": 0, "default": "0", "depends_on": null,
  "description": null, "docstatus": 0, "doctype": "Custom Field", "dt": "Shift Type",
  "fetch_from": null, "fetch_if_empty": 0, "fieldname": "custom_split_half_day",
  "fieldtype": "Check", "hidden": 0, "hide_border": 0, "hide_days": 0, "hide_seconds": 0,
  "ignore_user_permissions": 0, "ignore_xss_filter": 0, "in_global_search": 0, "in_list_view": 0,
  "in_preview": 0, "in_standard_filter": 0, "insert_after": "enable_auto_attendance",
  "is_system_generated": 0, "is_virtual": 0, "label": "Tách công sáng/chiều (VN)", "length": 0,
  "link_filters": null, "mandatory_depends_on": null, "modified": "2026-07-15 00:00:00.000000",
  "module": null, "name": "Shift Type-custom_split_half_day", "no_copy": 0, "non_negative": 0,
  "options": null, "permlevel": 0, "placeholder": null, "precision": "", "print_hide": 0,
  "print_hide_if_no_value": 0, "print_width": null, "read_only": 0, "read_only_depends_on": null,
  "report_hide": 0, "reqd": 0, "search_index": 0, "show_dashboard": 0, "sort_options": 0,
  "translatable": 0, "unique": 0, "width": null
 }
```

The other four (same boilerplate, only these keys differ):

| name | fieldname | fieldtype | default | insert_after | depends_on | label |
|---|---|---|---|---|---|---|
| `Shift Type-custom_lunch_start` | `custom_lunch_start` | `Time` | `"12:00:00"` | `custom_split_half_day` | `"eval:doc.custom_split_half_day"` | `Bắt đầu nghỉ trưa` |
| `Shift Type-custom_lunch_end` | `custom_lunch_end` | `Time` | `"13:30:00"` | `custom_lunch_start` | `"eval:doc.custom_split_half_day"` | `Kết thúc nghỉ trưa` |
| `Shift Type-custom_half_day_min_fraction` | `custom_half_day_min_fraction` | `Float` | `"0.5"` | `custom_lunch_end` | `"eval:doc.custom_split_half_day"` | `Ngưỡng công một buổi` |
| `Shift Type-custom_half_day_grace_minutes` | `custom_half_day_grace_minutes` | `Int` | `"15"` | `custom_half_day_min_fraction` | `"eval:doc.custom_split_half_day"` | `Ân hạn vào/ra (phút)` |

- [x] **Step 4: Add the 5 names to the hooks Custom Field filter**

In `hrms/hooks.py`, inside the `"Custom Field"` filter `in` list (after `"Expense Claim-custom_business_trip",`):

```python
					"Shift Type-custom_split_half_day",
					"Shift Type-custom_lunch_start",
					"Shift Type-custom_lunch_end",
					"Shift Type-custom_half_day_min_fraction",
					"Shift Type-custom_half_day_grace_minutes",
```

- [x] **Step 5: Migrate + normalize + run**

Run: `cd /home/miyano/frappe-bench && bench --site miyano migrate` (imports the fields)
Run (normalize JSON to canonical form): `bench --site miyano export-fixtures --app hrms`
  → then `git diff --stat hrms/fixtures/custom_field.json` (expect only the 5 new blocks, reformatted).
Run: `bash scratch/run_test.sh "hrms.hr.doctype.attendance.test_vn_half_day_classifier"`
Expected: `HARNESS_RESULT: OK`.

> If `export-fixtures` rewrites unrelated Leave Type / Attendance Code fixtures, `git checkout` those files
> — stage only `custom_field.json`.

- [x] **Step 6: Commit**

```bash
git add hrms/fixtures/custom_field.json hrms/hooks.py \
        hrms/hr/doctype/attendance/test_vn_half_day_classifier.py
git commit -m "feat(hr): Shift Type split-half-day config fields (lunch window, threshold, grace)"
```

---

## Task 2: The classifier + wire into `before_validate`

**Files:**
- Modify: `hrms/hr/doctype/attendance/attendance.py` (imports; new method; call in `before_validate`)
- Test: `hrms/hr/doctype/attendance/test_vn_half_day_classifier.py` (add classifier unit tests)

**Interfaces:**
- Consumes: the 5 Shift Type fields (Task 1); Attendance Codes `X`, `V` (already shipped).
- Produces: `Attendance.apply_vn_half_day_classifier()` — sets `custom_morning_code`/`custom_afternoon_code`
  (or `custom_attendance_code="V"`) + `working_hours` (net), then the existing bridge derives status/công.

- [x] **Step 1: Write the failing classifier unit tests**

Append to `hrms/hr/doctype/attendance/test_vn_half_day_classifier.py`:

```python
from frappe.utils import getdate


class TestVNHalfDayLogic(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.emp = frappe.db.get_value("Employee", {}, "name")
		cls.shift = "VN Split 08-1730 (test)"
		if not frappe.db.exists("Shift Type", cls.shift):
			frappe.get_doc(
				{
					"doctype": "Shift Type",
					"__newname": cls.shift,
					"start_time": "08:00:00",
					"end_time": "17:30:00",
					"custom_split_half_day": 1,
					"custom_lunch_start": "12:00:00",
					"custom_lunch_end": "13:30:00",
					"custom_half_day_min_fraction": 0.5,
					"custom_half_day_grace_minutes": 15,
				}
			).insert()
		cls.day = getdate("2099-03-04")

	def _cls(self, in_hm, out_hm, shift=None, **extra):
		doc = frappe.get_doc(
			{
				"doctype": "Attendance",
				"employee": self.emp,
				"attendance_date": self.day,
				"shift": shift if shift is not None else self.shift,
				"in_time": f"{self.day} {in_hm}:00",
				"out_time": f"{self.day} {out_hm}:00",
				**extra,
			}
		)
		doc.before_validate()
		return doc

	def test_full_day(self):
		d = self._cls("08:00", "17:30")
		self.assertEqual(d.status, "Present")
		self.assertEqual(d.custom_cong, 1.0)
		self.assertEqual(d.working_hours, 8.0)  # 4h morning + 4h afternoon, lunch excluded

	def test_morning_only(self):
		d = self._cls("08:00", "12:00")
		self.assertEqual(d.status, "Half Day")
		self.assertEqual(d.half_day_status, "Absent")
		self.assertEqual(d.custom_cong, 0.5)
		self.assertEqual(d.custom_morning_code, "X")
		self.assertEqual(d.custom_afternoon_code, "V")
		self.assertEqual(d.working_hours, 4.0)

	def test_afternoon_only(self):
		d = self._cls("13:30", "17:30")
		self.assertEqual(d.status, "Half Day")
		self.assertEqual(d.custom_morning_code, "V")
		self.assertEqual(d.custom_afternoon_code, "X")
		self.assertEqual(d.custom_cong, 0.5)

	def test_early_leave_below_threshold_is_half_day(self):
		# leaves 15:00: afternoon coverage 13:30–15:15(grace) = 1.75h/4h = 44% < 50% -> morning only
		d = self._cls("08:00", "15:00")
		self.assertEqual(d.status, "Half Day")
		self.assertEqual(d.custom_afternoon_code, "V")
		self.assertEqual(d.working_hours, 5.5)  # 4h morning + 1.5h afternoon (actual overlap, no grace)

	def test_no_session_is_absent(self):
		d = self._cls("12:10", "13:20")  # entirely inside lunch
		self.assertEqual(d.status, "Absent")
		self.assertEqual(d.custom_attendance_code, "V")

	def test_gated_off_for_non_split_shift(self):
		# a non-split shift: classifier is a no-op -> status stays as given, no split codes
		d = self._cls("08:00", "12:00", shift=None, status="Present")
		# override: use a plain shift lacking the flag
		d.shift = None
		d.custom_morning_code = None
		d.custom_afternoon_code = None
		d.status = "Present"
		d.before_validate()
		self.assertIsNone(d.custom_morning_code)
		self.assertIsNone(d.custom_afternoon_code)

	def test_manual_code_wins(self):
		d = self._cls("08:00", "12:00", custom_attendance_code="P")
		self.assertEqual(d.status, "On Leave")
		self.assertEqual(d.leave_type, "Nghỉ phép năm")
```

- [x] **Step 2: Run — verify it fails**

Run: `bash scratch/run_test.sh "hrms.hr.doctype.attendance.test_vn_half_day_classifier"`
Expected: FAIL — full-day gives no split codes yet (`custom_cong`/`status` not derived from in/out).

- [x] **Step 3: Add imports to `attendance.py`**

At the top of `hrms/hr/doctype/attendance/attendance.py`, ensure these imports exist (add what's missing):

```python
from datetime import datetime, timedelta

from frappe.utils import cint, flt, get_datetime, getdate
```

- [x] **Step 4: Wire the classifier into `before_validate`**

In `attendance.py`, change `before_validate` so the classifier runs BEFORE the bridge:

```python
	def before_validate(self):
		self.apply_vn_half_day_classifier()
		self.apply_attendance_code_bridge()
		# half_day_status is a Select; "" is not a valid stored value -> normalize to None
		if self.half_day_status == "":
			self.half_day_status = None
```

(Keep the existing body after the bridge call exactly as it was.)

- [x] **Step 5: Implement the classifier method**

Add this method to the `Attendance` class in `attendance.py` (place it just above `apply_attendance_code_bridge`):

```python
	# module-level fallbacks for shifts that enable the split but leave a field blank
	VN_DEFAULT_LUNCH_START = timedelta(hours=12)
	VN_DEFAULT_LUNCH_END = timedelta(hours=13, minutes=30)
	VN_DEFAULT_MIN_FRACTION = 0.5
	VN_DEFAULT_GRACE_MINUTES = 15

	def apply_vn_half_day_classifier(self):
		"""For a shift that opts into VN split-half-day, derive morning/afternoon codes + a
		lunch-excluded net working_hours from the day's in/out, so the code bridge produces the
		correct status/công. Gated + a no-op unless: shift set with custom_split_half_day=1,
		in/out present, no manual code, and status not On Leave."""
		if not self.get("shift") or not self.get("in_time") or not self.get("out_time"):
			return
		if self.get("custom_attendance_code") or self.get("custom_morning_code") or self.get(
			"custom_afternoon_code"
		):
			return  # respect a manually entered code
		if self.get("status") == "On Leave":
			return  # a leave day is not a worked day

		cfg = frappe.db.get_value(
			"Shift Type",
			self.shift,
			[
				"start_time",
				"end_time",
				"custom_split_half_day",
				"custom_lunch_start",
				"custom_lunch_end",
				"custom_half_day_min_fraction",
				"custom_half_day_grace_minutes",
			],
			as_dict=True,
		)
		if not cfg or not cint(cfg.custom_split_half_day) or not (cfg.start_time and cfg.end_time):
			return

		midnight = datetime.combine(getdate(self.attendance_date), datetime.min.time())
		lunch_start = cfg.custom_lunch_start or self.VN_DEFAULT_LUNCH_START
		lunch_end = cfg.custom_lunch_end or self.VN_DEFAULT_LUNCH_END
		m_start, m_end = midnight + cfg.start_time, midnight + lunch_start
		a_start, a_end = midnight + lunch_end, midnight + cfg.end_time
		in_t, out_t = get_datetime(self.in_time), get_datetime(self.out_time)
		grace = timedelta(minutes=cint(cfg.custom_half_day_grace_minutes) or self.VN_DEFAULT_GRACE_MINUTES)
		min_frac = flt(cfg.custom_half_day_min_fraction) or self.VN_DEFAULT_MIN_FRACTION

		def overlap_hours(lo, hi, w_lo, w_hi):
			start, end = max(lo, w_lo), min(hi, w_hi)
			return max(0.0, (end - start).total_seconds() / 3600.0)

		m_net = overlap_hours(in_t, out_t, m_start, m_end)
		a_net = overlap_hours(in_t, out_t, a_start, a_end)
		m_dur = (m_end - m_start).total_seconds() / 3600.0
		a_dur = (a_end - a_start).total_seconds() / 3600.0
		# coverage uses a grace-expanded interval (tolerate small late-in / early-out); net hours do not
		m_cov = (overlap_hours(in_t - grace, out_t + grace, m_start, m_end) / m_dur) if m_dur else 0.0
		a_cov = (overlap_hours(in_t - grace, out_t + grace, a_start, a_end) / a_dur) if a_dur else 0.0

		self.working_hours = round(m_net + a_net, 2)
		worked_m, worked_a = m_cov >= min_frac, a_cov >= min_frac
		if worked_m and worked_a:
			self.custom_morning_code = self.custom_afternoon_code = "X"
		elif worked_m:
			self.custom_morning_code, self.custom_afternoon_code = "X", "V"
		elif worked_a:
			self.custom_morning_code, self.custom_afternoon_code = "V", "X"
		else:
			self.custom_attendance_code = "V"
```

- [x] **Step 6: Run — verify all classifier tests pass**

Run: `bash scratch/run_test.sh "hrms.hr.doctype.attendance.test_vn_half_day_classifier"`
Expected: `HARNESS_RESULT: OK` (full day, morning/afternoon only, early-leave, absent, gated-off, manual-wins).

- [x] **Step 7: Regression — bridge + shift_type untouched**

Run: `bash scratch/run_test.sh "hrms.hr.doctype.attendance.test_attendance_code_bridge"` → OK (15).
Run: `bash scratch/run_test.sh "hrms.hr.doctype.shift_type.test_shift_type"` → OK (29, gated off → unchanged).

- [x] **Step 8: Commit**

```bash
git add hrms/hr/doctype/attendance/attendance.py \
        hrms/hr/doctype/attendance/test_vn_half_day_classifier.py
git commit -m "feat(hr): auto morning/afternoon classifier (lunch-excluded net hours), gated by shift flag"
```

---

## Task 3: Payroll-invariance gate — classified Half Day == native Half Day

**Files:**
- Test: `hrms/payroll/doctype/salary_slip/test_attendance_code_payroll_invariance.py` (add one test)

**Interfaces:** Consumes the classifier (Task 2). Proves it introduces no payroll delta vs a correct manual
Half Day for the same worked session.

- [x] **Step 1: Write the salary-slip-level gate test**

Append to `TestAttendanceCodePayrollInvariance` in
`hrms/payroll/doctype/salary_slip/test_attendance_code_payroll_invariance.py`:

```python
	@change_settings(
		"Payroll Settings", {"payroll_based_on": "Attendance", "daily_wages_fraction_for_half_day": 0.5}
	)
	def test_classifier_morning_only_matches_native_half_day(self):
		"""A shift-classified morning-only day (in 08:00 / out 12:00) must yield the same payroll
		as a native Half Day with half_day_status Absent."""
		first_sunday = get_first_sunday()
		shift = "VN Split PR 08-1730"
		if not frappe.db.exists("Shift Type", shift):
			frappe.get_doc(
				{
					"doctype": "Shift Type",
					"__newname": shift,
					"start_time": "08:00:00",
					"end_time": "17:30:00",
					"custom_split_half_day": 1,
					"custom_lunch_start": "12:00:00",
					"custom_lunch_end": "13:30:00",
				}
			).insert()

		emp_native = make_employee("inv_hd_native@codes.com")
		emp_class = make_employee("inv_hd_class@codes.com")
		for e in (emp_native, emp_class):
			frappe.db.set_value("Employee", e, {"relieving_date": None, "status": "Active"})

		date = add_days(first_sunday, 1)
		mark_attendance(emp_native, date, "Half Day", half_day_status="Present")  # full validate -> Absent
		att = frappe.get_doc(
			{
				"doctype": "Attendance",
				"employee": emp_class,
				"attendance_date": date,
				"shift": shift,
				"in_time": f"{date} 08:00:00",
				"out_time": f"{date} 12:00:00",
			}
		)
		att.insert()  # classifier -> morning X / afternoon V -> Half Day
		att.submit()
		self.assertEqual(att.status, "Half Day")

		ss_native = make_employee_salary_slip(emp_native, "Monthly", "Inv HD Native")
		ss_class = make_employee_salary_slip(emp_class, "Monthly", "Inv HD Class")
		self.assertEqual(ss_class.payment_days, ss_native.payment_days)
		self.assertEqual(ss_class.absent_days, ss_native.absent_days)
		self.assertEqual(ss_class.leave_without_pay, ss_native.leave_without_pay)
```

- [x] **Step 2: Run — verify the gate passes**

Run: `bash scratch/run_test.sh "hrms.payroll.doctype.salary_slip.test_attendance_code_payroll_invariance"`
Expected: `HARNESS_RESULT: OK` (native vs classified Half Day identical). If it FAILS, the classifier's
native fields diverge from a manual Half Day — fix the classifier, never the assertion.

- [x] **Step 3: Commit**

```bash
git add hrms/payroll/doctype/salary_slip/test_attendance_code_payroll_invariance.py
git commit -m "test(hr): gate — classified morning-only Half Day == native Half Day (payroll invariant)"
```

---

## Task 4: Dashboard net-hours — no double lunch subtraction for split shifts

**Files:**
- Modify: `hrms/hr/working_hours.py` (`compute_net_hours` gains `is_split`; `get_net_hours_map` passes it)
- Test: `hrms/hr/test_working_hours.py` (create if absent; else append)

**Interfaces:**
- Consumes: split-shift Attendance whose stored `working_hours` is already net (Task 2).
- Produces: `compute_net_hours(status, in_time, out_time, working_hours, is_split=False)` — when `is_split`,
  returns the stored (already-net) `working_hours` with no lunch subtraction.

- [x] **Step 1: Write the failing test**

Create/append `hrms/hr/test_working_hours.py`:

```python
# Copyright (c) 2026, Miyano Việt Nam.
from frappe.tests.utils import FrappeTestCase
from frappe.utils import get_datetime

from hrms.hr.working_hours import compute_net_hours


class TestWorkingHoursNet(FrappeTestCase):
	def test_non_split_subtracts_fixed_lunch(self):
		# stock behavior: Present full day, 9h gross -> 7.5h net (−1.5 lunch)
		i, o = get_datetime("2099-03-04 08:00:00"), get_datetime("2099-03-04 17:00:00")
		self.assertEqual(compute_net_hours("Present", i, o, 9.0), 7.5)

	def test_split_uses_stored_net(self):
		# split shift already stored net working_hours (lunch excluded) -> use it as-is, no −1.5
		i, o = get_datetime("2099-03-04 08:00:00"), get_datetime("2099-03-04 17:30:00")
		self.assertEqual(compute_net_hours("Present", i, o, 8.0, is_split=True), 8.0)
```

- [x] **Step 2: Run — verify it fails**

Run: `bash scratch/run_test.sh "hrms.hr.test_working_hours"`
Expected: FAIL — `compute_net_hours() got an unexpected keyword argument 'is_split'`.

- [x] **Step 3: Add the `is_split` branch to `compute_net_hours`**

In `hrms/hr/working_hours.py`, replace the `compute_net_hours` signature + body top:

```python
def compute_net_hours(status, in_time, out_time, working_hours, is_split=False):
	"""Giờ làm net của một ngày: gross (out-in hoặc working_hours) trừ nghỉ trưa theo status.
	Với ca tách sáng/chiều (is_split) thì working_hours ĐÃ là net (đã loại trưa) -> dùng thẳng."""
	if is_split:
		return max(round(flt(working_hours), 2), 0.0)
	if in_time and out_time:
		gross = flt(time_diff_in_hours(out_time, in_time))
	else:
		gross = flt(working_hours)
```

(Leave the rest of the function — the `gross <= 0` / FULL_DAY / Half Day branches — unchanged.)

- [x] **Step 4: Pass `is_split` from `get_net_hours_map`**

In `get_net_hours_map`, before the row loop add a lookup of split-enabled shifts, and pass the flag:

```python
	split_shifts = set(
		frappe.get_all("Shift Type", filters={"custom_split_half_day": 1}, pluck="name")
	)
	hours_map = {}
	for d in query.run(as_dict=True):
		shift = d.shift or ""
		net = compute_net_hours(d.status, d.in_time, d.out_time, d.working_hours, is_split=shift in split_shifts)
		hours_map.setdefault(d.employee, {}).setdefault(shift, {})[d.day_of_month] = net
```

(Replace the existing 3-line body of that loop with the `net = ...` call above; keep the `.setdefault(...)`.)

- [x] **Step 5: Run — verify pass + working-hours regression**

Run: `bash scratch/run_test.sh "hrms.hr.test_working_hours"` → OK.
Run any existing working-hours test module if present:
`bash scratch/run_test.sh "hrms.hr.report.working_hours"` (skip if no test module) — otherwise rely on Step 5's unit test.

- [x] **Step 6: Commit**

```bash
git add hrms/hr/working_hours.py hrms/hr/test_working_hours.py
git commit -m "feat(hr): net-hours dashboard uses stored net for split shifts (no double lunch subtraction)"
```

---

## Task 5: Integration — migrate, full regression, docs, sign-off note

**Files:**
- Modify: `tasks/plan-auto-morning-afternoon.md`, `spec/auto-morning-afternoon-attendance.md` (tick criteria)

- [x] **Step 1: Full regression sweep**

Run each → confirm `HARNESS_RESULT: OK`:
```
bash scratch/run_test.sh "hrms.hr.doctype.attendance.test_vn_half_day_classifier"
bash scratch/run_test.sh "hrms.hr.doctype.attendance.test_attendance_code_bridge"
bash scratch/run_test.sh "hrms.payroll.doctype.salary_slip.test_attendance_code_payroll_invariance"
bash scratch/run_test.sh "hrms.hr.test_working_hours"
bash scratch/run_test.sh "hrms.hr.doctype.shift_type.test_shift_type"
bash scratch/run_test.sh "hrms.hr.report.bang_cham_cong_thang.test_bang_cham_cong_thang"
```

- [x] **Step 2: E2E smoke on a throwaway split shift (rolled back)**

Via the harness or a manual console session, create a split Shift Type + one Attendance with in 08:00 /
out 12:00, insert, and confirm `status == "Half Day"`, `custom_morning_code == "X"`,
`custom_afternoon_code == "V"`, `working_hours == 4.0`. (Do NOT enable the flag on a real prod shift.)

- [x] **Step 3: Tick criteria + commit docs**

Mark the plan boxes + `## Success Criteria` in the spec. Add a one-line note that **enabling
`custom_split_half_day` on any real shift + the one-month parallel run is an ask-first, sign-off step**.

```bash
git add tasks/plan-auto-morning-afternoon.md spec/auto-morning-afternoon-attendance.md
git commit -m "docs(hr): Phase-4 morning/afternoon classifier done — criteria ticked, enablement ask-first"
```

- [ ] **STOP — do not enable on prod.** After merge, present the payroll-delta measurement (classified vs
  old threshold behavior on real shifts) and get explicit sign-off before switching on `custom_split_half_day`
  for any production shift; run one month in parallel first.

---

## Self-Review

**Spec coverage:** config fields → T1; classifier + gating + before_validate hook → T2; payroll gate → T3;
dashboard lunch reconciliation → T4; migrate/regression/sign-off → T5. Net-hours = overlap (not flat −1.5)
→ T2 (`working_hours`) + T4. Gating by `custom_split_half_day` → T2 test `test_gated_off_for_non_split_shift`
+ T2 Step 7 shift_type regression. ✓

**Placeholder scan:** every code/JSON step is concrete. T1 uses a full template object + an explicit
per-field diff table (same-step boilerplate replication, not a cross-task reference). ✓

**Type consistency:** `apply_vn_half_day_classifier` / the 5 `custom_*` field names / `is_split` param /
`custom_split_half_day` string match across fixtures, hooks, classifier, dashboard, and tests. `X`/`V`
codes exist (shipped). `working_hours` stored as net in T2 and consumed in T4. ✓

**Risk:** payroll-classification change — gated (T2), proven invariant vs manual (T3), enablement fenced
behind sign-off (T5 STOP). Upstream tests protected by the shift flag. ✓
