# Copyright (c) 2026, Miyano Việt Nam.
"""Nghỉ phép nửa ngày KHÔNG được trừ lương thêm lần nữa.

Nửa ngày nghỉ phép năm là nghỉ CÓ LƯƠNG, nửa còn lại nhân viên đi làm ⇒ ngày đó phải trả đủ công.
Nếu `half_day_status` bị đặt thành "Absent", `get_half_absent_days` sẽ trừ thêm 0,5 ngày: nhân viên
vừa mất nửa ngày quỹ phép vừa mất nửa ngày lương cho cùng một nửa ngày.

Test này chốt lại rằng đường đơn nghỉ (Leave Application → Attendance) sinh ra `half_day_status =
"Present"`. Nó ra đời sau khi phát hiện trên site có 2 bản ghi `1/2P` mang "Absent" — hoá ra là dữ
liệu seed demo ghi sai chứ không phải code sai (2026-07-29). Có test rồi thì lần sau phân biệt được
ngay hai chuyện đó mà không phải dựng lại thí nghiệm.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from hrms.tests.isolation import PerTestRollback
from hrms.tests.vn_test_utils import test_employee


class TestHalfDayLeaveIsNotDoubleDocked(PerTestRollback, FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.emp = test_employee()
		cls.company = frappe.db.get_value("Employee", cls.emp, "company")

	def half_day_leave(self, date="2099-03-04", period="Sáng"):
		alloc = frappe.get_doc(
			{
				"doctype": "Leave Allocation",
				"employee": self.emp,
				"leave_type": "Nghỉ phép năm",
				"from_date": "2099-01-01",
				"to_date": "2099-12-31",
				"new_leaves_allocated": 12,
				"company": self.company,
			}
		)
		alloc.insert()
		alloc.submit()

		leave = frappe.get_doc(
			{
				"doctype": "Leave Application",
				"employee": self.emp,
				"leave_type": "Nghỉ phép năm",
				"from_date": date,
				"to_date": date,
				"half_day": 1,
				"half_day_date": date,
				"company": self.company,
				"status": "Approved",
				"custom_leave_reason": "Nghỉ phép năm",
				"custom_half_day_period": period,
			}
		)
		leave.insert()
		leave.submit()
		return frappe.db.get_value(
			"Attendance",
			{"employee": self.emp, "attendance_date": date, "docstatus": ["<", 2]},
			["name", "status", "leave_type", "half_day_status", "custom_attendance_code"],
			as_dict=True,
		)

	def test_the_other_half_is_present_not_absent(self):
		att = self.half_day_leave()
		self.assertIsNotNone(att, "đơn nghỉ nửa ngày phải sinh ra Attendance")
		self.assertEqual(att.status, "Half Day")
		self.assertEqual(att.leave_type, "Nghỉ phép năm")
		self.assertEqual(att.custom_attendance_code, "1/2P")
		self.assertEqual(
			att.half_day_status,
			"Present",
			"nửa còn lại là đi làm; đặt Absent sẽ khiến payroll trừ oan thêm 0,5 ngày",
		)

	def test_payroll_pays_the_full_day(self):
		"""Ngày nghỉ phép nửa ngày phải được trả ĐỦ: nửa làm + nửa phép có lương."""
		self.half_day_leave()

		slip = frappe.new_doc("Salary Slip")
		slip.employee = self.emp
		slip.company = self.company
		slip.start_date = "2099-03-01"
		slip.end_date = "2099-03-31"
		slip.get_working_days_details()

		self.assertEqual(frappe.utils.flt(slip.absent_days), 0.0, "không được tính nửa ngày vắng")
		self.assertEqual(frappe.utils.flt(slip.leave_without_pay), 0.0, "phép năm là nghỉ CÓ lương")
