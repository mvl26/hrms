# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

from calendar import monthrange

import frappe
from frappe import _
from frappe.query_builder.functions import Extract
from frappe.utils import cint, flt, getdate, time_diff_in_hours
from frappe.utils.nestedset import get_descendants_of

LUNCH_BREAK_HOURS = 1.5
STANDARD_HOURS_PER_DAY = 8.0
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


def prepare_filters(filters):
	"""Đảm bảo month/year (mặc định tháng hiện tại) và companies (suy từ company)."""
	filters = frappe._dict(filters or {})
	today = getdate()
	filters.month = cint(filters.get("month")) or today.month
	filters.year = cint(filters.get("year")) or today.year

	if not filters.get("companies"):
		company = filters.get("company")
		companies = [company] if company else []
		if company:
			# gồm cả company con (nhất quán với báo cáo chấm công)
			companies.extend(get_descendants_of("Company", company))
		filters.companies = companies

	return filters


def get_net_hours_map(filters):
	"""{employee: {shift: {day_of_month: net_hours}}} cho tháng/năm trong filters."""
	companies = filters.get("companies") or ([filters.get("company")] if filters.get("company") else [])
	if not companies:
		# tránh SQL `company IN ()` (lỗi cú pháp) khi chưa xác định được company
		return {}

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


def _employee_total(shift_hours):
	return sum(net for days in shift_hours.values() for net in days.values())


def get_hours_by_week(filters):
	"""Tổng giờ làm toàn công ty theo từng tuần trong tháng. -> {labels, values}"""
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
	"""Tổng giờ làm theo từng phòng ban trong tháng. -> {labels, values}"""
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


# ---------------------------------------------------------------------------
# Định mức (standard hours = 8h × số ngày công theo Holiday List)
# ---------------------------------------------------------------------------


def get_standard_hours(total_days, num_holidays):
	"""Giờ định mức = 8h × số ngày công (tổng ngày trừ ngày nghỉ/lễ)."""
	working_days = max(cint(total_days) - cint(num_holidays), 0)
	return round(STANDARD_HOURS_PER_DAY * working_days, 2)


def get_effective_days_in_month(year, month):
	"""Số ngày dùng tính định mức: cả tháng, nhưng nếu là tháng hiện tại (chưa kết thúc)
	thì chỉ tính tới hôm nay — để KPI giữa tháng không báo mọi người thiếu giờ."""
	year, month = cint(year), cint(month)
	total = monthrange(year, month)[1]
	today = getdate()
	if year == today.year and month == today.month:
		return min(total, today.day)
	return total


def _count_holidays_in_month(holiday_list, year, month, up_to_day=None):
	if not holiday_list:
		return 0
	last_day = up_to_day or monthrange(cint(year), cint(month))[1]
	first = getdate(f"{year}-{cint(month):02d}-01")
	last = getdate(f"{year}-{cint(month):02d}-{cint(last_day):02d}")
	return frappe.db.count(
		"Holiday", {"parent": holiday_list, "holiday_date": ["between", [first, last]]}
	)


def get_standard_hours_map(filters, employees=None):
	"""{employee: standard_hours} theo Holiday List của từng nhân sự Active."""
	filters = prepare_filters(filters)
	effective_days = get_effective_days_in_month(filters.year, filters.month)
	company = filters.get("company") or (filters.companies[0] if filters.get("companies") else None)
	default_holiday_list = (
		frappe.get_cached_value("Company", company, "default_holiday_list") if company else None
	)

	if employees:
		emp_filters = {"name": ["in", employees]}
	elif filters.get("companies"):
		emp_filters = {"company": ["in", filters.companies], "status": "Active"}
	else:
		return {}
	emp_rows = frappe.get_all("Employee", filters=emp_filters, fields=["name", "holiday_list"])

	holiday_cache = {}
	result = {}
	for emp in emp_rows:
		hlist = emp.holiday_list or default_holiday_list
		if hlist not in holiday_cache:
			holiday_cache[hlist] = _count_holidays_in_month(
				hlist, filters.year, filters.month, up_to_day=effective_days
			)
		result[emp.name] = get_standard_hours(effective_days, holiday_cache[hlist])

	return result


def get_active_employee_count(filters):
	"""Số nhân sự Active trong các company của filters (mẫu số cho KPI trung bình)."""
	filters = prepare_filters(filters)
	if not filters.get("companies"):
		return 0
	return frappe.db.count("Employee", {"company": ["in", filters.companies], "status": "Active"})


# ---------------------------------------------------------------------------
# KPI number card methods (type Custom -> trả {"value", "fieldtype"})
# ---------------------------------------------------------------------------


def _parse_card_filters(filters):
	if isinstance(filters, str):
		filters = frappe.parse_json(filters)
	if isinstance(filters, (list, tuple)):
		parsed = {}
		for f in filters:
			if isinstance(f, (list, tuple)) and len(f) >= 4:
				parsed[f[1]] = f[3]
		filters = parsed
	filters = frappe._dict(filters or {})
	if not filters.get("company"):
		filters.company = frappe.defaults.get_user_default("Company")
	return prepare_filters(filters)


@frappe.whitelist()
def get_total_working_hours_card(filters=None):
	frappe.has_permission("Attendance", throw=True)
	filters = _parse_card_filters(filters)
	net_map = get_net_hours_map(filters)
	total = sum(_employee_total(shift_hours) for shift_hours in net_map.values())
	return {"value": round(total, 2), "fieldtype": "Float"}


@frappe.whitelist()
def get_avg_working_hours_card(filters=None):
	frappe.has_permission("Attendance", throw=True)
	filters = _parse_card_filters(filters)
	headcount = get_active_employee_count(filters)
	if not headcount:
		return {"value": 0.0, "fieldtype": "Float"}
	net_map = get_net_hours_map(filters)
	total = sum(_employee_total(shift_hours) for shift_hours in net_map.values())
	return {"value": round(total / headcount, 2), "fieldtype": "Float"}


@frappe.whitelist()
def get_under_target_count_card(filters=None):
	frappe.has_permission("Attendance", throw=True)
	filters = _parse_card_filters(filters)
	# duyệt MỌI nhân sự Active — người vắng cả tháng (0 giờ) cũng là thiếu giờ
	std_map = get_standard_hours_map(filters)
	if not std_map:
		return {"value": 0, "fieldtype": "Int"}
	net_map = get_net_hours_map(filters)
	count = 0
	for employee, standard in std_map.items():
		actual = _employee_total(net_map.get(employee, {}))
		if actual < standard:
			count += 1
	return {"value": count, "fieldtype": "Int"}
