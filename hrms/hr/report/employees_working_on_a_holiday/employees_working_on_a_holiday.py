import frappe
from frappe import _
from frappe.utils import getdate


def execute(filters=None):
	if not filters:
		filters = {}

	columns = get_columns()
	data = get_data(filters)
	return columns, data


def get_columns():
	return [
		{
			"label": _("Employee"),
			"fieldtype": "Link",
			"fieldname": "employee",
			"options": "Employee",
			"width": 300,
		},
		{
			"label": _("Employee Name"),
			"fieldtype": "Data",
			"width": 0,
			"hidden": 1,
		},
		{
			"label": _("Date"),
			"fieldtype": "Date",
			"width": 120,
		},
		{
			"label": _("Status"),
			"fieldtype": "Data",
			"width": 100,
		},
		{
			"label": _("Loại ngày"),
			"fieldtype": "Data",
			"width": 200,
		},
	]


def get_data(filters):
	"""Ai đã đi làm vào ngày KHÔNG phải đi làm — nghỉ cuối tuần lẫn ngày lễ.

	Trước đây báo cáo nối Attendance với dòng `Holiday`. Sau khi lịch tuần tách khỏi Holiday List,
	nối như vậy là chỉ còn thấy người đi làm NGÀY LỄ — mà công dụng chính của báo cáo này là trả lời
	"ai đang đi làm cuối tuần". Nay hỏi `work_schedule` và gọi tên rõ từng loại ngày.
	"""
	from hrms.hr.work_schedule import non_working_days_between, public_holidays_between

	employee_filters = {"company": filters.company}
	if filters.department:
		employee_filters["department"] = filters.department

	data = []
	for employee in frappe.get_list("Employee", filters=employee_filters, pluck="name"):
		off_days = non_working_days_between(employee, filters.from_date, filters.to_date)
		if not off_days:
			continue
		holidays = public_holidays_between(employee, filters.from_date, filters.to_date)

		rows = frappe.get_all(
			"Attendance",
			filters=[
				["employee", "=", employee],
				["attendance_date", "between", [filters.from_date, filters.to_date]],
				["status", "not in", ["Absent", "On Leave"]],
				["docstatus", "=", 1],
			],
			fields=["employee", "employee_name", "attendance_date", "status"],
		)
		for r in rows:
			day = getdate(r.attendance_date)
			if day not in off_days:
				continue
			kind = _("Nghỉ lễ") if day in holidays else _("Nghỉ cuối tuần")
			data.append([r.employee, r.employee_name, r.attendance_date, r.status, kind])

	return data
