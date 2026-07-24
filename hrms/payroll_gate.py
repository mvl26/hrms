# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# For license information, please see license.txt
"""Verification tooling for the prod payroll sign-off gates (`tasks/plan-prod-deploy.md`).

Read-only against the database — the only thing written is the snapshot file you name.

**T1/T2 — payroll must not move across a migrate.**

	# before the migrate
	bench --site <prod> execute hrms.payroll_gate.capture_payroll_baseline \
		--kwargs "{'path': '/tmp/payroll-baseline.json'}"
	# after the migrate — must report identical=True
	bench --site <prod> execute hrms.payroll_gate.compare_payroll_baseline \
		--kwargs "{'path': '/tmp/payroll-baseline.json'}"

**T4 — the VN morning/afternoon classifier must not move payroll.**

	bench --site <prod> execute hrms.payroll_gate.classifier_delta \
		--kwargs "{'year': 2026, 'month': 9, 'shift': 'Ca Hành Chính'}"

`classifier_delta` replays each day's real check-ins through the *upstream* threshold rule
(`ShiftType.get_attendance`, called directly so it can never drift from upstream) and compares the
result with the Attendance actually stored. Payroll reads only `status` / `leave_type` /
`half_day_status`, so if every day's triple matches, payroll is unchanged by definition.
"""

import hashlib
import json
from collections import defaultdict
from contextlib import contextmanager

import frappe
from frappe.utils import flt, get_first_day, get_last_day, getdate

# Salary Slip fields the attendance work is allowed to be judged on. gross_pay/net_pay are
# snapshotted for context but excluded from the verdict — they move for unrelated pay-rate reasons.
PAYROLL_GATE_FIELDS = ("payment_days", "absent_days", "leave_without_pay")
SNAPSHOT_FIELDS = ("name", "employee", "start_date", *PAYROLL_GATE_FIELDS, "gross_pay", "net_pay")

# The payroll-relevant triple. Everything else on Attendance is display-only.
PAYROLL_ATTENDANCE_FIELDS = ("status", "half_day_status", "leave_type")


def get_payroll_rows(company: str | None = None) -> list[dict]:
	"""Every submitted Salary Slip's payroll figures, ordered so snapshots are comparable."""
	filters = {"docstatus": 1}
	if company:
		filters["company"] = company

	rows = frappe.get_all("Salary Slip", filters=filters, fields=list(SNAPSHOT_FIELDS), order_by="name")
	return [{k: (str(v) if k == "start_date" and v else v) for k, v in row.items()} for row in rows]


def checksum_rows(rows: list[dict]) -> str:
	payload = json.dumps(rows, sort_keys=True, default=str, ensure_ascii=False)
	return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def capture_payroll_baseline(path: str, company: str | None = None) -> dict:
	"""T1: snapshot every submitted Salary Slip to `path` so a later run can prove nothing moved."""
	rows = get_payroll_rows(company)
	snapshot = {"company": company, "count": len(rows), "checksum": checksum_rows(rows), "rows": rows}

	with open(path, "w", encoding="utf-8") as f:
		json.dump(snapshot, f, ensure_ascii=False, indent=2, default=str)

	result = {"path": path, "count": snapshot["count"], "checksum": snapshot["checksum"]}
	print(f"[payroll_gate] captured {result['count']} slips -> {path}\n  checksum {result['checksum']}")
	return result


def diff_payroll_rows(before: list[dict], after: list[dict]) -> dict:
	"""Compare two snapshots on PAYROLL_GATE_FIELDS only. Pure — no database access."""
	before_by_name = {r["name"]: r for r in before}
	after_by_name = {r["name"]: r for r in after}

	changed = []
	for name in sorted(before_by_name.keys() & after_by_name.keys()):
		b, a = before_by_name[name], after_by_name[name]
		moved = {
			field: {"before": b.get(field), "after": a.get(field)}
			for field in PAYROLL_GATE_FIELDS
			if b.get(field) != a.get(field)
		}
		if moved:
			changed.append({"name": name, "employee": b.get("employee"), "fields": moved})

	missing = [before_by_name[n] for n in sorted(before_by_name.keys() - after_by_name.keys())]
	added = [after_by_name[n] for n in sorted(after_by_name.keys() - before_by_name.keys())]

	return {
		"identical": not (changed or missing or added),
		"changed": changed,
		"missing": missing,
		"added": added,
	}


