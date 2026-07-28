# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# See license.txt
"""Phase 2 GATE: prove that entering attendance via VN mã công (bridge) yields the SAME
payroll figures (payment_days / absent_days / leave_without_pay) as entering the equivalent
native status directly. If this holds, the attendance-code layer is payroll-neutral."""

import frappe
from frappe.tests.utils import FrappeTestCase, change_settings
from frappe.utils import add_days, flt

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
	(4, "Absent", None, "V"),  # vắng không lý do
	(5, "Work From Home", None, "CT"),  # đi công tác — paid, no deduction
	(6, "On Leave", "Nghỉ kết hôn", "KH"),  # nghỉ kết hôn có lương — paid, no deduction
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

		# sanity: the scenarios actually exercised LWP (K), paid leave (P), and an Absent day (V)
		self.assertEqual(ss_native.leave_without_pay, 1)
		self.assertEqual(ss_native.absent_days, 1)

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

	@change_settings(
		"Payroll Settings", {"payroll_based_on": "Attendance", "daily_wages_fraction_for_half_day": 0.5}
	)
	def test_classifier_morning_only_matches_native_half_day(self):
		"""A shift-classified morning-only day (in 08:00 / out 12:00) → X/K: đi làm nửa buổi, nửa còn
		lại NGHỈ KHÔNG LƯƠNG. NET PAY (payment_days) bằng hệt native Half Day docks 0.5; nhưng 0.5 đó nay
		là leave-without-pay (không lương) thay vì vắng — cùng số tiền, đúng category (X/K không phải X/V)."""
		first_sunday = get_first_sunday()
		shift = "VN Split PR 08-1730"
		if not frappe.db.exists("Shift Type", shift):
			frappe.get_doc(
				{
					"doctype": "Shift Type",
					"__newname": shift,
					"start_time": "08:00:00",
					"end_time": "17:30:00",
					"custom_split_half_day": 1,
					"custom_lunch_start": "12:00:00",
					"custom_lunch_end": "13:30:00",
				}
			).insert()

		emp_native = make_employee("inv_hd_native@codes.com")
		emp_class = make_employee("inv_hd_class@codes.com")
		for e in (emp_native, emp_class):
			frappe.db.set_value("Employee", e, {"relieving_date": None, "status": "Active"})

		date = add_days(first_sunday, 1)
		mark_attendance(emp_native, date, "Half Day", half_day_status="Present")  # full validate -> Absent
		att = frappe.get_doc(
			{
				"doctype": "Attendance",
				"employee": emp_class,
				"attendance_date": date,
				"shift": shift,
				"in_time": f"{date} 08:00:00",
				"out_time": f"{date} 12:00:00",
			}
		)
		att.insert()  # classifier -> token đơn 1/2K -> Half Day (Nghỉ không lương)
		att.submit()
		self.assertEqual(att.status, "Half Day")
		self.assertEqual(att.custom_attendance_code, "1/2K")

		ss_native = make_employee_salary_slip(emp_native, "Monthly", "Inv HD Native")
		ss_class = make_employee_salary_slip(emp_class, "Monthly", "Inv HD Class")
		# NET PAY BẤT BIẾN: cùng payment_days (0.5 bị trừ dù nửa kia là vắng hay không lương)
		self.assertEqual(ss_class.payment_days, ss_native.payment_days)
		# nhưng 0.5 đó nay là NGHỈ KHÔNG LƯƠNG (LWP), không phải Vắng — đúng ý X/K
		self.assertEqual(flt(ss_class.leave_without_pay), 0.5)
		self.assertEqual(flt(ss_class.absent_days), 0.0)
