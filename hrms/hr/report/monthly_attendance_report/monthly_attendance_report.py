# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt
"""Bảng chấm công tháng — read-only monthly timekeeping sheet.

Pivots by employee × day-of-month. Each cell is the mã công for that day:
- a real Attendance record → its code (or morning/afternoon codes, e.g. "X/P");
- otherwise a calendar marker derived (NOT stored) from the employee's data:
  `-` on a weekly-off (rest day) or after the relieving date, `NL` on a public holiday.

Totals columns sum per category: Công = actual worked công (Σ work_fraction), and the unworked
remainder of each half goes to that code's own category — or to Vắng when the code is itself a
"Công" code that only covers half a day (NN), so every attended day still adds up to a full công.
Read-only: never writes, so it is safe against payroll and existing data.
"""

from calendar import monthrange

import frappe
from frappe import _
from frappe.utils import cint, flt, getdate
from frappe.utils.nestedset import get_descendants_of

from erpnext.setup.doctype.employee.employee import get_holiday_list_for_employee

Filters = frappe._dict

# display-only markers derived from the calendar, not Attendance Code master records
MARKER_TERMINATED = "-"  # after relieving_date — HR convention: rest-day dash
MARKER_WEEKLY_OFF = "-"  # nghỉ hàng tuần (CN/T7) — HR convention: rest-day dash
MARKER_HOLIDAY = "NL"  # ngày nghỉ lễ có lương — kept distinct so paid holidays stay visible

# Loại nhận phần không đi làm của một mã thuộc loại "Công" (mã V cũng thuộc loại này)
CATEGORY_UNEXCUSED = "Vắng"

# Nghỉ lễ hưởng lương — suy từ Holiday List (không phải Attendance Code), đếm riêng một cột
CATEGORY_HOLIDAY = "Nghỉ lễ"


def execute(filters: Filters | None = None) -> tuple:
	filters = frappe._dict(filters or {})
	if not (filters.month and filters.year):
		frappe.throw(_("Please select month and year."))

	year, month = cint(filters.year), cint(filters.month)
	days = monthrange(year, month)[1]

	categories = get_categories(get_code_map())
	rows = get_sheet_rows(filters)

	columns = get_columns(days, categories)
	data = _rows_to_report_data(rows, days, categories)
	return columns, data


def get_code_map() -> dict:
	"""{code: {category, work_fraction, maps_to_status, leave_type}} for every Attendance Code."""
	rows = frappe.get_all(
		"Attendance Code",
		fields=["name", "category", "work_fraction", "maps_to_status", "leave_type"],
	)
	return {r.name: r for r in rows}


def get_categories(code_map: dict) -> list[str]:
	# stable, human order first; then any extra categories present in the data (incl. Nghỉ lễ,
	# a calendar-derived category not backed by an Attendance Code — always shown, appended last)
	preferred = ["Công", "Phép", "Việc riêng", "Ốm", "Thai sản", "Tai nạn LĐ", "Nghỉ bù", "Không lương", "Vắng"]
	present = {r.category for r in code_map.values() if r.category}
	present.add(CATEGORY_HOLIDAY)
	ordered = [c for c in preferred if c in present]
	ordered += sorted(present - set(preferred))
	return ordered


def _company_filter(filters: Filters) -> list | None:
	if not filters.get("company"):
		return None
	companies = [filters.company]
	if filters.get("include_company_descendants"):
		companies += get_descendants_of("Company", filters.company)
	return companies


def get_employees(filters: Filters, start, end) -> list:
	"""Roster to render: everyone employed at some point during the month (joined on/before
	month-end and not relieved before month-start), optionally scoped to a company tree."""
	conds = [["Employee", "date_of_joining", "<=", end]]
	companies = _company_filter(filters)
	if companies:
		conds.append(["Employee", "company", "in", companies])
	return frappe.get_all(
		"Employee",
		filters=conds,
		or_filters=[
			["Employee", "relieving_date", "is", "not set"],
			["Employee", "relieving_date", ">=", start],
		],
		fields=["name", "employee_name", "holiday_list", "relieving_date", "date_of_joining"],
		order_by="employee_name",
	)


def get_attendances(filters: Filters, start, end) -> dict:
	"""{employee: {day-of-month: attendance}} for the month.

	Only submitted Attendance (docstatus==1) is counted — the same rows payroll reads. A draft
	may never be submitted (or gets cancelled), so counting it would let a frozen sheet diverge
	from the Salary Slip; the upstream Monthly Attendance Sheet report filters the same way."""
	q = {"attendance_date": ["between", [start, end]], "docstatus": 1}
	companies = _company_filter(filters)
	if companies:
		q["company"] = ["in", companies]

	rows = frappe.get_all(
		"Attendance",
		filters=q,
		fields=[
			"employee",
			"attendance_date",
			"status",
			"leave_type",
			"custom_attendance_code",
			"custom_morning_code",
			"custom_afternoon_code",
		],
	)
	by_emp = {}
	for a in rows:
		by_emp.setdefault(a.employee, {})[getdate(a.attendance_date).day] = a
	return by_emp


def get_holidays(employees: list, start, end) -> dict:
	"""{employee: {day-of-month: is_weekly_off}} from each employee's resolved Holiday List."""
	cache = {}
	result = {}
	for e in employees:
		hl = e.holiday_list or get_holiday_list_for_employee(e.name, raise_exception=False)
		if not hl:
			result[e.name] = {}
			continue
		if hl not in cache:
			rows = frappe.get_all(
				"Holiday",
				filters={"parent": hl, "parenttype": "Holiday List", "holiday_date": ["between", [start, end]]},
				fields=["holiday_date", "weekly_off"],
			)
			cache[hl] = {getdate(r.holiday_date).day: cint(r.weekly_off) for r in rows}
		result[e.name] = cache[hl]
	return result


