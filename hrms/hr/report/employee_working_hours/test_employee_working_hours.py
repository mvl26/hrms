# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

import frappe
from frappe import _
from frappe.tests.utils import FrappeTestCase
from frappe.utils import getdate, time_diff_in_hours

from erpnext.setup.doctype.employee.test_employee import make_employee

from hrms.hr.report.employee_working_hours.employee_working_hours import (
	execute,
	get_daily_rows,
	get_summary_rows,
	prepare_filters,
)
from hrms.tests.isolation import PerTestRollback
from hrms.tests.vn_test_utils import default_company

# Mốc thời gian neo: quá khứ (Attendance cấm ngày tương lai) và đủ xa dữ liệu thật của site.
# 2019-06-03 là Thứ Hai.
MONDAY = "2019-06-03"
TUESDAY = "2019-06-04"
WEDNESDAY = "2019-06-05"
NEXT_MONDAY = "2019-06-10"


def make_attendance(
	employee,
	date,
	status="Present",
	in_time=None,
	out_time=None,
	shift=None,
	working_hours=None,
	submit=True,
):
	"""Một bản ghi Attendance cho test. `in_time`/`out_time` là giờ "HH:MM:SS" trong ngày `date`."""
	doc = frappe.get_doc(
		{
			"doctype": "Attendance",
			"employee": employee,
			"attendance_date": getdate(date),
			"status": status,
			"company": default_company(),
		}
	)
	if shift:
		doc.shift = shift
	if in_time and out_time:
		doc.in_time = f"{date} {in_time}"
		doc.out_time = f"{date} {out_time}"
		doc.working_hours = (
			working_hours if working_hours is not None else time_diff_in_hours(doc.out_time, doc.in_time)
		)
	doc.insert()
	if submit:
		doc.submit()
	doc.reload()
	return doc


def base_filters(**overrides):
	filters = {
		"from_date": MONDAY,
		"to_date": "2019-06-07",
		"company": default_company(),
	}
	filters.update(overrides)
	return filters


class TestEmployeeWorkingHoursDaily(PerTestRollback, FrappeTestCase):
	"""Giờ của từng ngày — phải dùng đúng công thức net của `working_hours.compute_net_hours`."""

	def test_present_full_day_deducts_lunch_break(self):
		employee = make_employee("ewh_present@miyano.test", company=default_company())
		make_attendance(employee, MONDAY, in_time="08:00:00", out_time="17:30:00")

		rows = get_daily_rows(base_filters(employee=employee))

		self.assertEqual(len(rows), 1)
		self.assertEqual(rows[0]["hours"], 8.0)  # 9.5h gross - 1.5h nghỉ trưa

	def test_half_day_keeps_gross_hours(self):
		employee = make_employee("ewh_halfday@miyano.test", company=default_company())
		make_attendance(employee, MONDAY, status="Half Day", in_time="08:00:00", out_time="12:00:00")

		rows = get_daily_rows(base_filters(employee=employee))

		self.assertEqual(rows[0]["hours"], 4.0)  # nửa ngày không trừ trưa

	def test_absent_day_has_zero_hours(self):
		employee = make_employee("ewh_absent@miyano.test", company=default_company())
		make_attendance(employee, MONDAY, status="Absent")

		rows = get_daily_rows(base_filters(employee=employee))

		self.assertEqual(rows[0]["hours"], 0.0)

	def test_in_out_are_formatted_as_clock_time(self):
		employee = make_employee("ewh_clock@miyano.test", company=default_company())
		make_attendance(employee, MONDAY, in_time="08:05:00", out_time="17:35:00")

		row = get_daily_rows(base_filters(employee=employee))[0]

		self.assertEqual(row["in_time"], "08:05")
		self.assertEqual(row["out_time"], "17:35")

	def test_day_of_week_label(self):
		employee = make_employee("ewh_dow@miyano.test", company=default_company())
		make_attendance(employee, MONDAY, in_time="08:00:00", out_time="17:30:00")

		row = get_daily_rows(base_filters(employee=employee))[0]

		self.assertEqual(row["day_of_week"], _("Mon"))

	def test_draft_and_cancelled_attendance_are_ignored(self):
		employee = make_employee("ewh_docstatus@miyano.test", company=default_company())
		make_attendance(employee, MONDAY, in_time="08:00:00", out_time="17:30:00", submit=False)
		submitted = make_attendance(employee, TUESDAY, in_time="08:00:00", out_time="17:30:00")
		submitted.cancel()

		rows = get_daily_rows(base_filters(employee=employee))

		self.assertEqual(rows, [])

	def test_date_range_excludes_days_outside_it(self):
		employee = make_employee("ewh_range@miyano.test", company=default_company())
		make_attendance(employee, MONDAY, in_time="08:00:00", out_time="17:30:00")
		make_attendance(employee, NEXT_MONDAY, in_time="08:00:00", out_time="17:30:00")

		rows = get_daily_rows(base_filters(employee=employee))

		self.assertEqual([str(r["attendance_date"]) for r in rows], [MONDAY])

	def test_split_shift_hours_are_not_lunch_deducted_twice(self):
		"""Ca tách buổi lưu `working_hours` ĐÃ là giờ net — report phải dùng thẳng."""
		if not frappe.get_meta("Shift Type").has_field("custom_split_half_day"):
			self.skipTest("site chưa có custom field custom_split_half_day (fixtures)")

		shift = frappe.get_doc(
			{
				"doctype": "Shift Type",
				"__newname": "EWH Split Shift",
				"start_time": "08:00:00",
				"end_time": "17:30:00",
				"custom_split_half_day": 1,
			}
		).insert()

		employee = make_employee("ewh_split@miyano.test", company=default_company())
		attendance = make_attendance(
			employee, MONDAY, in_time="08:00:00", out_time="17:30:00", shift=shift.name
		)

		row = get_daily_rows(base_filters(employee=employee))[0]

		# giờ của report = giờ net ca tách đã lưu, KHÔNG trừ trưa thêm lần nữa
		self.assertEqual(row["hours"], round(attendance.working_hours, 2))
		self.assertNotEqual(row["hours"], round(attendance.working_hours - 1.5, 2))


