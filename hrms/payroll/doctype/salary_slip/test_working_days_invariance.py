# Copyright (c) 2026, Miyano Việt Nam.
"""CỔNG: mẫu số lương phải giống hệt trước và sau khi tách lịch làm việc khỏi lịch nghỉ lễ.

Mỗi ca chạy hai lần — một lần khi Holiday List VẪN còn các dòng nghỉ cuối tuần (trạng thái hôm nay),
một lần sau khi đã gỡ chúng (trạng thái sau di trú, mô phỏng ngay trong savepoint của test). Vì
`set_working_days` ĐẶT con số tuyệt đối từ lịch tuần chứ không cộng/trừ delta, hai trạng thái phải
cho **cùng** kết quả; lệch nghĩa là hoặc lịch tuần khai sai, hoặc công thức sai.

KHÔNG được nới lỏng bộ test này để "cho xanh" — nó là thứ duy nhất đứng giữa một refactor lịch và
việc trả sai lương cho cả công ty.
"""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt, getdate

from hrms.tests.isolation import PerTestRollback
from hrms.tests.vn_test_utils import default_company, test_employee

FIELDS = ("total_working_days", "payment_days", "absent_days", "leave_without_pay")

MON_TO_FRI = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]

# Tháng 7/2026: 31 ngày, 23 ngày T2-T6, ngày lễ công ty 17/07 rơi thứ Sáu.
PERIOD_START, PERIOD_END = "2026-07-01", "2026-07-31"
JULY_SCHEDULED_DAYS = 23


