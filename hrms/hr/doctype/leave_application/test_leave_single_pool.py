# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# See license.txt
"""Bậc 2 — gộp một quỹ phép năm: đơn P/Ô/Cô cùng rút "Nghỉ phép năm" nhưng bảng công hiện riêng.

Chạy qua harness rollback (KHÔNG bench run-tests trên miyano)."""

import frappe
from frappe.tests.utils import FrappeTestCase


class TestLeaveSinglePool(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.emp = frappe.db.get_value("Employee", {"status": "Active"}, "name")
		cls.company = frappe.db.get_value("Employee", cls.emp, "company")
		cls.year = 2099

	def _alloc(self, leave_type, days):
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

	def _leave_app(self, leave_type, from_d, to_d, code=None):
		la = frappe.get_doc(
			{
				"doctype": "Leave Application",
				"employee": self.emp,
				"leave_type": leave_type,
				"from_date": from_d,
				"to_date": to_d,
				"company": self.company,
				"status": "Approved",
			}
		)
		if code:
			la.custom_attendance_code = code
		la.insert(ignore_permissions=True)
		la.submit()
		return la

	def test_annual_leave_app_creates_P_attendance(self):
		self._alloc("Nghỉ phép năm", 12)
		la = self._leave_app("Nghỉ phép năm", f"{self.year}-03-05", f"{self.year}-03-05")
		att = frappe.db.get_value(
			"Attendance",
			{"leave_application": la.name},
			["status", "leave_type", "custom_attendance_code"],
			as_dict=True,
		)
		self.assertIsNotNone(att, "đơn duyệt phải sinh Attendance")
		self.assertEqual(att.status, "On Leave")
		self.assertEqual(att.leave_type, "Nghỉ phép năm")
		self.assertEqual(att.custom_attendance_code, "P")  # bridge reverse-derive
