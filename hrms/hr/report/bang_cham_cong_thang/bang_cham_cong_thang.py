# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt
"""Bảng chấm công tháng — read-only monthly timekeeping sheet.

Pivots Attendance by employee × day-of-month; each cell shows the mã công for that day and
extra columns total the work_fraction per category (Công / Phép / Ốm / Không lương / ...).
Read-only: it never writes, so it is safe against payroll and existing data.
"""

from calendar import monthrange

import frappe
from frappe import _
from frappe.utils import cint, flt, getdate
from frappe.utils.nestedset import get_descendants_of

Filters = frappe._dict


def execute(filters: Filters | None = None) -> tuple:
	filters = frappe._dict(filters or {})
	if not (filters.month and filters.year):
		frappe.throw(_("Please select month and year."))

	code_map = get_code_map()
	categories = get_categories(code_map)
	days = monthrange(cint(filters.year), cint(filters.month))[1]

	attendances = get_attendances(filters, days)
	columns = get_columns(days, categories)
	data = get_data(attendances, days, categories, code_map)
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
	preferred = ["Công", "Phép", "Ốm", "Thai sản", "Nghỉ bù", "Không lương"]
	present = {r.category for r in code_map.values() if r.category}
	ordered = [c for c in preferred if c in present]
	ordered += sorted(present - set(preferred))
	return ordered


def get_attendances(filters: Filters, days: int) -> list:
	start = getdate(f"{cint(filters.year)}-{cint(filters.month):02d}-01")
	end = getdate(f"{cint(filters.year)}-{cint(filters.month):02d}-{days:02d}")
	q = {"attendance_date": ["between", [start, end]], "docstatus": ["<", 2]}
	if filters.get("company"):
		companies = [filters.company]
		if filters.get("include_company_descendants"):
			companies += get_descendants_of("Company", filters.company)
		q["company"] = ["in", companies]

	return frappe.get_all(
		"Attendance",
		filters=q,
		fields=[
			"employee",
			"employee_name",
			"attendance_date",
			"status",
			"leave_type",
			"custom_attendance_code",
			"custom_morning_code",
			"custom_afternoon_code",
		],
		order_by="employee_name, attendance_date",
	)


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


def get_data(attendances: list, days: int, categories: list[str], code_map: dict) -> list:
	cat_index = {cat: idx for idx, cat in enumerate(categories)}
	rows = {}
	for att in attendances:
		row = rows.setdefault(
			att.employee,
			{
				"employee": att.employee,
				"employee_name": att.employee_name,
				**{f"cat_{i}": 0.0 for i in range(len(categories))},
			},
		)
		display, morning, afternoon = _resolve_day(att, code_map)
		row[f"day_{getdate(att.attendance_date).day}"] = display
		# each half contributes work_fraction * 0.5 to its category total
		for half in (morning, afternoon):
			c = code_map.get(half)
			if c and c.category in cat_index:
				row[f"cat_{cat_index[c.category]}"] = flt(row[f"cat_{cat_index[c.category]}"]) + flt(c.work_fraction) * 0.5

	return list(rows.values())
