# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# See license.txt

from datetime import timedelta

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import get_datetime

from erpnext.setup.doctype.employee.test_employee import make_employee

from hrms.tests.isolation import PerTestRollback
from hrms.tests.vn_test_utils import default_company
from hrms.vn_payroll.lunch import (
	DEFAULT_LUNCH_END,
	DEFAULT_LUNCH_START,
	count_lunch_days,
	shift_lunch_window,
)


class TestShiftLunchWindow(PerTestRollback, FrappeTestCase):
	def test_falls_back_to_default_when_no_shift(self):
		self.assertEqual(shift_lunch_window(None), (DEFAULT_LUNCH_START, DEFAULT_LUNCH_END))

	def test_reads_window_from_shift_type(self):
		from hrms.hr.doctype.shift_type.test_shift_type import setup_shift_type

		st = setup_shift_type(shift_type="MVL Lunch Win", start_time="08:00:00", end_time="17:00:00")
		st.custom_lunch_start = timedelta(hours=11)
		st.custom_lunch_end = timedelta(hours=14)
		st.save()
		self.assertEqual(shift_lunch_window(st.name), (11 * 60, 14 * 60))


class TestCountLunchDays(PerTestRollback, FrappeTestCase):
	def setUp(self):
		self.emp = make_employee("lunch_test@codes.com", company=default_company())

	def day(self, d, status, ins=()):
		att = frappe.get_doc(
			{
				"doctype": "Attendance",
				"employee": self.emp,
				"attendance_date": f"2099-06-{d:02d}",
				"custom_attendance_code": "X" if status == "Present" else None,
				"status": status,
			}
		)
		att.flags.ignore_validate = True
		att.insert()
		att.submit()
		for hm in ins:
			frappe.get_doc(
				{
					"doctype": "Employee Checkin",
					"employee": self.emp,
					"time": get_datetime(f"2099-06-{d:02d} {hm}"),
				}
			).insert()

	def count(self):
		return count_lunch_days(self.emp, "2099-06-01", "2099-06-30")

	def test_full_shift_present_counts(self):
		self.day(1, "Present", ("08:00:00", "17:30:00"))
		self.assertEqual(self.count(), 1)

	def test_morning_only_does_not_count(self):
		# ra 11:30 < 13:30 → chỉ làm sáng, không ăn trưa tại công ty
		self.day(2, "Present", ("08:00:00", "11:30:00"))
		self.assertEqual(self.count(), 0)

	def test_afternoon_only_does_not_count(self):
		# vào 14:00 >= 12:00 → chỉ làm chiều
		self.day(3, "Present", ("14:00:00", "17:00:00"))
		self.assertEqual(self.count(), 0)

	def test_boundary_out_exactly_1330_counts(self):
		self.day(4, "Present", ("11:59:00", "13:30:00"))
		self.assertEqual(self.count(), 1)

	def test_leave_day_with_full_checkins_does_not_count(self):
		# ngày nghỉ phép dù có checkin cũng không tính ăn trưa (không phải ngày công)
		self.day(5, "On Leave", ("08:00:00", "17:30:00"))
		self.assertEqual(self.count(), 0)

	def test_present_without_checkin_does_not_count(self):
		self.day(6, "Present", ())
		self.assertEqual(self.count(), 0)

	def test_multiple_days_sum(self):
		self.day(7, "Present", ("08:00:00", "17:30:00"))  # +1
		self.day(8, "Present", ("08:00:00", "11:00:00"))  # sáng, 0
		self.day(9, "Half Day", ("08:00:00", "17:30:00"))  # +1 (Half Day cũng là ngày công)
		self.assertEqual(self.count(), 2)
