# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# See license.txt
"""Phase 2 GATE: prove that entering attendance via VN mã công (bridge) yields the SAME
payroll figures (payment_days / absent_days / leave_without_pay) as entering the equivalent
native status directly. If this holds, the attendance-code layer is payroll-neutral."""

import frappe
from frappe.tests.utils import FrappeTestCase, change_settings
from frappe.utils import add_days

import erpnext
from erpnext.setup.doctype.employee.test_employee import make_employee

from hrms.hr.doctype.leave_application.test_leave_application import get_first_sunday
from hrms.payroll.doctype.salary_slip.test_salary_slip import (
	make_employee_salary_slip,
	make_holiday_list,
	mark_attendance,
)

# (day offset from first sunday, native status, native leave_type, equivalent single-day code)
# full-day scenarios only: for a full On-Leave day half_day_status is irrelevant to payroll,
# so the native (ignore_validate) and code (full validate) paths are directly comparable.
SCENARIOS = [
	(1, "Present", None, "X"),
	(2, "On Leave", "Nghỉ không lương", "K"),  # LWP
	(3, "On Leave", "Nghỉ phép năm", "P"),  # paid leave
]


class TestAttendanceCodePayrollInvariance(FrappeTestCase):
	def setUp(self):
		make_holiday_list()
		frappe.db.set_value(
			"Company",
			erpnext.get_default_company(),
			"default_holiday_list",
			"Salary Slip Test Holiday List",
		)

	def _mark_by_code(self, employee, date, code):
		att = frappe.get_doc(
			{
				"doctype": "Attendance",
				"employee": employee,
				"attendance_date": date,
				"custom_attendance_code": code,
			}
		)
		att.insert()  # before_validate bridge sets status/leave_type from the code
		att.submit()

	@change_settings(
		"Payroll Settings", {"payroll_based_on": "Attendance", "daily_wages_fraction_for_half_day": 0.5}
	)
	def test_payroll_identical_native_vs_codes(self):
		first_sunday = get_first_sunday()
		emp_native = make_employee("invariance_native@codes.com")
		emp_codes = make_employee("invariance_codes@codes.com")
		for e in (emp_native, emp_codes):
			frappe.db.set_value("Employee", e, {"relieving_date": None, "status": "Active"})

		for offset, status, leave_type, code in SCENARIOS:
			date = add_days(first_sunday, offset)
			mark_attendance(emp_native, date, status, leave_type=leave_type, ignore_validate=True)
			self._mark_by_code(emp_codes, date, code)

		ss_native = make_employee_salary_slip(emp_native, "Monthly", "Invariance SS Native")
		ss_codes = make_employee_salary_slip(emp_codes, "Monthly", "Invariance SS Codes")

		# the whole point: code-entered attendance must not change any payroll figure
		self.assertEqual(ss_codes.leave_without_pay, ss_native.leave_without_pay)
		self.assertEqual(ss_codes.absent_days, ss_native.absent_days)
		self.assertEqual(ss_codes.payment_days, ss_native.payment_days)

		# sanity: the scenario actually exercised LWP (K) and paid leave (P, no LWP)
		self.assertEqual(ss_native.leave_without_pay, 1)
		self.assertEqual(ss_native.absent_days, 0)

	@change_settings(
		"Payroll Settings", {"payroll_based_on": "Attendance", "daily_wages_fraction_for_half_day": 0.5}
	)
	def test_half_day_code_payroll_matches_native(self):
		"""Half-day codes (NN/1/2P/1/2K) map to native Half Day. Run BOTH the native and the
		code path through full validation so check_leave_record settles half_day_status the
		same way for both — proving the code layer adds no payroll difference on half days."""
		first_sunday = get_first_sunday()
		emp_native = make_employee("invariance_hd_native@codes.com")
		emp_codes = make_employee("invariance_hd_codes@codes.com")
		for e in (emp_native, emp_codes):
			frappe.db.set_value("Employee", e, {"relieving_date": None, "status": "Active"})

		date = add_days(first_sunday, 1)
		# NN = làm nửa ngày; native equivalent is a plain Half Day. No leave application exists,
		# so check_leave_record forces half_day_status -> Absent identically on both paths.
		mark_attendance(emp_native, date, "Half Day", half_day_status="Present")  # full validate
		self._mark_by_code(emp_codes, date, "NN")

		ss_native = make_employee_salary_slip(emp_native, "Monthly", "Invariance HD Native")
		ss_codes = make_employee_salary_slip(emp_codes, "Monthly", "Invariance HD Codes")

		self.assertEqual(ss_codes.payment_days, ss_native.payment_days)
		self.assertEqual(ss_codes.absent_days, ss_native.absent_days)
		self.assertEqual(ss_codes.leave_without_pay, ss_native.leave_without_pay)
