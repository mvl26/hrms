"""
Diagnose & fix: why do Employee Checkins get `skip_auto_attendance = 1`
even though nobody ticked the box?

Verified in HRMS source — `skip_auto_attendance` defaults to 0 and no client script sets it.
It becomes 1 only via:
  1. Manual tick by a user.
  2. Import via add_log_based_on_employee_field(..., skip_auto_attendance=1)  -> device/API.
  3. The hourly auto-attendance job: when Attendance creation raises a ValidationError
     (DuplicateAttendance / OverlappingShift / date < DOJ / inactive employee), the job
     rolls back, sets skip_auto_attendance=1 on those checkins, and writes a Comment with
     the exact reason.  (employee_checkin.py -> handle_attendance_exception)

RUN (on the production server, from the frappe-bench directory):

  # 1) Diagnose (read-only) — start here:
  bench --site <your-site> execute hrms.skip_attendance_diag.diagnose

  # 2) Preview which unlinked skipped checkins would be re-enabled (no change):
  bench --site <your-site> execute hrms.skip_attendance_diag.reset_wrongly_skipped

  # 3) Actually re-enable them so the hourly job reprocesses them:
  bench --site <your-site> execute hrms.skip_attendance_diag.reset_wrongly_skipped \
        --kwargs "{'apply': True}"

  # Optional filters on reset (any combination):
  --kwargs "{'apply': True, 'from_date': '2026-06-01', 'to_date': '2026-06-30', 'employee': 'HR-EMP-0001'}"
"""

import csv

import frappe

LINE = "=" * 64


def _skip_comment_map(names):
	"""Return {checkin_name: latest skip-comment content} for the given checkin names."""
	if not names:
		return {}
	rows = frappe.get_all(
		"Comment",
		filters={"reference_doctype": "Employee Checkin", "reference_name": ["in", names]},
		fields=["reference_name", "content", "creation"],
		order_by="creation asc",
	)
	out = {}
	for r in rows:
		out[r.reference_name] = (r.content or "").replace("\n", " ")
	return out


def _filter_by_comment(names, reason_contains, only_without_comment):
	"""Narrow `names` by their skip-comment (reason). No-op if neither filter is set."""
	if not names or not (reason_contains or only_without_comment):
		return names
	cmap = _skip_comment_map(names)
	if only_without_comment:
		return [n for n in names if n not in cmap]
	needle = (reason_contains or "").lower()
	return [n for n in names if needle in cmap.get(n, "").lower()]


def diagnose():
	"""Read-only report of how many checkins are skipped and WHY.

	Returns a dict of the headline counts (total, skipped, linked, nolink, offshift,
	no_comment, date_has_attendance) so it is usable programmatically and in tests.
	"""
	print("\n" + LINE)
	print("SKIP AUTO ATTENDANCE DIAGNOSTIC   site:", frappe.local.site)
	print(LINE)

	total = frappe.db.count("Employee Checkin")
	skipped = frappe.db.count("Employee Checkin", {"skip_auto_attendance": 1})
	pct = round(100 * skipped / total, 1) if total else 0
	print(f"Total checkins           : {total}")
	print(f"skip_auto_attendance = 1 : {skipped}  ({pct}%)")

	if not skipped:
		print("\nNo skipped checkins. Nothing to diagnose.")
		print(LINE + "\n")
		return {
			"total": total,
			"skipped": 0,
			"linked": 0,
			"nolink": 0,
			"offshift": 0,
			"no_comment": 0,
			"date_has_attendance": 0,
		}

	sk_linked = frappe.db.count("Employee Checkin", {"skip_auto_attendance": 1, "attendance": ["is", "set"]})
	# a skipped checkin is either linked or not, so derive nolink by subtraction:
	# frappe.db.count mishandles ["in", ["", None]] (SQL `IN (..,NULL)` never matches NULL).
	sk_nolink = skipped - sk_linked
	sk_offshift = frappe.db.count("Employee Checkin", {"skip_auto_attendance": 1, "offshift": 1})
	print(f"  - linked to an Attendance (legitimately done) : {sk_linked}")
	print(f"  - NOT linked (candidates to reprocess)        : {sk_nolink}")
	print(f"  - offshift=1 (no shift; job ignores anyway)   : {sk_offshift}")

	print("\n--- Reasons recorded on skipped checkins (Comments = ground truth) ---")
	rows = frappe.db.sql(
		"""
		SELECT c.content, COUNT(*) cnt
		FROM `tabComment` c
		WHERE c.reference_doctype='Employee Checkin'
		  AND c.reference_name IN (
			  SELECT name FROM `tabEmployee Checkin` WHERE skip_auto_attendance=1)
		GROUP BY c.content ORDER BY cnt DESC LIMIT 15
		""",
		as_dict=True,
	)
	if not rows:
		print("  (no comments on any skipped checkin)")
	for r in rows:
		print(f"  [{r.cnt}]  {(r.content or '').replace(chr(10), ' ')[:170]}")

	no_comment = frappe.db.sql(
		"""
		SELECT COUNT(*) FROM `tabEmployee Checkin` ec
		WHERE ec.skip_auto_attendance=1
		  AND NOT EXISTS (SELECT 1 FROM `tabComment` c
			  WHERE c.reference_doctype='Employee Checkin' AND c.reference_name=ec.name)
		"""
	)[0][0]
	print(f"\nSkipped checkins WITHOUT any comment : {no_comment}")
	print("  -> high here  => imported with skip_auto_attendance=1 by the device/API,")
	print("                   NOT skipped by the hourly job (path #2). Fix the integration.")

	dup = frappe.db.sql(
		"""
		SELECT COUNT(DISTINCT ec.name)
		FROM `tabEmployee Checkin` ec
		JOIN `tabAttendance` a
		  ON a.employee = ec.employee
		 AND a.attendance_date = DATE(ec.time)
		 AND a.docstatus < 2
		WHERE ec.skip_auto_attendance=1
		  AND (ec.attendance IS NULL OR ec.attendance='')
		"""
	)[0][0]
	print(f"\nSkipped (unlinked) checkins whose date ALREADY has an Attendance : {dup}")
	print("  -> high here  => DuplicateAttendanceError is the cause (path #3).")
	print(LINE + "\n")
	return {
		"total": total,
		"skipped": skipped,
		"linked": sk_linked,
		"nolink": sk_nolink,
		"offshift": sk_offshift,
		"no_comment": no_comment,
		"date_has_attendance": dup,
	}


