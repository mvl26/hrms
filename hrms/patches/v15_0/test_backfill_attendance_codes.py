# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# See license.txt
"""Tests for the attendance-code backfill patch. Records are created code-less (stripped after
insert) to mimic pre-feature / auto-attendance rows, then backfilled."""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import getdate

from hrms.patches.v15_0.backfill_attendance_codes import backfill


class TestBackfillAttendanceCodes(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.emp = frappe.db.get_value("Employee", {}, "name")

	def _bare(self, day, status, leave_type=None, half_day_status=None):
		"""Insert an attendance then strip its code fields, simulating a pre-feature record."""
		doc = frappe.new_doc("Attendance")
		doc.employee = self.emp
		doc.attendance_date = getdate(f"2098-05-{day:02d}")
		doc.status = status
		doc.leave_type = leave_type
		doc.half_day_status = half_day_status
		doc.flags.ignore_validate = True
		doc.insert(ignore_permissions=True)
		doc.submit()
		frappe.db.set_value(
			"Attendance", doc.name, {"custom_attendance_code": None, "custom_cong": 0}, update_modified=False
		)
		return doc.name

	def _code(self, name):
		return frappe.db.get_value("Attendance", name, ["custom_attendance_code", "custom_cong"], as_dict=True)

	def test_backfill_populates_codes(self):
		n_present = self._bare(1, "Present")
		n_leave = self._bare(2, "On Leave", "Nghỉ phép năm")
		n_absent = self._bare(3, "Absent")
		n_halfday = self._bare(4, "Half Day", half_day_status="Absent")

		backfill()

		self.assertEqual(self._code(n_present).custom_attendance_code, "X")
		self.assertEqual(self._code(n_present).custom_cong, 1.0)
		self.assertEqual(self._code(n_leave).custom_attendance_code, "P")
		self.assertEqual(self._code(n_leave).custom_cong, 0.0)
		self.assertEqual(self._code(n_absent).custom_attendance_code, "V")
		self.assertEqual(self._code(n_halfday).custom_attendance_code, "NN")
		self.assertEqual(self._code(n_halfday).custom_cong, 0.5)

	def test_backfill_preserves_existing_codes(self):
		# a record that already carries a code must NOT be overwritten
		n = self._bare(6, "Present")
		frappe.db.set_value("Attendance", n, "custom_attendance_code", "NN", update_modified=False)
		backfill()
		self.assertEqual(self._code(n).custom_attendance_code, "NN")

	def test_dry_run_writes_nothing(self):
		n = self._bare(7, "Present")
		summary = backfill(dry_run=True)
		self.assertEqual(summary.get("X"), 1)
		self.assertIn(self._code(n).custom_attendance_code, (None, ""))  # still empty
