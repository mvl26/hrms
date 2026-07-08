# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt
"""Bảng chấm công tháng — read-only monthly timekeeping sheet.

Pivots by employee × day-of-month. Each cell is the mã công for that day:
- a real Attendance record → its code (or morning/afternoon codes, e.g. "X/P");
- otherwise a calendar marker derived (NOT stored) from the employee's data:
  `N` after the relieving date, `CN` on a weekly-off, `NL` on a public holiday.

Totals columns sum per category: Công = actual worked công (Σ work_fraction), and each leave
column = Σ (1 − work_fraction) of that category's halves. Read-only: never writes, so it is
safe against payroll and existing data.
"""

from calendar import monthrange

import frappe
from frappe import _
from frappe.utils import cint, flt, getdate
from frappe.utils.nestedset import get_descendants_of

from erpnext.setup.doctype.employee.employee import get_holiday_list_for_employee

Filters = frappe._dict

# display-only markers derived from the calendar, not Attendance Code master records
MARKER_TERMINATED = "N"
MARKER_WEEKLY_OFF = "CN"
MARKER_HOLIDAY = "NL"


def execute(filters: Filters | None = None) -> tuple:
	filters = frappe._dict(filters or {})
	if not (filters.month and filters.year):
		frappe.throw(_("Please select month and year."))

	year, month = cint(filters.year), cint(filters.month)
	days = monthrange(year, month)[1]
	start = getdate(f"{year}-{month:02d}-01")
	end = getdate(f"{year}-{month:02d}-{days:02d}")

	code_map = get_code_map()
	categories = get_categories(code_map)
	employees = get_employees(filters, start, end)
	attendances = get_attendances(filters, start, end)
	holidays = get_holidays(employees, start, end)

	columns = get_columns(days, categories)
	data = get_data(employees, attendances, holidays, days, year, month, categories, code_map)
	return columns, data


def get_code_map() -> dict:
	"""{code: {category, work_fraction, maps_to_status, leave_type}} for every Attendance Code."""
	rows = frappe.get_all(
		"Attendance Code",
		fields=["name", "category", "work_fraction", "maps_to_status", "leave_type"],
	)
	return {r.name: r for r in rows}


def get_categories(code_map: dict) -> list[str]:
	# stable, human order first; then any extra categories present in the data
	preferred = ["Công", "Phép", "Ốm", "Thai sản", "Tai nạn LĐ", "Nghỉ bù", "Không lương", "Vắng"]
	present = {r.category for r in code_map.values() if r.category}
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
	"""{employee: {day-of-month: attendance}} for the month."""
	q = {"attendance_date": ["between", [start, end]], "docstatus": ["<", 2]}
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


def get_data(
	employees: list,
	attendances: dict,
	holidays: dict,
	days: int,
	year: int,
	month: int,
	categories: list[str],
	code_map: dict,
) -> list:
	cat_index = {cat: idx for idx, cat in enumerate(categories)}
	cong_idx = cat_index.get("Công")
	data = []
	for e in employees:
		row = {
			"employee": e.name,
			"employee_name": e.employee_name,
			**{f"cat_{i}": 0.0 for i in range(len(categories))},
		}
		emp_att = attendances.get(e.name, {})
		emp_hol = holidays.get(e.name, {})
		relieving = getdate(e.relieving_date) if e.relieving_date else None
		joining = getdate(e.date_of_joining) if e.date_of_joining else None

		for day in range(1, days + 1):
			d = getdate(f"{year}-{month:02d}-{day:02d}")
			# priority: đã ngừng việc > bản ghi Attendance > ngày lễ/CN > (trước khi vào làm →) trống
			if relieving and d > relieving:
				row[f"day_{day}"] = MARKER_TERMINATED
				continue
			att = emp_att.get(day)
			if att:
				display, morning, afternoon = _resolve_day(att, code_map)
				row[f"day_{day}"] = display
				for half in (morning, afternoon):
					c = code_map.get(half)
					if not c:
						continue
					wf = flt(c.work_fraction)
					if cong_idx is not None:
						row[f"cat_{cong_idx}"] += wf * 0.5  # công thực đi làm
					if c.category != "Công" and c.category in cat_index:
						row[f"cat_{cat_index[c.category]}"] += (1 - wf) * 0.5  # phần nghỉ
			elif joining and d < joining:
				continue  # chưa vào làm → để trống
			elif day in emp_hol:
				row[f"day_{day}"] = MARKER_WEEKLY_OFF if emp_hol[day] else MARKER_HOLIDAY

		data.append(row)
	return data
