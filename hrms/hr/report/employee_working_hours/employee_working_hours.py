# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt
"""Báo cáo giờ làm việc: giờ vào / giờ ra / tổng giờ / TB giờ mỗi ngày của nhân viên đang làm việc.

Chỉ ĐỌC Attendance đã duyệt (`docstatus = 1`) — không ghi gì, nên payroll-neutral theo định nghĩa.

**Giờ ở báo cáo này là giờ CÓ MẶT, không phải giờ quy công.** `Attendance.working_hours` của ca
tách buổi chỉ cộng phần giờ nằm trong khung ca (`vn_day_classifier.classify_day`), nên người ở lại
tới 19:30 vẫn chỉ được ghi 8h — dùng con số đó thì "TB giờ/ngày" hoá ra là công tháng chứ không
phải thời gian thật ở văn phòng. Vì vậy giờ mỗi ngày được tính lại từ giờ vào/ra: (ra - vào) trừ
phần giao với khung nghỉ trưa của ca. Giờ quy công vẫn giữ ở cột riêng để đối chiếu bảng chấm công.

Ngày không có giờ vào/ra (WFH, yêu cầu chấm công, nhập tay) không phải ngày làm ở văn phòng → 0 giờ
và không vào mẫu số TB. Xem `spec/employee-working-hours-report.md`.
"""

from datetime import datetime

import frappe
from frappe import _
from frappe.utils import cint, get_datetime, get_first_day, get_last_day, getdate

from hrms.hr.doctype.attendance.vn_day_classifier import overlap_hours, resolve_lunch_window
from hrms.hr.working_hours import compute_net_hours

# nhãn thứ trong tuần theo chỉ số `date.weekday()` (0 = Thứ Hai)
WEEKDAY_LABELS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")

# ngày đã chấm là nghỉ thì dù có punch lẻ cũng không tính là ngày làm việc ở văn phòng
NON_PRESENCE_STATUSES = ("Absent", "On Leave")


def execute(filters=None):
	filters = prepare_filters(filters)
	employees = get_employees(filters)
	daily_rows = get_daily_rows(filters, employees)
	report_summary = get_report_summary(daily_rows)

	if filters.view == "Detail":
		return get_detail_columns(), daily_rows, None, None, report_summary

	summary_rows = get_summary_rows(filters, employees, daily_rows)
	return get_summary_columns(), summary_rows, None, None, report_summary


def prepare_filters(filters=None):
	"""Chuẩn hoá filter: mặc định khoảng ngày là tháng hiện tại, chế độ xem là Summary."""
	filters = frappe._dict(filters or {})
	today = getdate()
	filters.from_date = getdate(filters.get("from_date") or get_first_day(today))
	filters.to_date = getdate(filters.get("to_date") or get_last_day(today))
	filters.view = filters.get("view") or "Summary"
	filters.include_inactive = cint(filters.get("include_inactive"))
	if not filters.get("company"):
		filters.company = frappe.defaults.get_user_default("Company")
	return filters


def get_employees(filters):
	"""Nhân viên khớp filter — mặc định chỉ người đang làm việc (status Active)."""
	filters = prepare_filters(filters)

	conditions = {}
	if filters.get("company"):
		conditions["company"] = filters.company
	if filters.get("employee"):
		conditions["name"] = filters.employee
	if filters.get("department"):
		conditions["department"] = filters.department
	if not filters.include_inactive:
		conditions["status"] = "Active"

	return frappe.get_all(
		"Employee",
		filters=conditions,
		fields=["name", "employee_name", "department"],
		order_by="employee_name asc",
	)


def get_split_shift_names():
	"""Ca bật tách buổi — `working_hours` của chúng ĐÃ là giờ net, không trừ trưa lần hai.

	Đọc phòng thủ: `custom_split_half_day` là custom field (fixtures), site chưa migrate thì chưa
	có field và câu lọc sẽ vỡ.
	"""
	if not frappe.get_meta("Shift Type").has_field("custom_split_half_day"):
		return set()
	return set(frappe.get_all("Shift Type", filters={"custom_split_half_day": 1}, pluck="name"))


def get_lunch_window_map():
	"""{ca: khung nghỉ trưa} — cùng luật với bộ chấm mã công (`resolve_lunch_window`).

	Đọc phòng thủ: hai field này là custom field (fixtures), site chưa migrate thì chưa có.
	"""
	meta = frappe.get_meta("Shift Type")
	if not (meta.has_field("custom_lunch_start") and meta.has_field("custom_lunch_end")):
		return {}

	return {
		shift.name: resolve_lunch_window(shift.custom_lunch_start, shift.custom_lunch_end)
		for shift in frappe.get_all("Shift Type", fields=["name", "custom_lunch_start", "custom_lunch_end"])
	}


