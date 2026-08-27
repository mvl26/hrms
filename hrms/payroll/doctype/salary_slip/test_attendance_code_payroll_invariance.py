# Copyright (c) 2026, Miyano Việt Nam.
"""Phase 2 GATE: prove that entering attendance via VN mã công (bridge) yields the SAME
payroll figures (payment_days / absent_days / leave_without_pay) as entering the equivalent
native status directly. If this holds, the attendance-code layer is payroll-neutral.

Đo qua `SalarySlip.get_working_days_details` (`vn_test_utils.working_days_details`) — KHÔNG dựng
cấu trúc lương, vì `make_employee_salary_slip` của upstream hardcode `_Test Company` và hệ thống
tài khoản tên tiếng Anh, nên vỡ trên site thật của Miyano (hệ thống tài khoản tiếng Việt). Cùng
cách `test_exempt_payroll.py` và `hrms/tests/test_timekeeping_e2e.py` đang dùng. Ba con số đo được
chính là ba con số duy nhất mà cổng này cần chứng minh là bất biến."""

import frappe
from frappe.tests.utils import FrappeTestCase, change_settings
from frappe.utils import add_days, flt, get_first_day, get_last_day

import erpnext
from erpnext.setup.doctype.employee.test_employee import make_employee

from hrms.hr.doctype.leave_application.test_leave_application import get_first_sunday
from hrms.payroll.doctype.salary_slip.test_salary_slip import make_holiday_list, mark_attendance
from hrms.tests.isolation import PerTestRollback
from hrms.tests.vn_test_utils import working_days_details

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


class TestAttendanceCodePayrollInvariance(PerTestRollback, FrappeTestCase):
	def setUp(self):
		make_holiday_list()
		frappe.db.set_value(
			"Company",
			erpnext.get_default_company(),
			"default_holiday_list",
			"Salary Slip Test Holiday List",
		)

	def payroll_figures(self, employee, any_date_in_month):
		"""Ba con số lương của KỲ chứa `any_date_in_month` — kỳ mà `make_employee_salary_slip` cũ dựng."""
		return working_days_details(
			employee, get_first_day(any_date_in_month), get_last_day(any_date_in_month)
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

		ss_native = self.payroll_figures(emp_native, first_sunday)
		ss_codes = self.payroll_figures(emp_codes, first_sunday)

		# the whole point: code-entered attendance must not change any payroll figure
		self.assertEqual(ss_codes.lwp, ss_native.lwp)
		self.assertEqual(ss_codes.absent_days, ss_native.absent_days)
		self.assertEqual(ss_codes.payment_days, ss_native.payment_days)

		# sanity: the scenarios actually exercised LWP (K), paid leave (P), and an Absent day (V)
		self.assertEqual(ss_native.lwp, 1)
		self.assertEqual(ss_native.absent_days, 1)

	@change_settings(
		"Payroll Settings", {"payroll_based_on": "Attendance", "daily_wages_fraction_for_half_day": 0.5}
	)
	def test_half_day_code_payroll_matches_native(self):
		"""Half-day codes (1/2X/1/2P/1/2K) map to native Half Day. Run BOTH the native and the
		code path through full validation so check_leave_record settles half_day_status the
		same way for both — proving the code layer adds no payroll difference on half days."""
		first_sunday = get_first_sunday()
		emp_native = make_employee("invariance_hd_native@codes.com")
		emp_codes = make_employee("invariance_hd_codes@codes.com")
		for e in (emp_native, emp_codes):
			frappe.db.set_value("Employee", e, {"relieving_date": None, "status": "Active"})

		date = add_days(first_sunday, 1)
		# 1/2X = đi làm thiếu giờ; native equivalent is a plain Half Day. No leave application exists,
		# so check_leave_record forces half_day_status -> Absent identically on both paths.
		mark_attendance(emp_native, date, "Half Day", half_day_status="Present")  # full validate
		self._mark_by_code(emp_codes, date, "1/2X")

		ss_native = self.payroll_figures(emp_native, first_sunday)
		ss_codes = self.payroll_figures(emp_codes, first_sunday)

		self.assertEqual(ss_codes.payment_days, ss_native.payment_days)
		self.assertEqual(ss_codes.absent_days, ss_native.absent_days)
		self.assertEqual(ss_codes.lwp, ss_native.lwp)

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
		att.insert()  # 4h < 8h tối thiểu -> mã 1/2X -> Half Day, KHÔNG gắn loại nghỉ
		att.submit()
		self.assertEqual(att.status, "Half Day")
		self.assertEqual(att.custom_attendance_code, "1/2X")

		ss_native = self.payroll_figures(emp_native, first_sunday)
		ss_class = self.payroll_figures(emp_class, first_sunday)
		# Từ 2026-07-29 mã do máy chấm là 1/2X (không bịa ra đơn nghỉ không lương), nên ngày này
		# GIỐNG HỆT một Half Day nhập tay: cùng payment_days, cùng absent_days, LWP bằng 0.
		self.assertEqual(ss_class.payment_days, ss_native.payment_days)
		self.assertEqual(flt(ss_class.lwp), flt(ss_native.lwp))
		self.assertEqual(flt(ss_class.absent_days), flt(ss_native.absent_days))
		self.assertEqual(flt(ss_class.lwp), 0.0)
		self.assertEqual(flt(ss_class.absent_days), 0.5)