class TestWorkingDaysInvariance(PerTestRollback, FrappeTestCase):
	def setUp(self):
		self.company = default_company()
		self.employee = test_employee("wd_invariance@codes.com")
		self.shift = "_Test Lich Tuan Invariance"
		if not frappe.db.exists("Shift Type", self.shift):
			frappe.get_doc(
				{
					"doctype": "Shift Type",
					"__newname": self.shift,
					"start_time": "8:0:0",
					"end_time": "17:0:0",
				}
			).insert(ignore_permissions=True)
		for idx, day in enumerate(MON_TO_FRI, start=1):
			frappe.get_doc(
				{
					"doctype": "Assignment Rule Day",
					"parent": self.shift,
					"parenttype": "Shift Type",
					"parentfield": "custom_working_days",
					"day": day,
					"idx": idx,
				}
			).insert(ignore_permissions=True)
		frappe.db.set_value("Employee", self.employee, "default_shift", self.shift)
		frappe.db.set_value("Employee", self.employee, "date_of_joining", "2020-01-01")
		frappe.db.set_value("Employee", self.employee, "relieving_date", None)
		frappe.db.set_value("Employee", self.employee, "holiday_list", self.make_holiday_list())
		frappe.clear_cache(doctype="Employee")

	def make_holiday_list(self) -> str:
		"""Lịch của trạng thái HÔM NAY: 104 dòng nghỉ cuối tuần + 1 dòng lễ, y như site thật."""
		name = f"_Test WD {self.company} 2026"
		if frappe.db.exists("Holiday List", name):
			frappe.delete_doc("Holiday List", name, force=True, ignore_permissions=True)
		doc = frappe.get_doc(
			{
				"doctype": "Holiday List",
				"holiday_list_name": name,
				"from_date": "2026-01-01",
				"to_date": "2026-12-31",
				"holidays": [
					{"holiday_date": "2026-07-17", "description": "Nghỉ lễ công ty", "weekly_off": 0}
				],
			}
		)
		doc.weekly_off = "Saturday"
		doc.get_weekly_off_dates()
		doc.weekly_off = "Sunday"
		doc.get_weekly_off_dates()
		doc.save(ignore_permissions=True)
		return doc.name

	def drop_weekly_off_rows(self):
		"""Mô phỏng bước di trú ngay trong savepoint của test."""
		hl = frappe.db.get_value("Employee", self.employee, "holiday_list")
		frappe.db.delete("Holiday", {"parent": hl, "weekly_off": 1})
		frappe.clear_cache()

	def numbers(self, start=PERIOD_START, end=PERIOD_END) -> dict:
		"""Bốn con số lương, đi qua ĐÚNG đường thật: controller tính rồi hook đặt lại."""
		from hrms.vn_payroll.salary_slip_hook import set_working_days

		slip = frappe.new_doc("Salary Slip")
		slip.employee = self.employee
		slip.company = frappe.db.get_value("Employee", self.employee, "company")
		slip.start_date = getdate(start)
		slip.end_date = getdate(end)
		slip.get_working_days_details()
		set_working_days(slip)
		return {f: flt(slip.get(f)) for f in FIELDS}

	def assert_invariant(self, start=PERIOD_START, end=PERIOD_END):
		"""Chạy cùng một ca ở hai trạng thái lịch và đòi hai kết quả giống hệt."""
		before = self.numbers(start, end)
		self.drop_weekly_off_rows()
		after = self.numbers(start, end)
		self.assertEqual(before, after, "mẫu số lương đổi khi gỡ dòng nghỉ cuối tuần")
		return after

	def mark(self, day, status, leave_type=None, half_day_status=None):
		att = frappe.get_doc(
			{
				"doctype": "Attendance",
				"employee": self.employee,
				"attendance_date": getdate(day),
				"company": self.company,
				"status": status,
				"leave_type": leave_type,
				"half_day_status": half_day_status,
			}
		)
		att.flags.ignore_validate = True
		att.insert(ignore_permissions=True)
		att.submit()
		return att.name

	# --- 8 ca biên -----------------------------------------------------------

	def test_plain_period(self):
		got = self.assert_invariant()
		self.assertEqual(got["total_working_days"], JULY_SCHEDULED_DAYS)

	def test_period_with_a_public_holiday_counts_it_into_the_denominator(self):
		"""Ngày lễ 17/07 NẰM TRONG mẫu số — dùng `working_*` thay `scheduled_*` là hụt đúng 1 ngày."""
		got = self.assert_invariant()
		self.assertEqual(got["total_working_days"], JULY_SCHEDULED_DAYS)

	def test_period_with_an_absent_day(self):
		self.mark("2026-07-21", "Absent")
		got = self.assert_invariant()
		self.assertEqual(got["absent_days"], 1.0)
		self.assertEqual(got["payment_days"], JULY_SCHEDULED_DAYS - 1)

	def test_period_with_a_half_day(self):
		self.mark("2026-07-21", "Half Day", half_day_status="Absent")
		got = self.assert_invariant()
		self.assertEqual(got["payment_days"], JULY_SCHEDULED_DAYS - 0.5)

	def test_employee_joining_mid_period(self):
		frappe.db.set_value("Employee", self.employee, "date_of_joining", "2026-07-16")
		frappe.clear_cache(doctype="Employee")
		got = self.assert_invariant()
		self.assertEqual(got["total_working_days"], JULY_SCHEDULED_DAYS)
		self.assertLess(got["payment_days"], JULY_SCHEDULED_DAYS)

	def test_employee_relieved_mid_period(self):
		frappe.db.set_value("Employee", self.employee, "relieving_date", "2026-07-15")
		frappe.db.set_value("Employee", self.employee, "status", "Left")
		frappe.clear_cache(doctype="Employee")
		got = self.assert_invariant()
		self.assertEqual(got["total_working_days"], JULY_SCHEDULED_DAYS)
		self.assertLess(got["payment_days"], JULY_SCHEDULED_DAYS)

	def test_period_made_entirely_of_rest_days(self):
		"""Kỳ toàn ngày nghỉ: mẫu số 0, không được chia 0 hay ra số âm."""
		got = self.assert_invariant("2026-07-25", "2026-07-26")  # T7 + CN
		self.assertEqual(got["total_working_days"], 0.0)
		self.assertEqual(got["payment_days"], 0.0)

	def test_lwp_greater_than_the_base_clamps_to_zero(self):
		"""Nhánh clamp của ERPNext: `base <= lwp` thì payment_days = 0, không phải số âm."""
		for day in range(1, 32):
			d = getdate(f"2026-07-{day:02d}")
			if d.weekday() < 5:
				self.mark(d, "On Leave", leave_type="Nghỉ không lương")
		got = self.assert_invariant()
		self.assertGreaterEqual(got["payment_days"], 0.0)