def presence_hours(in_time, out_time, attendance_date, lunch_start=None, lunch_end=None):
	"""Giờ thực sự có mặt: (giờ ra - giờ vào) trừ phần giao với khung nghỉ trưa.

	KHÔNG cắt theo khung ca — ở lại sau giờ tan ca vẫn được tính. Thiếu giờ vào hoặc giờ ra thì
	không xác định được thời gian có mặt → 0.
	"""
	if not (in_time and out_time):
		return 0.0

	in_time, out_time = get_datetime(in_time), get_datetime(out_time)
	if out_time <= in_time:
		return 0.0

	day = datetime.combine(getdate(attendance_date), datetime.min.time())
	lunch_start, lunch_end = resolve_lunch_window(lunch_start, lunch_end)
	lunch = overlap_hours(in_time, out_time, day + lunch_start, day + lunch_end)
	present = (out_time - in_time).total_seconds() / 3600.0
	return round(max(present - lunch, 0.0), 2)


def get_daily_rows(filters, employees=None):
	"""Một dòng cho mỗi ngày có Attendance đã duyệt, kèm giờ có mặt và giờ quy công của ngày đó."""
	filters = prepare_filters(filters)
	if employees is None:
		employees = get_employees(filters)
	if not employees:
		return []

	employee_map = {e.name: e for e in employees}
	split_shifts = get_split_shift_names()
	lunch_windows = get_lunch_window_map()

	Attendance = frappe.qb.DocType("Attendance")
	query = (
		frappe.qb.from_(Attendance)
		.select(
			Attendance.employee,
			Attendance.attendance_date,
			Attendance.status,
			Attendance.shift,
			Attendance.in_time,
			Attendance.out_time,
			Attendance.working_hours,
		)
		.where(
			(Attendance.docstatus == 1)
			& (Attendance.employee.isin(list(employee_map)))
			& (Attendance.attendance_date >= filters.from_date)
			& (Attendance.attendance_date <= filters.to_date)
		)
		.orderby(Attendance.employee_name)
		.orderby(Attendance.attendance_date)
	)
	if filters.get("shift"):
		query = query.where(Attendance.shift == filters.shift)

	rows = []
	for record in query.run(as_dict=True):
		employee = employee_map[record.employee]
		lunch_start, lunch_end = lunch_windows.get(record.shift or "", (None, None))
		hours = 0.0
		if record.status not in NON_PRESENCE_STATUSES:
			hours = presence_hours(
				record.in_time, record.out_time, record.attendance_date, lunch_start, lunch_end
			)
		credited_hours = compute_net_hours(
			record.status,
			record.in_time,
			record.out_time,
			record.working_hours,
			is_split=(record.shift or "") in split_shifts,
		)
		rows.append(
			{
				"employee": record.employee,
				"employee_name": employee.employee_name,
				"department": employee.department,
				"attendance_date": record.attendance_date,
				"day_of_week": _(WEEKDAY_LABELS[getdate(record.attendance_date).weekday()]),
				"shift": record.shift,
				"status": record.status,
				"in_time": format_minutes(clock_minutes(record.in_time)),
				"out_time": format_minutes(clock_minutes(record.out_time)),
				"in_minutes": clock_minutes(record.in_time),
				"out_minutes": clock_minutes(record.out_time),
				"hours": hours,
				"credited_hours": credited_hours,
			}
		)

	return rows


def get_summary_rows(filters, employees=None, daily_rows=None):
	"""Một dòng cho mỗi nhân viên khớp filter — kể cả người không chấm công ngày nào (0 giờ)."""
	filters = prepare_filters(filters)
	if employees is None:
		employees = get_employees(filters)
	if daily_rows is None:
		daily_rows = get_daily_rows(filters, employees)

	totals = {}
	for row in daily_rows:
		# chỉ ngày thực sự có giờ mới vào tổng và vào mẫu số TB — ngày nghỉ/vắng không kéo TB xuống
		if row["hours"] <= 0:
			continue
		total = totals.setdefault(row["employee"], {"hours": 0.0, "days": 0, "in": [], "out": []})
		total["hours"] += row["hours"]
		total["days"] += 1
		if row["in_minutes"] is not None:
			total["in"].append(row["in_minutes"])
		if row["out_minutes"] is not None:
			total["out"].append(row["out_minutes"])

	summary = []
	for employee in employees:
		total = totals.get(employee.name)
		days = total["days"] if total else 0
		hours = round(total["hours"], 2) if total else 0.0
		summary.append(
			{
				"employee": employee.name,
				"employee_name": employee.employee_name,
				"department": employee.department,
				"days_counted": days,
				"total_hours": hours,
				"avg_hours": round(hours / days, 2) if days else 0.0,
				"avg_in_time": average_clock(total["in"]) if total else None,
				"avg_out_time": average_clock(total["out"]) if total else None,
			}
		)

	return summary


