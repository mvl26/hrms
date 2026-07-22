# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# See license.txt
"""Công cụ dựng lại Attendance từ checkin — bất biến quan trọng nhất là KHÔNG đụng ngày nghỉ phép."""

import datetime

import frappe
from frappe.tests.utils import FrappeTestCase

from hrms.rebuild_attendance_from_checkin import (
	FIELDS_BACKUP,
	month_bounds,
	rebuild,
	shift_employees,
)

D = datetime.date
SHIFT = "Ca Hành Chính"


class TestRebuildAttendanceFromCheckin(FrappeTestCase):
	def test_month_bounds(self):
		self.assertEqual(month_bounds(2026, 6), (D(2026, 6, 1), D(2026, 6, 30)))
		self.assertEqual(month_bounds(2026, 2), (D(2026, 2, 1), D(2026, 2, 28)))
		self.assertEqual(month_bounds(2026, 12), (D(2026, 12, 1), D(2026, 12, 31)))

	def test_backup_captures_leave_application_link(self):
		"""Cả thiết kế dựa vào cột này để biết bản nào do đơn nghỉ sinh ra — thiếu là xoá nhầm."""
		self.assertIn("leave_application", FIELDS_BACKUP)

	def test_dry_run_changes_nothing_and_separates_leave_records(self):
		if not frappe.db.exists("Shift Type", SHIFT):
			self.skipTest(f"site không có ca {SHIFT}")

		start, end = month_bounds(2026, 6)
		employees = shift_employees(SHIFT, start, end)
		if not employees:
			self.skipTest("không có nhân viên nào thuộc ca trong kỳ")

		def counts():
			return (
				frappe.db.count("Attendance", {"attendance_date": ["between", [start, end]]}),
				frappe.db.count("Employee Checkin", {"time": ["between", [str(start), f"{end} 23:59:59"]]}),
			)

		before = counts()
		plan = rebuild(2026, 6, shift=SHIFT, apply=False)
		self.assertEqual(counts(), before, "chạy thử không được đổi bất cứ thứ gì")

		# bản ghi giữ lại + bản ghi xoá phải cộng đúng tổng: không bỏ sót, không đếm trùng
		self.assertEqual(
			plan["attendance_keep_from_leave"] + plan["attendance_to_delete"],
			plan["attendance_total"],
		)
		self.assertIn("CHẠY THỬ", plan["note"])

	def test_shift_employees_includes_default_shift_holders(self):
		if not frappe.db.exists("Shift Type", SHIFT):
			self.skipTest(f"site không có ca {SHIFT}")

		start, end = month_bounds(2026, 6)
		found = set(shift_employees(SHIFT, start, end))
		by_default = set(frappe.get_all("Employee", filters={"default_shift": SHIFT}, pluck="name"))
		self.assertTrue(by_default <= found, "người lấy ca này làm mặc định phải nằm trong phạm vi")
