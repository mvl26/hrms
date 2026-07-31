# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

import unittest

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
	elif working_hours is not None:
		doc.working_hours = working_hours
	doc.insert()
	if submit:
		doc.submit()
	doc.reload()
	return doc


def make_split_shift(name, **kwargs):
	"""Ca tách buổi 08:00-17:30 — giờ quy công của ca này bị cap ở khung ca."""
	if not frappe.get_meta("Shift Type").has_field("custom_split_half_day"):
		raise unittest.SkipTest("site chưa có custom field custom_split_half_day (fixtures)")

	shift = frappe.get_doc(
		{
			"doctype": "Shift Type",
			"__newname": name,
			"start_time": "08:00:00",
			"end_time": "17:30:00",
			"custom_split_half_day": 1,
			"custom_lunch_start": "12:00:00",
			"custom_lunch_end": "13:30:00",
		}
	)
	shift.update(kwargs)
	return shift.insert().name


def base_filters(**overrides):
	filters = {
		"from_date": MONDAY,
		"to_date": "2019-06-07",
		"company": default_company(),
	}
	filters.update(overrides)
	return filters


class TestEmployeeWorkingHoursDaily(PerTestRollback, FrappeTestCase):
	"""Giờ của từng ngày — giờ CÓ MẶT tính từ giờ vào/ra, không phải giờ quy công của bảng chấm công."""

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

	def test_hours_are_actual_presence_not_capped_by_shift(self):
		"""Giờ của report là giờ CÓ MẶT thật, không phải giờ quy công đã cap ở khung ca.

		`Attendance.working_hours` của ca tách buổi chỉ cộng phần nằm trong khung ca (xem
		`vn_day_classifier.classify_day`), nên người ở lại tới 19:30 vẫn chỉ được ghi 8h. Lấy con
		số đó làm giờ trung bình thì TB thành "giờ quy công", không phải giờ ở văn phòng.
		"""
		shift = make_split_shift("EWH Split Shift")
		employee = make_employee("ewh_split@miyano.test", company=default_company())
		attendance = make_attendance(employee, MONDAY, in_time="08:00:00", out_time="19:30:00", shift=shift)

		row = get_daily_rows(base_filters(employee=employee))[0]

		# có mặt 08:00->19:30 = 11,5h, trừ 1,5h nghỉ trưa = 10,0h
		self.assertEqual(row["hours"], 10.0)
		# giờ quy công vẫn giữ nguyên con số của bảng chấm công (bị cap ở khung ca 08:00-17:30)
		self.assertEqual(attendance.working_hours, 8.0)
		self.assertEqual(row["credited_hours"], 8.0)

	def test_day_without_punch_has_no_presence_hours(self):
		"""Ngày được trả công nhưng không có giờ vào/ra (WFH, yêu cầu chấm công, nhập tay) không
		phải ngày làm ở văn phòng → 0 giờ và không vào mẫu số TB."""
		employee = make_employee("ewh_nopunch@miyano.test", company=default_company())
		make_attendance(employee, MONDAY, status="Work From Home", working_hours=8.0)

		rows = get_daily_rows(base_filters(employee=employee))
		summary = get_summary_rows(base_filters(employee=employee))

		self.assertEqual(rows[0]["hours"], 0.0)
		self.assertEqual(summary[0]["days_counted"], 0)
		self.assertEqual(summary[0]["avg_hours"], 0.0)

	def test_absent_day_with_punch_is_excluded(self):
		"""Ngày đã chấm là vắng thì dù có punch lẻ cũng không tính là ngày làm việc."""
		employee = make_employee("ewh_absent_punch@miyano.test", company=default_company())
		make_attendance(employee, MONDAY, status="Absent", in_time="08:00:00", out_time="17:30:00")

		rows = get_daily_rows(base_filters(employee=employee))

		self.assertEqual(rows[0]["hours"], 0.0)

	def test_lunch_deducted_only_when_presence_overlaps_it(self):
		employee = make_employee("ewh_lunch@miyano.test", company=default_company())
		make_attendance(employee, MONDAY, in_time="08:00:00", out_time="11:00:00")  # về trước trưa
		make_attendance(employee, TUESDAY, in_time="13:30:00", out_time="17:30:00")  # vào sau trưa

		rows = get_daily_rows(base_filters(employee=employee))
		hours = {str(r["attendance_date"]): r["hours"] for r in rows}

		self.assertEqual(hours[MONDAY], 3.0)  # không chạm giờ trưa -> không trừ
		self.assertEqual(hours[TUESDAY], 4.0)

	def test_degenerate_shift_lunch_window_falls_back_to_default(self):
		"""Ca tạo mới không nhập giờ trưa bị Frappe điền giờ hiện tại vào cả hai field (khung rộng
		0 giây). Khung rác đó phải rơi về mặc định 12:00-13:30, không thì cả ngày không bị trừ trưa."""
		meta = frappe.get_meta("Shift Type")
		if not (meta.has_field("custom_lunch_start") and meta.has_field("custom_lunch_end")):
			self.skipTest("site chưa có custom field giờ nghỉ trưa của ca (fixtures)")

		shift = make_split_shift(
			"EWH Broken Lunch", custom_lunch_start="11:25:08", custom_lunch_end="11:25:08"
		)
		employee = make_employee("ewh_badlunch@miyano.test", company=default_company())
		make_attendance(employee, MONDAY, in_time="08:00:00", out_time="17:30:00", shift=shift)

		row = get_daily_rows(base_filters(employee=employee))[0]

		self.assertEqual(row["hours"], 8.0)  # 9,5h - 1,5h mặc định

	def test_lunch_window_comes_from_shift_config(self):
		"""Khung nghỉ trưa lấy theo cấu hình ca, không hard-code 12:00-13:30."""
		meta = frappe.get_meta("Shift Type")
		if not (meta.has_field("custom_lunch_start") and meta.has_field("custom_lunch_end")):
			self.skipTest("site chưa có custom field giờ nghỉ trưa của ca (fixtures)")

		shift = make_split_shift(
			"EWH Lunch Shift", custom_lunch_start="11:30:00", custom_lunch_end="12:30:00"
		)
		employee = make_employee("ewh_lunchcfg@miyano.test", company=default_company())
		make_attendance(employee, MONDAY, in_time="08:00:00", out_time="17:30:00", shift=shift)

		row = get_daily_rows(base_filters(employee=employee))[0]

		self.assertEqual(row["hours"], 8.5)  # 9,5h - 1,0h nghỉ trưa của ca


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
				"credited_hours",
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
		self.assertEqual(by_label[_("Total Presence Hours")], 14.0)
		self.assertEqual(by_label[_("Employees At Office")], 1)
		self.assertEqual(by_label[_("Avg Hours / Day")], 7.0)
