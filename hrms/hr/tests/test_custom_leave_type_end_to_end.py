# Copyright (c) 2026, Miyano Việt Nam.
"""Loại nghỉ HR tự tạo phải chạy ĐÚNG như loại nghỉ fixtures — đó là cả mục tiêu của thay đổi này.

Tái hiện đúng sự cố 2026-08-24 (spec §1.1): loại nghỉ tạo tay không gắn mã cho ra 0 công, im lặng.
Sau thay đổi: chưa gắn mã thì bị CHẶN; gắn một dòng Mã Công là ra đúng mã và CÔNG = 1, trên cả hai
đường (ngày chưa có chấm công, và ngày đã có bản ghi Vắng).

Chạy qua harness rollback (KHÔNG bench run-tests trên miyano).
"""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import getdate

from hrms.tests.isolation import PerTestRollback
from hrms.tests.vn_test_utils import default_company, test_employee

LEAVE_TYPE = "Nghỉ chuyên cần Miyano"
CODE = "CC"
DAY_FRESH = "2099-06-15"
DAY_WITH_ABSENT = "2099-06-16"


class TestCustomLeaveTypeEndToEnd(PerTestRollback, FrappeTestCase):
	def setUp(self):
		self.employee = test_employee("loai_nghi_tu_tao@codes.com")
		self.company = default_company()
		frappe.get_doc(
			{"doctype": "Leave Type", "leave_type_name": LEAVE_TYPE, "is_lwp": 0, "max_leaves_allowed": 30}
		).insert(ignore_permissions=True)

	def add_code(self):
		"""ĐÚNG MỘT dòng master data — đây là toàn bộ việc HR phải làm cho một loại nghỉ mới."""
		frappe.get_doc(
			{
				"doctype": "Attendance Code",
				"code": CODE,
				"code_name": "Nghỉ chuyên cần",
				"category": "Việc riêng",
				"work_fraction": 0,
				"is_paid": 1,
				"maps_to_status": "On Leave",
				"leave_type": LEAVE_TYPE,
			}
		).insert(ignore_permissions=True)

	def allocate(self):
		alloc = frappe.get_doc(
			{
				"doctype": "Leave Allocation",
				"employee": self.employee,
				"leave_type": LEAVE_TYPE,
				"from_date": "2099-01-01",
				"to_date": "2099-12-31",
				"new_leaves_allocated": 10,
			}
		)
		alloc.insert(ignore_permissions=True)
		alloc.submit()

	def apply_leave(self, day):
		la = frappe.get_doc(
			{
				"doctype": "Leave Application",
				"employee": self.employee,
				"leave_type": LEAVE_TYPE,
				"from_date": day,
				"to_date": day,
				"company": self.company,
				"status": "Approved",
				"leave_approver": frappe.session.user,
			}
		)
		la.insert(ignore_permissions=True)
		la.submit()
		return la

	def mark_absent(self, day):
		att = frappe.get_doc(
			{
				"doctype": "Attendance",
				"employee": self.employee,
				"attendance_date": day,
				"status": "Absent",
				"company": self.company,
			}
		)
		att.insert(ignore_permissions=True)
		att.submit()

	def attendance_of(self, leave_application):
		return frappe.get_all(
			"Attendance",
			filters={"leave_application": leave_application},
			fields=["status", "leave_type", "custom_attendance_code", "custom_work_credit"],
		)[0]

	def test_unmapped_leave_type_is_blocked_not_silently_zero(self):
		"""TRƯỚC: 0 công trong im lặng. SAU: chặn thẳng, kèm hướng dẫn."""
		self.allocate()
		with self.assertRaisesRegex(frappe.ValidationError, "mã công"):
			self.apply_leave(DAY_FRESH)

	def test_one_code_makes_a_fresh_day_worth_one_cong(self):
		"""Ngày chưa có chấm công → mã đúng, CÔNG = 1."""
		self.add_code()
		self.allocate()
		att = self.attendance_of(self.apply_leave(DAY_FRESH).name)
		self.assertEqual(att.status, "On Leave")
		self.assertEqual(att.leave_type, LEAVE_TYPE)
		self.assertEqual(att.custom_attendance_code, CODE)
		self.assertEqual(att.custom_work_credit, 1.0)

	def test_one_code_also_fixes_a_day_already_marked_absent(self):
		"""Ngày ĐÃ có bản ghi Vắng — đường `db_set` của upstream, chỗ mã `V` từng kẹt lại."""
		self.add_code()
		self.allocate()
		self.mark_absent(DAY_WITH_ABSENT)
		att = self.attendance_of(self.apply_leave(DAY_WITH_ABSENT).name)
		self.assertEqual(att.status, "On Leave")
		self.assertEqual(att.custom_attendance_code, CODE, "mã V không được kẹt lại")
		self.assertEqual(att.custom_work_credit, 1.0)

	def test_the_day_lands_in_the_right_column_of_the_monthly_sheet(self):
		"""Mã có nhóm "Việc riêng" → ngày đó phải vào đúng cột đó và cộng vào Tổng công."""
		from hrms.hr.report.monthly_attendance_report.monthly_attendance_report import get_sheet_rows

		self.add_code()
		self.allocate()
		self.apply_leave(DAY_FRESH)

		rows = [
			r
			for r in get_sheet_rows({"month": 6, "year": 2099, "company": self.company})
			if r["employee"] == self.employee
		]
		self.assertTrue(rows, "nhân viên phải có mặt trên bảng công")
		row = rows[0]
		self.assertEqual(row["days"].get(getdate(DAY_FRESH).day), CODE)
		self.assertEqual(row["totals"].get("Việc riêng"), 1.0)
		self.assertEqual(row["totals"].get("Tổng công"), 1.0, "nghỉ công ty trả phải vào Tổng công")
