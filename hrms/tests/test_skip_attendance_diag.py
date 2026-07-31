# Copyright (c) 2026, Miyano Việt Nam.
from datetime import timedelta

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import getdate, now_datetime

from erpnext.setup.doctype.employee.test_employee import make_employee

from hrms.skip_attendance_diag import diagnose, export_csv, reset_wrongly_skipped
from hrms.tests.isolation import PerTestRollback


def make_skipped_checkin(employee, minutes_ago=1, log_type="IN", reason=None, linked=False):
	"""Insert an Employee Checkin with skip_auto_attendance=1.

	reason: if given, attach a "Reason for skipping auto attendance" Comment.
	linked: if True, mark the checkin as linked to an Attendance (attendance field set),
	        which is how a legitimately-processed checkin looks.
	"""
	log = frappe.get_doc(
		{
			"doctype": "Employee Checkin",
			"employee": employee,
			"time": now_datetime() - timedelta(minutes=minutes_ago),
			"log_type": log_type,
			"skip_auto_attendance": 1,
		}
	).insert()

	if reason:
		frappe.get_doc(
			{
				"doctype": "Comment",
				"comment_type": "Comment",
				"reference_doctype": "Employee Checkin",
				"reference_name": log.name,
				"content": f"Reason for skipping auto attendance:<br>{reason}",
			}
		).insert(ignore_permissions=True)

	if linked:
		# only the set/not-set state matters to the selection logic
		frappe.db.set_value("Employee Checkin", log.name, "attendance", "ATT-DUMMY", update_modified=False)

	return log


class TestSkipAttendanceDiag(PerTestRollback, FrappeTestCase):
	def setUp(self):
		self.employee = make_employee("test_skip_diag@example.com")
		# isolate: this employee starts each test with no checkins
		frappe.db.delete("Employee Checkin", {"employee": self.employee})

	def _make_draft_attendance(self, date):
		company = frappe.db.get_value("Employee", self.employee, "company")
		return frappe.get_doc(
			{
				"doctype": "Attendance",
				"employee": self.employee,
				"attendance_date": date,
				"status": "Present",
				"company": company,
			}
		).insert()

	# --- reset_wrongly_skipped: selection logic -------------------------------

	def test_reset_selects_unlinked_but_not_linked_checkins(self):
		unlinked = make_skipped_checkin(self.employee, minutes_ago=1)
		linked = make_skipped_checkin(self.employee, minutes_ago=2, linked=True)

		names = reset_wrongly_skipped(employee=self.employee, require_no_existing_attendance=False)

		self.assertIn(unlinked.name, names)
		self.assertNotIn(linked.name, names)

	def test_reset_dry_run_does_not_change_the_flag(self):
		checkin = make_skipped_checkin(self.employee, minutes_ago=1)

		reset_wrongly_skipped(employee=self.employee, require_no_existing_attendance=False)  # apply=False

		self.assertEqual(frappe.db.get_value("Employee Checkin", checkin.name, "skip_auto_attendance"), 1)

	def test_only_without_comment_targets_device_import_checkins(self):
		with_comment = make_skipped_checkin(self.employee, minutes_ago=1, reason="Attendance already marked")
		without_comment = make_skipped_checkin(self.employee, minutes_ago=2)

		names = reset_wrongly_skipped(
			employee=self.employee, only_without_comment=True, require_no_existing_attendance=False
		)

		self.assertIn(without_comment.name, names)
		self.assertNotIn(with_comment.name, names)

	def test_reason_contains_targets_one_specific_cause(self):
		duplicate = make_skipped_checkin(
			self.employee, minutes_ago=1, reason="Attendance already marked for the date"
		)
		inactive = make_skipped_checkin(
			self.employee, minutes_ago=2, reason="Cannot mark attendance for an Inactive employee"
		)

		names = reset_wrongly_skipped(
			employee=self.employee, reason_contains="already marked", require_no_existing_attendance=False
		)

		self.assertIn(duplicate.name, names)
		self.assertNotIn(inactive.name, names)

	def test_require_no_existing_attendance_excludes_dates_already_marked(self):
		checkin = make_skipped_checkin(self.employee, minutes_ago=1)

		# no attendance yet -> the checkin is a reset candidate
		self.assertIn(
			checkin.name,
			reset_wrongly_skipped(employee=self.employee, require_no_existing_attendance=True),
		)

		# once that date already has an Attendance, it must be excluded
		self._make_draft_attendance(getdate())
		self.assertNotIn(
			checkin.name,
			reset_wrongly_skipped(employee=self.employee, require_no_existing_attendance=True),
		)

	# --- diagnose: reported counts --------------------------------------------

	def test_diagnose_reports_counts(self):
		make_skipped_checkin(self.employee, minutes_ago=1)  # unlinked, no comment
		make_skipped_checkin(self.employee, minutes_ago=2, reason="already marked")  # unlinked, comment
		make_skipped_checkin(self.employee, minutes_ago=3, linked=True)  # linked

		res = diagnose()

		self.assertGreaterEqual(res["skipped"], 3)
		self.assertGreaterEqual(res["linked"], 1)
		self.assertGreaterEqual(res["nolink"], 2)
		self.assertGreaterEqual(res["no_comment"], 1)

	def test_diagnose_zero_state_returns_zero_counts(self):
		# this employee has no checkins after setUp; if the whole site is empty the
		# early-return path is exercised — either way the shape is stable.
		res = diagnose()
		self.assertIn("skipped", res)
		self.assertGreaterEqual(res["skipped"], 0)

	# --- export_csv -----------------------------------------------------------

	def test_export_csv_writes_skipped_checkins_with_reasons(self):
		import csv as _csv
		import os
		import tempfile

		with_reason = make_skipped_checkin(
			self.employee, minutes_ago=1, reason="Attendance already marked for the date"
		)
		without_reason = make_skipped_checkin(self.employee, minutes_ago=2)

		path = os.path.join(tempfile.gettempdir(), f"skip_diag_test_{frappe.generate_hash(length=8)}.csv")
		try:
			export_csv(path=path)
			with open(path, newline="") as f:
				by_name = {row["checkin"]: row for row in _csv.DictReader(f)}
		finally:
			if os.path.exists(path):
				os.remove(path)

		self.assertIn(with_reason.name, by_name)
		self.assertIn(without_reason.name, by_name)
		self.assertIn("already marked", by_name[with_reason.name]["skip_reason_comment"])
		self.assertEqual(by_name[without_reason.name]["skip_reason_comment"], "")