class TestEmployeeWorkingHoursSummary(PerTestRollback, FrappeTestCase):
	"""Dòng tổng hợp mỗi nhân viên: tổng giờ, số ngày có chấm giờ, TB giờ/ngày, giờ vào/ra TB."""

	def test_totals_and_average_use_only_days_with_hours(self):
		employee = make_employee("ewh_avg@miyano.test", company=default_company())
		make_attendance(employee, MONDAY, in_time="08:00:00", out_time="17:30:00")  # 8h
		make_attendance(employee, TUESDAY, in_time="08:00:00", out_time="15:30:00")  # 6h
		make_attendance(employee, WEDNESDAY, status="Absent")  # 0h -> ngoài mẫu số

		row = next(r for r in get_summary_rows(base_filters(employee=employee)) if r["employee"] == employee)

		self.assertEqual(row["total_hours"], 14.0)
		self.assertEqual(row["days_counted"], 2)
		self.assertEqual(row["avg_hours"], 7.0)

	def test_average_in_and_out_times(self):
		employee = make_employee("ewh_avgtime@miyano.test", company=default_company())
		make_attendance(employee, MONDAY, in_time="08:00:00", out_time="17:30:00")
		make_attendance(employee, TUESDAY, in_time="09:00:00", out_time="18:30:00")

		row = next(r for r in get_summary_rows(base_filters(employee=employee)) if r["employee"] == employee)

		self.assertEqual(row["avg_in_time"], "08:30")
		self.assertEqual(row["avg_out_time"], "18:00")

	def test_active_employee_without_attendance_shows_zero(self):
		employee = make_employee("ewh_noattendance@miyano.test", company=default_company())

		row = next(
			(r for r in get_summary_rows(base_filters(employee=employee)) if r["employee"] == employee),
			None,
		)

		self.assertIsNotNone(row, "nhân viên Active không chấm công vẫn phải có dòng")
		self.assertEqual(row["total_hours"], 0.0)
		self.assertEqual(row["days_counted"], 0)
		self.assertEqual(row["avg_hours"], 0.0)  # không chia cho 0
		self.assertIsNone(row["avg_in_time"])

	def test_department_filter(self):
		departments = frappe.get_all("Department", pluck="name", limit=2)
		if len(departments) < 2:
			self.skipTest("site cần ít nhất 2 Department cho test lọc phòng ban")

		wanted = make_employee("ewh_dept_a@miyano.test", company=default_company(), department=departments[0])
		other = make_employee("ewh_dept_b@miyano.test", company=default_company(), department=departments[1])
		make_attendance(wanted, MONDAY, in_time="08:00:00", out_time="17:30:00")
		make_attendance(other, MONDAY, in_time="08:00:00", out_time="17:30:00")

		employees = [r["employee"] for r in get_summary_rows(base_filters(department=departments[0]))]

		self.assertIn(wanted, employees)
		self.assertNotIn(other, employees)

	def test_left_employee_hidden_unless_include_inactive(self):
		employee = make_employee("ewh_left@miyano.test", company=default_company())
		make_attendance(employee, MONDAY, in_time="08:00:00", out_time="17:30:00")
		frappe.db.set_value("Employee", employee, {"status": "Left", "relieving_date": getdate("2019-12-31")})

		active_only = [r["employee"] for r in get_summary_rows(base_filters())]
		with_inactive = [r["employee"] for r in get_summary_rows(base_filters(include_inactive=1))]

		self.assertNotIn(employee, active_only)
		self.assertIn(employee, with_inactive)


