# Copyright (c) 2026, Miyano Việt Nam.
"""GATE: tính năng miễn chấm công chỉ được đụng số lương của ĐÚNG người được tick.

- Người KHÔNG có cờ: `payment_days` / `absent_days` / LWP y hệt trước và sau (bất biến cứng).
- Người CÓ cờ: công = số ngày làm việc trong kỳ (đó là thay đổi CÓ CHỦ Ý, đã ký duyệt 2026-08-18).

Đo qua `SalarySlip.get_working_days_details` — KHÔNG dựng cấu trúc lương, vì
`make_employee_salary_slip` cần chart-of-accounts của `_Test Company` (miyano không có).
Cùng cách `hrms/tests/test_timekeeping_e2e.py` đang dùng.
"""

import frappe
from frappe.tests.utils import FrappeTestCase, change_settings
from frappe.utils import add_days, flt, getdate

from hrms.hr.attendance_exempt import fill_full_day, process_exempt_employees
from hrms.tests.isolation import PerTestRollback
from hrms.tests.vn_test_utils import default_company, test_employee

MONTH_START = getdate("2099-06-01")
MONTH_END = getdate("2099-06-30")


def working_days_details(employee, start, end):
	slip = frappe.new_doc("Salary Slip")
	slip.employee = employee
	slip.company = default_company()
	slip.start_date = getdate(start)
	slip.end_date = getdate(end)
	slip.get_working_days_details()
	return frappe._dict(
		total=flt(slip.total_working_days),
		payment_days=flt(slip.payment_days),
		absent_days=flt(slip.absent_days),
		lwp=flt(slip.leave_without_pay),
	)


class TestExemptPayroll(PerTestRollback, FrappeTestCase):
	@change_settings("Payroll Settings", {"payroll_based_on": "Attendance"})
	def test_sweep_does_not_touch_plain_employee(self):
		"""BẤT BIẾN CỨNG: lượt quét chạy trên dữ liệu THẬT của tháng này mà người không có cờ không
		đổi một con số nào, và không có Attendance nào được sinh cho họ."""
		plain = test_employee("payroll_plain@miyano.test")
		frappe.db.set_value(
			"Employee", plain, {"custom_exempt_from_checkin": 0, "relieving_date": None, "status": "Active"}
		)
		start = add_days(getdate(), -31)
		end = add_days(getdate(), -1)

		before = working_days_details(plain, start, end)
		rows_before = frappe.db.count("Attendance", {"employee": plain})

		process_exempt_employees()

		self.assertEqual(working_days_details(plain, start, end), before)
		self.assertEqual(frappe.db.count("Attendance", {"employee": plain}), rows_before)

	@change_settings("Payroll Settings", {"payroll_based_on": "Attendance"})
	def test_exempt_employee_is_paid_every_working_day(self):
		emp = test_employee("payroll_exempt@miyano.test")
		frappe.db.set_value(
			"Employee",
			emp,
			{
				"custom_exempt_from_checkin": 1,
				"custom_exempt_from_checkin_from": MONTH_START,
				"relieving_date": None,
				"status": "Active",
			},
		)
		day = MONTH_START
		while day <= MONTH_END:
			fill_full_day(emp, day)
			day = add_days(day, 1)

		res = working_days_details(emp, MONTH_START, MONTH_END)
		self.assertEqual(res.absent_days, 0.0, "người miễn chấm công không còn ngày vắng nào")
		self.assertEqual(res.lwp, 0.0)
		self.assertEqual(res.payment_days, res.total, "đủ công cả kỳ")