def reset_wrongly_skipped(
	from_date=None,
	to_date=None,
	employee=None,
	shift=None,
	reason_contains=None,
	only_without_comment=False,
	require_no_existing_attendance=True,
	apply=False,
):
	"""Set skip_auto_attendance back to 0 so the hourly auto-attendance job reprocesses them.

	Safe by design: only touches checkins NOT yet linked to an Attendance, so it never
	disturbs already-processed records. Dry-run unless apply=True.

	Returns the list of matched checkin names (whether or not apply=True), so callers/tests
	can assert on the selection without changing data.

	Surgical targeting (combine as needed):
	  from_date/to_date/employee/shift : scope by time window, employee, or shift.
	  only_without_comment=True        : reset ONLY checkins with no skip-comment
	                                     (i.e. device/API imports, path #2 — safest reset).
	  reason_contains="already marked" : reset ONLY checkins whose skip-comment matches
	                                     this substring (target one specific cause you fixed).
	  require_no_existing_attendance   : skip checkins whose date already has an Attendance
	                                     (avoids immediately re-hitting DuplicateAttendanceError).
	"""
	filters = {"skip_auto_attendance": 1, "attendance": ["is", "not set"]}
	if employee:
		filters["employee"] = employee
	if shift:
		filters["shift"] = shift
	if from_date and to_date:
		filters["time"] = ["between", [from_date, to_date]]
	elif from_date:
		filters["time"] = [">=", from_date]
	elif to_date:
		filters["time"] = ["<=", to_date]

	names = frappe.get_all("Employee Checkin", filters=filters, pluck="name")
	names = _filter_by_comment(names, reason_contains, only_without_comment)

	if require_no_existing_attendance and names:
		rows = frappe.get_all(
			"Employee Checkin", filters={"name": ["in", names]}, fields=["name", "employee", "time"]
		)
		names = [
			r.name
			for r in rows
			if not frappe.db.exists(
				"Attendance",
				{
					"employee": r.employee,
					"attendance_date": frappe.utils.getdate(r.time),
					"docstatus": ["<", 2],
				},
			)
		]

	print(f"\n[reset_wrongly_skipped] site={frappe.local.site}  matched={len(names)}  apply={apply}")
	print(
		f"  filters: from={from_date} to={to_date} employee={employee} shift={shift} "
		f"reason_contains={reason_contains!r} only_without_comment={only_without_comment} "
		f"require_no_existing_attendance={require_no_existing_attendance}"
	)
	if not names:
		print("  Nothing to reset with these filters.")
		return names

	if not apply:
		print("  DRY RUN — nothing changed. Sample that WOULD be re-enabled:")
		for n in names[:10]:
			print("   ", n)
		print(f"  Re-run with --kwargs \"{{'apply': True}}\" to apply to all {len(names)}.")
		return names

	frappe.db.set_value(
		"Employee Checkin", {"name": ["in", names]}, "skip_auto_attendance", 0, update_modified=False
	)
	# commit chủ đích: công cụ chạy ngoài request cycle (bench execute), ghi từng phần để lần chạy dài không mất việc đã làm
	frappe.db.commit()  # nosemgrep
	print(f"  DONE — reset skip_auto_attendance=0 on {len(names)} checkins.")
	print("  They will be reprocessed on the next hourly auto-attendance run,")
	print("  or trigger now via Shift Type -> Mark Attendance / process_auto_attendance.")
	return names


def export_csv(path="/tmp/skipped_checkins.csv"):
	"""Dump every skipped checkin with its reason to a CSV for eyeballing in a spreadsheet.

	bench --site <site> execute hrms.skip_attendance_diag.export_csv
	bench --site <site> execute hrms.skip_attendance_diag.export_csv --kwargs "{'path': '/tmp/x.csv'}"
	"""
	rows = frappe.get_all(
		"Employee Checkin",
		filters={"skip_auto_attendance": 1},
		fields=["name", "employee", "employee_name", "time", "shift", "log_type", "attendance", "offshift"],
		order_by="time asc",
	)
	cmap = _skip_comment_map([r.name for r in rows])
	# đường dẫn do quản trị viên truyền khi chạy bench execute, không đến từ request
	with open(path, "w", newline="") as f:  # nosemgrep
		w = csv.writer(f)
		w.writerow(
			[
				"checkin",
				"employee",
				"employee_name",
				"time",
				"shift",
				"log_type",
				"linked_attendance",
				"offshift",
				"skip_reason_comment",
			]
		)
		for r in rows:
			w.writerow(
				[
					r.name,
					r.employee,
					r.employee_name,
					r.time,
					r.shift,
					r.log_type,
					r.attendance or "",
					r.offshift,
					cmap.get(r.name, ""),
				]
			)
	print(f"Wrote {len(rows)} skipped checkins -> {path}")
