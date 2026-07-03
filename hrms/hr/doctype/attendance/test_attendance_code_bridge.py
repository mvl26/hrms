# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# See license.txt
"""Unit tests for the VN attendance-code <-> native-status bridge (Attendance.before_validate).
Codes are exercised in isolation (before_validate, no insert) so native validation such as
check_leave_record does not mask the bridge's own output."""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import getdate


class TestAttendanceCodeBridge(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.emp = frappe.db.get_value("Employee", {}, "name")

	def _bridge(self, **codes):
		doc = frappe.get_doc(
			{"doctype": "Attendance", "employee": self.emp, "attendance_date": getdate(), **codes}
		)
		doc.before_validate()
		return doc

	def test_forward_full_workday(self):
		d = self._bridge(custom_attendance_code="X")
		self.assertEqual(d.status, "Present")
		self.assertIn(d.leave_type, (None, ""))
		self.assertEqual(d.custom_cong, 1.0)

	def test_forward_full_annual_leave(self):
		d = self._bridge(custom_attendance_code="P")
		self.assertEqual(d.status, "On Leave")
		self.assertEqual(d.leave_type, "Nghỉ phép năm")
		self.assertEqual(d.custom_cong, 0)

	def test_forward_full_unpaid_leave(self):
		d = self._bridge(custom_attendance_code="KL")
		self.assertEqual(d.status, "On Leave")
		self.assertEqual(d.leave_type, "Nghỉ không lương")
		self.assertEqual(d.custom_cong, 0)

	def test_forward_half_work_half_leave(self):
		# sáng=X + chiều=P -> Half Day, half_day_status Present, leave_type phép năm, công 0.5
		d = self._bridge(custom_morning_code="X", custom_afternoon_code="P")
		self.assertEqual(d.status, "Half Day")
		self.assertEqual(d.leave_type, "Nghỉ phép năm")
		self.assertEqual(d.half_day_status, "Present")
		self.assertEqual(d.custom_cong, 0.5)

	def test_reverse_derives_code_from_native_status(self):
		# a record with a native status but no code (auto-attendance / leave) -> derive display code
		d = self._bridge(status="Present")
		self.assertEqual(d.custom_attendance_code, "X")
		self.assertEqual(d.custom_cong, 1.0)

	def test_reverse_derives_leave_code(self):
		d = self._bridge(status="On Leave", leave_type="Nghỉ ốm")
		self.assertEqual(d.custom_attendance_code, "Ô")
		self.assertEqual(d.custom_cong, 0)