def get_columns(days: int, categories: list[str]) -> list:
	columns = [
		{"fieldname": "employee", "label": _("Mã NV"), "fieldtype": "Link", "options": "Employee", "width": 110},
		{"fieldname": "employee_name", "label": _("Nhân viên"), "fieldtype": "Data", "width": 180},
	]
	for day in range(1, days + 1):
		columns.append({"fieldname": f"day_{day}", "label": str(day), "fieldtype": "Data", "width": 45})
	for idx, cat in enumerate(categories):
		columns.append({"fieldname": f"cat_{idx}", "label": cat, "fieldtype": "Float", "width": 80, "precision": 2})
	return columns


def _resolve_day(att, code_map: dict) -> tuple:
	"""Return (display, morning_code, afternoon_code) for one attendance, mirroring the bridge:
	explicit morning/afternoon win, then a single day code, else reverse-derive from status."""
	morning = att.custom_morning_code or att.custom_attendance_code
	afternoon = att.custom_afternoon_code or att.custom_attendance_code
	if not (morning or afternoon):
		derived = _reverse_code(att.status, att.leave_type, code_map)
		morning = afternoon = derived
	else:
		morning = morning or afternoon
		afternoon = afternoon or morning

	if not morning:
		return "", None, None
	display = morning if morning == afternoon else f"{morning}/{afternoon}"
	return display, morning, afternoon


def _reverse_code(status, leave_type, code_map: dict):
	if not status:
		return None
	for name, r in code_map.items():
		if r.maps_to_status == status and (r.leave_type or None) == (leave_type or None):
			return name
	return None


def get_sheet_rows(filters: Filters) -> list[dict]:
	"""Semantic per-employee rows shared by this report AND the Bảng Công Tháng DocType:
	``{employee, employee_name, days: {day-of-month: symbol}, totals: {category: float}}``.
	Công total = Σ work_fraction × 0.5 (worked-công); the unworked remainder (1 − work_fraction) × 0.5
	of each half lands in that code's category, falling back to Vắng for a half-covering "Công" code.
	This is the single source of timekeeping derivation — consumers must not re-implement it."""
	filters = frappe._dict(filters or {})
	year, month = cint(filters.year), cint(filters.month)
	days = monthrange(year, month)[1]
	start = getdate(f"{year}-{month:02d}-01")
	end = getdate(f"{year}-{month:02d}-{days:02d}")

	code_map = get_code_map()
	employees = get_employees(filters, start, end)
	attendances = get_attendances(filters, start, end)
	holidays = get_holidays(employees, start, end)

	rows = []
	for e in employees:
		emp_att = attendances.get(e.name, {})
		emp_hol = holidays.get(e.name, {})
		relieving = getdate(e.relieving_date) if e.relieving_date else None
		joining = getdate(e.date_of_joining) if e.date_of_joining else None
		day_syms = {}
		totals = {}

		for day in range(1, days + 1):
			d = getdate(f"{year}-{month:02d}-{day:02d}")
			# priority: đã ngừng việc > bản ghi Attendance > ngày lễ/CN > (trước khi vào làm →) trống
			if relieving and d > relieving:
				day_syms[day] = MARKER_TERMINATED
				continue
			att = emp_att.get(day)
			if att:
				display, morning, afternoon = _resolve_day(att, code_map)
				day_syms[day] = display
				for half in (morning, afternoon):
					c = code_map.get(half)
					if not c:
						continue
					wf = flt(c.work_fraction)
					totals["Công"] = totals.get("Công", 0.0) + wf * 0.5  # công thực đi làm
					rest = (1 - wf) * 0.5  # phần không đi làm của nửa buổi này
					if rest:
						# Mã nghỉ (P, Ô, 1/2P…) ghi vào đúng loại của nó. Mã thuộc loại "Công" mà
						# không làm đủ buổi (NN = làm nửa ngày) không nói nửa kia nghỉ vì gì, nên
						# nửa đó là nghỉ không lý do -> Vắng. Thiếu nhánh này thì ngày NN chỉ quy ra
						# 0.5 công và dòng bảng công không cân về số ngày công của tháng.
						bucket = c.category if c.category != "Công" else CATEGORY_UNEXCUSED
						totals[bucket] = totals.get(bucket, 0.0) + rest
			elif joining and d < joining:
				continue  # chưa vào làm → để trống
			elif day in emp_hol:
				if emp_hol[day]:
					day_syms[day] = MARKER_WEEKLY_OFF  # nghỉ hàng tuần (CN) — không tính công
				else:
					# nghỉ lễ hưởng lương → đếm vào cột "Nghỉ lễ" (nghỉ nhưng vẫn hưởng lương)
					day_syms[day] = MARKER_HOLIDAY
					totals[CATEGORY_HOLIDAY] = totals.get(CATEGORY_HOLIDAY, 0.0) + 1.0

		rows.append(
			{"employee": e.name, "employee_name": e.employee_name, "days": day_syms, "totals": totals}
		)
	return rows


def _rows_to_report_data(rows: list[dict], days: int, categories: list[str]) -> list:
	"""Map the shared semantic rows onto this report's flat column layout (day_N / cat_i)."""
	cat_index = {cat: idx for idx, cat in enumerate(categories)}
	data = []
	for r in rows:
		row = {
			"employee": r["employee"],
			"employee_name": r["employee_name"],
			**{f"cat_{i}": 0.0 for i in range(len(categories))},
		}
		for day, sym in r["days"].items():
			row[f"day_{day}"] = sym
		for cat, val in r["totals"].items():
			if cat in cat_index:
				row[f"cat_{cat_index[cat]}"] = flt(val)
		data.append(row)
	return data
