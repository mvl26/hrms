"""Backfill the mã-công display fields on Attendance records that predate the VN
attendance-code feature (or were created by auto-attendance / leave applications).

Reverse-derives the code from (status, leave_type) exactly like Attendance.before_validate,
and writes ONLY the two display fields `custom_attendance_code` + `custom_work_credit` — never
status / leave_type / half_day_status — so payroll is provably untouched. Idempotent: only
fills rows whose code is still empty; manually-set codes are preserved. Supports a dry run.
"""

import frappe
from frappe.utils import flt


def execute():
	backfill()


def backfill(dry_run: bool = False) -> dict:
	"""Fill custom_attendance_code / custom_work_credit on code-less Attendance. Returns {code: rows}."""
	if not frappe.db.has_column("Attendance", "custom_attendance_code"):
		return {}

	codes = frappe.get_all(
		"Attendance Code", fields=["name", "maps_to_status", "leave_type", "work_fraction"]
	)
	summary = {}
	for c in codes:
		conds = [
			"docstatus < 2",
			"status = %(status)s",
			"(custom_attendance_code is null or custom_attendance_code = '')",
			"(custom_morning_code is null or custom_morning_code = '')",
			"(custom_afternoon_code is null or custom_afternoon_code = '')",
		]
		params = {"status": c.maps_to_status, "code": c.name, "cong": flt(c.work_fraction)}
		if c.leave_type:
			conds.append("leave_type = %(lt)s")
			params["lt"] = c.leave_type
		else:
			conds.append("(leave_type is null or leave_type = '')")
		where = " and ".join(conds)

		n = frappe.db.sql(f"select count(*) from `tabAttendance` where {where}", params)[0][0]
		if not n:
			continue
		summary[c.name] = n
		if not dry_run:
			frappe.db.sql(
				f"update `tabAttendance` set custom_attendance_code = %(code)s, custom_work_credit = %(cong)s where {where}",
				params,
			)
	return summary