class TestEmployeeWorkingHoursReport(PerTestRollback, FrappeTestCase):
	"""`execute()` — hai chế độ xem và thẻ tóm tắt."""

	def test_prepare_filters_defaults_to_current_month_and_summary(self):
		filters = prepare_filters({"company": default_company()})

		today = getdate()
		self.assertEqual(filters.from_date, getdate(f"{today.year}-{today.month:02d}-01"))
		self.assertEqual(filters.view, "Summary")

	def test_summary_view_columns_and_rows(self):
		employee = make_employee("ewh_exec_summary@miyano.test", company=default_company())
		make_attendance(employee, MONDAY, in_time="08:00:00", out_time="17:30:00")

		columns, data, _chart_none, _chart, report_summary = execute(base_filters(employee=employee))

		fieldnames = [c["fieldname"] for c in columns]
		self.assertEqual(
			fieldnames,
			[
				"employee",
				"employee_name",
				"department",
				"days_counted",
				"total_hours",
				"avg_hours",
				"avg_in_time",
				"avg_out_time",
			],
		)
		self.assertEqual(len(data), 1)
		self.assertEqual(data[0]["total_hours"], 8.0)
		self.assertEqual(len(report_summary), 3)

	def test_detail_view_columns_and_rows(self):
		employee = make_employee("ewh_exec_detail@miyano.test", company=default_company())
		make_attendance(employee, MONDAY, in_time="08:00:00", out_time="17:30:00")
		make_attendance(employee, TUESDAY, in_time="08:00:00", out_time="17:30:00")

		columns, data, *_rest = execute(base_filters(employee=employee, view="Detail"))

		fieldnames = [c["fieldname"] for c in columns]
		self.assertEqual(
			fieldnames,
			[
				"employee",
				"employee_name",
				"attendance_date",
				"day_of_week",
				"shift",
				"status",
				"in_time",
				"out_time",
				"hours",
			],
		)
		self.assertEqual(len(data), 2)
		self.assertEqual(data[0]["in_time"], "08:00")

	def test_report_summary_totals(self):
		employee = make_employee("ewh_exec_cards@miyano.test", company=default_company())
		make_attendance(employee, MONDAY, in_time="08:00:00", out_time="17:30:00")
		make_attendance(employee, TUESDAY, in_time="08:00:00", out_time="15:30:00")

		_columns, _data, _none, _chart, report_summary = execute(base_filters(employee=employee))

		by_label = {card["label"]: card["value"] for card in report_summary}
		self.assertEqual(by_label[_("Total Hours")], 14.0)
		self.assertEqual(by_label[_("Employees With Hours")], 1)
		self.assertEqual(by_label[_("Avg Hours / Day")], 7.0)
