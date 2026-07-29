# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# See license.txt
"""Khoá kỳ: chốt công rồi thì ngày công trong kỳ không thêm/sửa/huỷ được nữa."""

import frappe
from frappe.tests.utils import FrappeTestCase

from hrms.hr.period_lock import is_period_locked, locking_sheet
from hrms.tests.isolation import PerTestRollback
from hrms.tests.vn_test_utils import ensure_short_hours_code


class TestPeriodLock(PerTestRollback, FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		ensure_short_hours_code()
		cls.emp = frappe.db.get_value("Employee", {"status": "Active"}, "name")
		cls.company = frappe.db.get_value("Employee", cls.emp, "company")

	def mk_sheet(self, month, year=2099, submit=True, department=None):
		sheet = frappe.get_doc(
			{
				"doctype": "Monthly Attendance Sheet",
				"company": self.company,
				"month": str(month),
				"year": year,
				"department": department,
			}
		).insert()
		if submit:
			sheet.submit()
		return sheet

	def mk_attendance(self, day, month=11, year=2099, submit=True, **kw):
		doc = frappe.get_doc(
			{
				"doctype": "Attendance",
				"employee": self.emp,
				"attendance_date": f"{year}-{month:02d}-{day:02d}",
				"company": self.company,
				"status": "Present",
				**kw,
			}
		).insert()
		if submit:
			doc.submit()
		return doc

	def test_an_open_period_is_not_locked(self):
		self.assertFalse(is_period_locked(self.emp, "2099-11-05"))

	def test_a_submitted_sheet_locks_its_own_month_only(self):
		sheet = self.mk_sheet(11)
		self.assertEqual(locking_sheet(self.emp, "2099-11-05"), sheet.name)
		self.assertIsNone(locking_sheet(self.emp, "2099-12-05"))

	def test_a_draft_sheet_locks_nothing(self):
		self.mk_sheet(11, submit=False)
		self.assertFalse(is_period_locked(self.emp, "2099-11-05"))

	def test_a_cancelled_sheet_reopens_the_period(self):
		sheet = self.mk_sheet(11)
		self.assertTrue(is_period_locked(self.emp, "2099-11-05"))
		sheet.cancel()
		self.assertFalse(is_period_locked(self.emp, "2099-11-05"))

	def test_a_sheet_for_another_department_does_not_lock_this_employee(self):
		other = frappe.db.get_value("Department", {"name": ["!=", ""]}, "name")
		emp_dept = frappe.db.get_value("Employee", self.emp, "department")
		if not other or other == emp_dept:
			self.skipTest("site không có phòng ban khác để phân biệt")
		self.mk_sheet(11, department=other)
		self.assertFalse(is_period_locked(self.emp, "2099-11-05"))

	def test_creating_attendance_inside_a_locked_period_is_blocked(self):
		self.mk_sheet(11)
		with self.assertRaises(frappe.exceptions.ValidationError):
			self.mk_attendance(6)

	def test_cancelling_attendance_inside_a_locked_period_is_blocked(self):
		att = self.mk_attendance(7)
		self.mk_sheet(11)
		with self.assertRaises(frappe.exceptions.ValidationError):
			att.cancel()

	def test_correcting_attendance_inside_a_locked_period_is_blocked(self):
		from hrms.hr.attendance_review import apply_correction

		att = self.mk_attendance(8)
		self.mk_sheet(11)
		with self.assertRaises(frappe.exceptions.ValidationError):
			apply_correction(att.name, "1/2X", "sửa sau khi đã chốt")

	def test_correcting_is_allowed_again_after_the_sheet_is_cancelled(self):
		from hrms.hr.attendance_review import apply_correction

		att = self.mk_attendance(9)
		sheet = self.mk_sheet(11)
		sheet.cancel()
		apply_correction(att.name, "1/2X", "mở lại kỳ để sửa theo biên bản")
		self.assertEqual(frappe.db.get_value("Attendance", att.name, "status"), "Half Day")
