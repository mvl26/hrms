# Copyright (c) 2026, Miyano Việt Nam.
import frappe
from frappe.tests.utils import FrappeTestCase

from hrms.tests.isolation import PerTestRollback


def create_attendance_code(code, **kwargs):
	"""Insert (or replace) an Attendance Code for tests."""
	if frappe.db.exists("Attendance Code", code):
		frappe.delete_doc("Attendance Code", code, force=True)
	doc = frappe.get_doc(
		{
			"doctype": "Attendance Code",
			"code": code,
			"code_name": kwargs.pop("code_name", code),
			"maps_to_status": kwargs.pop("maps_to_status", "Present"),
		}
	)
	doc.update(kwargs)
	return doc.insert()


class TestAttendanceCode(PerTestRollback, FrappeTestCase):
	def test_record_is_named_after_its_code(self):
		doc = create_attendance_code("X", code_name="Công đủ ngày")
		self.assertEqual(doc.name, "X")
		self.assertEqual(doc.code_name, "Công đủ ngày")

	def test_defaults_full_paid_work_day(self):
		doc = create_attendance_code("XD")
		self.assertEqual(doc.work_fraction, 1)
		self.assertEqual(doc.is_paid, 1)

	def test_code_must_be_unique(self):
		create_attendance_code("P", maps_to_status="On Leave")
		with self.assertRaises(frappe.exceptions.DuplicateEntryError):
			frappe.get_doc(
				{
					"doctype": "Attendance Code",
					"code": "P",
					"code_name": "duplicate",
					"maps_to_status": "On Leave",
				}
			).insert()

	def test_maps_to_status_is_mandatory(self):
		doc = frappe.get_doc({"doctype": "Attendance Code", "code": "NN", "code_name": "no status"})
		with self.assertRaises(frappe.exceptions.MandatoryError):
			doc.insert()

	def test_leave_type_is_optional(self):
		doc = create_attendance_code("K", maps_to_status="Absent", work_fraction=0, is_paid=0)
		self.assertIn(doc.leave_type, (None, ""))
		self.assertEqual(doc.work_fraction, 0)
		self.assertEqual(doc.is_paid, 0)