def compare_payroll_baseline(path: str, company: str | None = None) -> dict:
	"""T1/T2: re-read the current slips and diff them against the snapshot saved at `path`."""
	with open(path, encoding="utf-8") as f:
		snapshot = json.load(f)

	result = diff_payroll_rows(snapshot["rows"], get_payroll_rows(company or snapshot.get("company")))
	verdict = "IDENTICAL" if result["identical"] else "DRIFTED"
	print(
		f"[payroll_gate] {verdict} — changed={len(result['changed'])} "
		f"missing={len(result['missing'])} added={len(result['added'])}"
	)
	for change in result["changed"]:
		print(f"  {change['name']} ({change['employee']}): {change['fields']}")
	return result


def get_checkins_for_attendance(attendance: str) -> list[dict]:
	"""The check-in logs `process_auto_attendance` linked to this Attendance, in the shape
	`ShiftType.get_attendance` expects."""
	return frappe.get_all(
		"Employee Checkin",
		filters={"attendance": attendance},
		fields=["name", "employee", "log_type", "time", "shift", "shift_start", "shift_end"],
		order_by="time",
	)


def classifier_delta(year: int, month: int, shift: str, company: str | None = None) -> dict:
	"""T4: for one month on one shift, compare each stored Attendance against what the upstream
	threshold rule would have produced from the very same check-ins.

	Only days whose Attendance came from check-ins are examined — a day with no linked check-in
	has no upstream counterfactual to compare against, so it is counted as skipped, not as a match.
	"""
	start, end = (
		get_first_day(getdate(f"{year}-{month:02d}-01")),
		get_last_day(getdate(f"{year}-{month:02d}-01")),
	)

	filters = {"attendance_date": ["between", [start, end]], "shift": shift, "docstatus": ["<", 2]}
	if company:
		filters["company"] = company

	records = frappe.get_all(
		"Attendance",
		filters=filters,
		fields=["name", "employee", "attendance_date", *PAYROLL_ATTENDANCE_FIELDS],
		order_by="employee, attendance_date",
	)

	shift_doc = frappe.get_cached_doc("Shift Type", shift)
	differing, skipped = [], []
	summary = defaultdict(lambda: {"actual": defaultdict(int), "threshold": defaultdict(int)})

	for record in records:
		logs = get_checkins_for_attendance(record.name)
		if not logs:
			skipped.append(
				{"attendance": record.name, "employee": record.employee, "date": str(record.attendance_date)}
			)
			continue

		threshold_status = shift_doc.get_attendance(logs)[0]
		actual = {field: record.get(field) for field in PAYROLL_ATTENDANCE_FIELDS}
		# upstream auto-attendance never assigns a leave type, and leaves half_day_status unset
		threshold = {"status": threshold_status, "half_day_status": None, "leave_type": None}

		summary[record.employee]["actual"][actual["status"]] += 1
		summary[record.employee]["threshold"][threshold_status] += 1

		if actual != threshold:
			differing.append(
				{
					"attendance": record.name,
					"employee": record.employee,
					"date": str(record.attendance_date),
					"actual": actual,
					"threshold": threshold,
				}
			)

	# Examining nothing proves nothing: a gate that reads "clean" without replaying a single day
	# would wave through exactly the risk it exists to catch.
	days_examined = len(records) - len(skipped)
	conclusive = days_examined > 0
	verdict = "no-delta" if conclusive and not differing else "delta" if differing else "inconclusive"

	report = {
		"shift": shift,
		"period": f"{start} .. {end}",
		"days_examined": days_examined,
		"skipped_no_checkins": skipped,
		"conclusive": conclusive,
		"verdict": verdict,
		"payroll_identical": not differing,
		"differing": differing,
		"summary": {emp: {k: dict(v) for k, v in counts.items()} for emp, counts in summary.items()},
	}

	headline = {
		"no-delta": "NO PAYROLL DELTA",
		"delta": "PAYROLL DELTA FOUND",
		"inconclusive": "INCONCLUSIVE — no day could be replayed, nothing was verified",
	}[verdict]
	print(
		f"[payroll_gate] {shift} {report['period']}: {headline} — "
		f"examined={days_examined} differing={len(differing)} skipped={len(skipped)}"
	)
	for diff in differing[:20]:
		print(f"  {diff['date']} {diff['employee']}: {diff['actual']} vs threshold {diff['threshold']}")
	return report


# ── T5 — what would switching `payroll_based_on` to "Attendance" actually cost? ───────────────
# The mã công only reach payroll when Payroll Settings reads Attendance instead of Leave. Flipping
# that on a live site is a sign-off gate, so this answers the question WITHOUT flipping anything:
# it computes each employee's day-figures under both modes purely in memory.