def get_report_summary(daily_rows):
	total_hours = round(sum(row["hours"] for row in daily_rows), 2)
	days = sum(1 for row in daily_rows if row["hours"] > 0)
	employees = len({row["employee"] for row in daily_rows if row["hours"] > 0})

	return [
		{
			"label": _("Total Presence Hours"),
			"value": total_hours,
			"datatype": "Float",
			"indicator": "Blue",
		},
		{
			"label": _("Employees At Office"),
			"value": employees,
			"datatype": "Int",
			"indicator": "Green",
		},
		{
			"label": _("Avg Hours / Day"),
			"value": round(total_hours / days, 2) if days else 0.0,
			"datatype": "Float",
			"indicator": "Blue",
		},
	]


# ---------------------------------------------------------------------------
# Giờ đồng hồ
# ---------------------------------------------------------------------------


def clock_minutes(value):
	"""Giờ đồng hồ của một datetime, tính bằng phút từ 00:00. None nếu không có giá trị."""
	if not value:
		return None
	value = get_datetime(value)
	return value.hour * 60 + value.minute


def format_minutes(minutes):
	"""Phút từ 00:00 -> chuỗi `HH:MM`."""
	if minutes is None:
		return None
	return f"{minutes // 60:02d}:{minutes % 60:02d}"


def average_clock(minutes_list):
	"""Giờ đồng hồ trung bình của một danh sách phút. Ca qua đêm đọc theo giờ đồng hồ."""
	if not minutes_list:
		return None
	return format_minutes(round(sum(minutes_list) / len(minutes_list)))


# ---------------------------------------------------------------------------
# Cột
# ---------------------------------------------------------------------------


def get_summary_columns():
	return [
		{
			"label": _("Employee"),
			"fieldname": "employee",
			"fieldtype": "Link",
			"options": "Employee",
			"width": 140,
		},
		{
			"label": _("Employee Name"),
			"fieldname": "employee_name",
			"fieldtype": "Data",
			"width": 200,
		},
		{
			"label": _("Department"),
			"fieldname": "department",
			"fieldtype": "Link",
			"options": "Department",
			"width": 160,
		},
		{
			"label": _("Days At Office"),
			"fieldname": "days_counted",
			"fieldtype": "Int",
			"width": 130,
		},
		{
			"label": _("Total Presence Hours"),
			"fieldname": "total_hours",
			"fieldtype": "Float",
			"precision": 2,
			"width": 110,
		},
		{
			"label": _("Avg Hours / Day"),
			"fieldname": "avg_hours",
			"fieldtype": "Float",
			"precision": 2,
			"width": 130,
		},
		{
			"label": _("Avg In Time"),
			"fieldname": "avg_in_time",
			"fieldtype": "Data",
			"width": 110,
		},
		{
			"label": _("Avg Out Time"),
			"fieldname": "avg_out_time",
			"fieldtype": "Data",
			"width": 110,
		},
	]


def get_detail_columns():
	return [
		{
			"label": _("Employee"),
			"fieldname": "employee",
			"fieldtype": "Link",
			"options": "Employee",
			"width": 140,
		},
		{
			"label": _("Employee Name"),
			"fieldname": "employee_name",
			"fieldtype": "Data",
			"width": 180,
		},
		{
			"label": _("Date"),
			"fieldname": "attendance_date",
			"fieldtype": "Date",
			"width": 110,
		},
		{
			"label": _("Weekday"),
			"fieldname": "day_of_week",
			"fieldtype": "Data",
			"width": 70,
		},
		{
			"label": _("Shift"),
			"fieldname": "shift",
			"fieldtype": "Link",
			"options": "Shift Type",
			"width": 130,
		},
		{
			"label": _("Status"),
			"fieldname": "status",
			"fieldtype": "Data",
			"width": 100,
		},
		{
			"label": _("In Time"),
			"fieldname": "in_time",
			"fieldtype": "Data",
			"width": 90,
		},
		{
			"label": _("Out Time"),
			"fieldname": "out_time",
			"fieldtype": "Data",
			"width": 90,
		},
		{
			"label": _("Presence Hours"),
			"fieldname": "hours",
			"fieldtype": "Float",
			"precision": 2,
			"width": 110,
		},
		{
			"label": _("Credited Hours"),
			"fieldname": "credited_hours",
			"fieldtype": "Float",
			"precision": 2,
			"width": 110,
		},
	]
