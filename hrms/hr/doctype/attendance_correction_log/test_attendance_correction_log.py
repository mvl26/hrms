# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase

from hrms.tests.isolation import PerTestRollback
from hrms.tests.vn_test_utils import test_employee


class TestAttendanceCorrectionLog(PerTestRollback, FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.emp = test_employee()

	def mk(self, **extra):
		return frappe.get_doc(
			{
				"doctype": "Attendance Correction Log",
				"attendance": self.attendance(),
				"employee": self.emp,
				"attendance_date": "2099-03-04",
				"old_code": "V",
				"new_code": "X",
				"old_status": "Absent",
				"new_status": "Present",
				"reason": "quên chấm công, có xác nhận của quản lý",
				**extra,
			}
		)

	def attendance(self):
		if not getattr(self, "_att", None):
			doc = frappe.get_doc(
				{
					"doctype": "Attendance",
					"employee": self.emp,
					"attendance_date": "2099-03-04",
					"status": "Present",
				}
			).insert()
			self._att = doc.name
		return self._att

	def test_reason_is_mandatory(self):
		with self.assertRaises(frappe.exceptions.MandatoryError):
			self.mk(reason=None).insert()

	def test_it_records_both_sides_and_stamps_the_author(self):
		log = self.mk()
		log.insert()
		self.assertEqual(log.old_status, "Absent")
		self.assertEqual(log.new_status, "Present")
		self.assertEqual(log.corrected_by, frappe.session.user)
		self.assertTrue(log.corrected_on)

	def test_it_cannot_be_edited_after_creation(self):
		log = self.mk()
		log.insert()
		log.reason = "đổi ý"
		with self.assertRaises(frappe.exceptions.ValidationError):
			log.save()

	def test_log_correction_helper_writes_one_row(self):
		from hrms.hr.doctype.attendance_correction_log.attendance_correction_log import log_correction

		att = frappe.get_doc("Attendance", self.attendance())
		name = log_correction(
			att,
			{"custom_attendance_code": "V", "status": "Absent", "leave_type": None, "half_day_status": None},
			{"custom_attendance_code": "X", "status": "Present", "leave_type": None, "half_day_status": None},
			"sửa theo biên bản",
		)
		row = frappe.get_doc("Attendance Correction Log", name)
		self.assertEqual(row.attendance, att.name)
		self.assertEqual((row.old_code, row.new_code), ("V", "X"))
		self.assertEqual(row.reason, "sửa theo biên bản")