# Day-figures a Salary Slip derives before any money is involved — comparable without a salary
# structure, which is what makes this runnable on a site where payroll has never been set up.
PAYROLL_DAY_FIELDS = ("total_working_days", "payment_days", "absent_days", "leave_without_pay")


@contextmanager
def payroll_mode(mode: str, consider_unmarked_attendance_as: str | None = None):
	"""Make Salary Slip read `payroll_based_on = mode` **in memory only** — never writes.

	`SalarySlip.get_working_days_details` pulls the setting through `frappe.get_cached_value`, so
	shadowing that read is enough to simulate the other mode. The stored setting is untouched,
	which is what makes this safe to point at real payroll data.
	"""
	real = frappe.get_cached_value

	def patched(doctype, name=None, fieldname="name", *args, **kwargs):
		value = real(doctype, name, fieldname, *args, **kwargs)
		if doctype != "Payroll Settings" or not isinstance(value, dict):
			return value
		# copy: mutating the cached dict in place would poison payroll for the whole process
		simulated = frappe._dict(value)
		simulated.payroll_based_on = mode
		if consider_unmarked_attendance_as:
			simulated.consider_unmarked_attendance_as = consider_unmarked_attendance_as
		return simulated

	frappe.get_cached_value = patched
	try:
		yield
	finally:
		frappe.get_cached_value = real


def employee_day_figures(employee: str, company: str, start, end) -> dict:
	"""The payroll day-figures for one employee over one period, from an UNSAVED Salary Slip."""
	slip = frappe.new_doc("Salary Slip")
	slip.employee = employee
	slip.company = company
	slip.start_date = start
	slip.end_date = end
	slip.get_working_days_details()
	return {field: flt(slip.get(field)) for field in PAYROLL_DAY_FIELDS}


def simulate_payroll_mode_delta(
	year: int,
	month: int,
	company: str | None = None,
	employees: list[str] | None = None,
	mode_a: str = "Leave",
	mode_b: str = "Attendance",
) -> dict:
	"""T5: per employee, the payroll day-figures under `mode_a` vs `mode_b` for one real month.

	Read-only — no setting is changed and no Salary Slip is saved, so this is safe on live data.
	Run it before asking for sign-off to switch a site onto attendance-driven payroll:

		bench --site <site> execute hrms.payroll_gate.simulate_payroll_mode_delta \
			--kwargs "{'year': 2026, 'month': 7, 'company': 'Miyano'}"
	"""
	start = get_first_day(getdate(f"{year}-{month:02d}-01"))
	end = get_last_day(start)

	if not employees:
		filters = {"status": "Active"}
		if company:
			filters["company"] = company
		employees = [e.name for e in frappe.get_all("Employee", filters=filters, fields=["name"])]

	rows, failed = [], []
	for employee in sorted(employees):
		emp_company = company or frappe.db.get_value("Employee", employee, "company")
		try:
			with payroll_mode(mode_a):
				figures_a = employee_day_figures(employee, emp_company, start, end)
			with payroll_mode(mode_b):
				figures_b = employee_day_figures(employee, emp_company, start, end)
		except Exception as e:  # one bad employee must not sink the whole report
			failed.append({"employee": employee, "error": str(e)})
			continue

		delta = {field: flt(figures_b[field]) - flt(figures_a[field]) for field in PAYROLL_DAY_FIELDS}
		rows.append(
			{
				"employee": employee,
				"employee_name": frappe.db.get_value("Employee", employee, "employee_name"),
				"marked_days": frappe.db.count(
					"Attendance",
					{"employee": employee, "attendance_date": ["between", [start, end]], "docstatus": 1},
				),
				mode_a: figures_a,
				mode_b: figures_b,
				"delta": delta,
				"changed": any(round(v, 6) for v in delta.values()),
			}
		)

	changed = [r for r in rows if r["changed"]]
	report = {
		"period": f"{start} .. {end}",
		"company": company,
		"modes": [mode_a, mode_b],
		"employees_examined": len(rows),
		"employees_changed": len(changed),
		"payroll_identical": not changed,
		"rows": rows,
		"failed": failed,
	}

	print(
		f"[payroll_gate] {mode_a} → {mode_b} {report['period']}: "
		f"{'NO CHANGE' if report['payroll_identical'] else 'PAID DAYS WOULD CHANGE'} — "
		f"examined={len(rows)} changed={len(changed)} failed={len(failed)}"
	)
	for row in changed:
		moved = {f: v for f, v in row["delta"].items() if round(v, 6)}
		print(f"  {row['employee']} ({row['employee_name']}) marked={row['marked_days']}: {moved}")
	for bad in failed:
		print(f"  !! {bad['employee']}: {bad['error']}")
	return report
