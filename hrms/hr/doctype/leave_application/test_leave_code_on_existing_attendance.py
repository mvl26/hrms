# Copyright (c) 2026, Miyano Việt Nam.
"""Đơn nghỉ duyệt ĐÈ LÊN ngày đã bị chấm Vắng: mã công phải đổi theo loại nghỉ, không kẹt ở `V`.

Bối cảnh: job `hourly_long` tạo Attendance `Absent` (mã `V`) khi nhân viên không có checkin. Đơn
nghỉ duyệt sau đi nhánh `db_set` của upstream `create_or_update_attendance` — ghi thẳng DB nên
`before_validate` (và cầu nối mã công) KHÔNG chạy, mã `V` nằm nguyên trong khi `status` đã là
`On Leave`. Bảng công tháng gom theo category của mã nên ngày đó đếm vào cột Vắng thay vì cột đúng.

Chạy qua harness rollback (KHÔNG bench run-tests trên miyano).
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from hrms.tests.isolation import PerTestRollback
from hrms.tests.vn_test_utils import test_employee


class TestLeaveCodeOnExistingAttendance(PerTestRollback, FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.year = 2099
		cls.emp = test_employee()
		cls.company = frappe.db.get_value("Employee", cls.emp, "company")

	def _absent_attendance(self, date):
		"""Bản ghi Vắng như auto-attendance sinh ra khi không có checkin."""
		att = frappe.get_doc(
			{
				"doctype": "Attendance",
				"employee": self.emp,
				"attendance_date": date,
				"company": self.company,
				"status": "Absent",
			}
		)
		att.insert(ignore_permissions=True)
		att.submit()
		att.reload()
		return att

	def _alloc(self, leave_type, days=30):
		a = frappe.get_doc(
			{
				"doctype": "Leave Allocation",
				"employee": self.emp,
				"leave_type": leave_type,
				"from_date": f"{self.year}-01-01",
				"to_date": f"{self.year}-12-31",
				"new_leaves_allocated": days,
				"company": self.company,
			}
		)
		a.insert(ignore_permissions=True)
		a.submit()
		return a

	def _approve_leave(self, leave_type, date, reason=None):
		la = frappe.get_doc(
			{
				"doctype": "Leave Application",
				"employee": self.emp,
				"leave_type": leave_type,
				"from_date": date,
				"to_date": date,
				"company": self.company,
				"status": "Approved",
			}
		)
		if reason:
			la.custom_leave_reason = reason
		la.insert(ignore_permissions=True)
		la.submit()
		return la

	def _att_row(self, date):
		return frappe.db.get_value(
			"Attendance",
			{"employee": self.emp, "attendance_date": date, "docstatus": ("<", 2)},
			["status", "leave_type", "half_day_status", "custom_attendance_code", "custom_work_credit"],
			as_dict=True,
		)

	def test_absent_then_sick_leave_approved_gets_sick_code(self):
		"""Loại nghỉ NGOÀI quỹ phép năm: `Nghỉ ốm` → mã `Ô`, không được kẹt ở `V`."""
		date = f"{self.year}-03-10"
		self._alloc("Nghỉ ốm")
		att = self._absent_attendance(date)
		self.assertEqual(att.custom_attendance_code, "V", "tiền đề: auto-attendance ghi V")

		self._approve_leave("Nghỉ ốm", date)

		row = self._att_row(date)
		self.assertEqual(row.status, "On Leave")
		self.assertEqual(row.leave_type, "Nghỉ ốm")
		self.assertEqual(row.custom_attendance_code, "Ô", "mã công phải theo loại nghỉ, không kẹt ở V")

	def test_absent_then_pool_leave_approved_gets_p(self):
		"""Quỹ phép năm vốn đã chạy đúng — chốt lại để bản sửa không làm hỏng."""
		date = f"{self.year}-03-11"
		self._alloc("Nghỉ phép năm", 12)
		self._absent_attendance(date)
		self._approve_leave("Nghỉ phép năm", date, reason="Nghỉ phép năm")

		row = self._att_row(date)
		self.assertEqual(row.custom_attendance_code, "P")

	def test_maternity_leave_over_absent(self):
		"""Loại nghỉ khác nữa: `Nghỉ thai sản` → `TS`."""
		date = f"{self.year}-03-12"
		self._alloc("Nghỉ thai sản", 180)
		self._absent_attendance(date)
		self._approve_leave("Nghỉ thai sản", date)

		self.assertEqual(self._att_row(date).custom_attendance_code, "TS")

	def test_payroll_fields_untouched(self):
		"""Sửa mã công là THUẦN HIỂN THỊ: status/leave_type/half_day_status đúng như đơn nghỉ đặt."""
		date = f"{self.year}-03-13"
		self._alloc("Nghỉ ốm")
		self._absent_attendance(date)
		self._approve_leave("Nghỉ ốm", date)

		row = self._att_row(date)
		self.assertEqual(row.status, "On Leave")
		self.assertEqual(row.leave_type, "Nghỉ ốm")
		self.assertIsNone(row.half_day_status)

	def test_unmapped_leave_type_leaves_code_alone(self):
		"""Loại nghỉ chưa có Attendance Code nào trỏ tới: KHÔNG bịa mã, để nguyên."""
		lt = frappe.get_doc({"doctype": "Leave Type", "leave_type_name": "Nghỉ thử chưa map", "is_lwp": 0})
		lt.insert(ignore_permissions=True)

		date = f"{self.year}-03-14"
		self._alloc(lt.name)
		self._absent_attendance(date)
		self._approve_leave(lt.name, date)

		row = self._att_row(date)
		self.assertEqual(row.status, "On Leave")
		self.assertEqual(row.leave_type, lt.name)
		# không map được thì giữ nguyên mã cũ, tuyệt đối không tự chế mã mới
		self.assertEqual(row.custom_attendance_code, "V")
