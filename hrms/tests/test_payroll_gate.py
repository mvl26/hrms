# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# See license.txt
"""Tooling for the prod payroll sign-off gates (tasks/plan-prod-deploy.md T1 + T4)."""

import json
import os
import tempfile

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import get_datetime

from hrms.payroll_gate import (
	capture_payroll_baseline,
	classifier_delta,
	compare_payroll_baseline,
	diff_payroll_rows,
)


def slip(name, employee="EMP-1", payment_days=22, absent_days=0, leave_without_pay=0):
	return {
		"name": name,
		"employee": employee,
		"start_date": "2026-09-01",
		"payment_days": payment_days,
		"absent_days": absent_days,
		"leave_without_pay": leave_without_pay,
		"gross_pay": 10_000_000.0,
		"net_pay": 9_000_000.0,
	}


class TestDiffPayrollRows(FrappeTestCase):
	"""Pure diff logic — the heart of the T1/T2 'byte-identical' gate."""

	def test_identical_snapshots_report_no_difference(self):
		rows = [slip("SS-1"), slip("SS-2", employee="EMP-2")]
		result = diff_payroll_rows(rows, list(rows))

		self.assertTrue(result["identical"])
		self.assertEqual(result["changed"], [])
		self.assertEqual(result["missing"], [])
		self.assertEqual(result["added"], [])

	def test_a_changed_payroll_figure_is_reported_with_before_and_after(self):
		before = [slip("SS-1", payment_days=22)]
		after = [slip("SS-1", payment_days=21)]

		result = diff_payroll_rows(before, after)

		self.assertFalse(result["identical"])
		self.assertEqual(len(result["changed"]), 1)
		change = result["changed"][0]
		self.assertEqual(change["name"], "SS-1")
		self.assertEqual(change["fields"]["payment_days"], {"before": 22, "after": 21})

	def test_only_payroll_relevant_fields_are_compared(self):
		"""gross_pay/net_pay move for many legitimate reasons; the gate is about attendance-driven
		fields, so a pay-rate change must not be reported as a gate failure."""
		before = [slip("SS-1")]
		after = [dict(slip("SS-1"), gross_pay=11_000_000.0, net_pay=9_900_000.0)]

		result = diff_payroll_rows(before, after)

		self.assertTrue(result["identical"], result)

	def test_a_disappeared_slip_is_reported_as_missing(self):
		result = diff_payroll_rows([slip("SS-1"), slip("SS-2")], [slip("SS-1")])

		self.assertFalse(result["identical"])
		self.assertEqual([r["name"] for r in result["missing"]], ["SS-2"])

	def test_a_new_slip_is_reported_as_added(self):
		result = diff_payroll_rows([slip("SS-1")], [slip("SS-1"), slip("SS-2")])

		self.assertFalse(result["identical"])
		self.assertEqual([r["name"] for r in result["added"]], ["SS-2"])


class TestCapturePayrollBaseline(FrappeTestCase):
	def test_capture_writes_a_readable_snapshot_and_reports_its_count(self):
		with tempfile.TemporaryDirectory() as d:
			path = os.path.join(d, "baseline.json")
			result = capture_payroll_baseline(path=path)

			self.assertTrue(os.path.exists(path))
			self.assertEqual(result["path"], path)
			self.assertEqual(result["count"], frappe.db.count("Salary Slip", {"docstatus": 1}))

			with open(path, encoding="utf-8") as f:
				saved = json.load(f)
			self.assertEqual(len(saved["rows"]), result["count"])
			self.assertEqual(saved["checksum"], result["checksum"])

	def test_comparing_a_fresh_snapshot_against_the_db_finds_no_difference(self):
		with tempfile.TemporaryDirectory() as d:
			path = os.path.join(d, "baseline.json")
			capture_payroll_baseline(path=path)

			result = compare_payroll_baseline(path)

			self.assertTrue(result["identical"], result)

	def test_comparing_against_a_tampered_snapshot_detects_the_drift(self):
		"""Proves the gate would actually catch a payroll move rather than always saying OK."""
		with tempfile.TemporaryDirectory() as d:
			path = os.path.join(d, "baseline.json")
			capture_payroll_baseline(path=path)

			with open(path, encoding="utf-8") as f:
				saved = json.load(f)
			saved["rows"].append(slip("SS-DOES-NOT-EXIST"))
			with open(path, "w", encoding="utf-8") as f:
				json.dump(saved, f)

			result = compare_payroll_baseline(path)

			self.assertFalse(result["identical"])
			self.assertEqual([r["name"] for r in result["missing"]], ["SS-DOES-NOT-EXIST"])


class TestClassifierDelta(FrappeTestCase):
	"""T4: does the VN classifier move any payroll-relevant field vs the upstream threshold rule?"""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.employee = frappe.db.get_value("Employee", {"status": "Active"}, "name")
		cls.shift = "VN Gate Split Shift (test)"
		if not frappe.db.exists("Shift Type", cls.shift):
			frappe.get_doc(
				{
					"doctype": "Shift Type",
					"__newname": cls.shift,
					"start_time": "08:00:00",
					"end_time": "17:30:00",
					"enable_auto_attendance": 1,
					"custom_split_half_day": 1,
					"custom_lunch_start": "12:00:00",
					"custom_lunch_end": "13:30:00",
					"custom_half_day_min_fraction": 0.5,
					"custom_half_day_grace_minutes": 15,
					"working_hours_calculation_based_on": "First Check-in and Last Check-out",
					"determine_check_in_and_check_out": "Alternating entries as IN and OUT during the same shift",
				}
			).insert()

	def make_day(self, date, in_hm, out_hm):
		"""One worked day: check-ins + the Attendance the classifier produces from them."""
		attendance = frappe.get_doc(
			{
				"doctype": "Attendance",
				"employee": self.employee,
				"attendance_date": date,
				"shift": self.shift,
				"in_time": f"{date} {in_hm}",
				"out_time": f"{date} {out_hm}",
				"company": frappe.db.get_value("Employee", self.employee, "company"),
			}
		).insert()

		for log_type, t in (("IN", in_hm), ("OUT", out_hm)):
			checkin = frappe.get_doc(
				{
					"doctype": "Employee Checkin",
					"employee": self.employee,
					"time": get_datetime(f"{date} {t}"),
					"log_type": log_type,
					"shift": self.shift,
					"shift_start": get_datetime(f"{date} 08:00:00"),
					"shift_end": get_datetime(f"{date} 17:30:00"),
				}
			).insert()
			# link it the way process_auto_attendance does — setting it at insert time is rejected
			# by Employee Checkin.validate_time_change
			frappe.db.set_value("Employee Checkin", checkin.name, "attendance", attendance.name)
		return attendance

	def test_a_full_day_matches_the_upstream_threshold_rule(self):
		"""08:00-17:30 is Present under both rules → nothing for payroll to notice."""
		self.make_day("2099-04-01", "08:00:00", "17:30:00")

		report = classifier_delta(2099, 4, self.shift)

		self.assertEqual(report["days_examined"], 1)
		self.assertEqual(report["differing"], [])
		self.assertTrue(report["payroll_identical"])

	def test_a_morning_only_day_is_reported_as_a_difference(self):
		"""With no thresholds configured, upstream calls 08:00-12:00 'Present'; the VN classifier
		calls it a Half Day. That is exactly the delta the T4 gate must surface."""
		self.make_day("2099-05-04", "08:00:00", "12:00:00")

		report = classifier_delta(2099, 5, self.shift)

		self.assertEqual(report["days_examined"], 1)
		self.assertFalse(report["payroll_identical"])
		self.assertEqual(len(report["differing"]), 1)

		diff = report["differing"][0]
		self.assertEqual(diff["actual"]["status"], "Half Day")
		self.assertEqual(diff["threshold"]["status"], "Present")

	def test_the_summary_counts_days_per_employee_under_both_rules(self):
		self.make_day("2099-06-01", "08:00:00", "17:30:00")
		self.make_day("2099-06-02", "08:00:00", "12:00:00")

		report = classifier_delta(2099, 6, self.shift)

		summary = report["summary"][self.employee]
		self.assertEqual(summary["actual"]["Present"], 1)
		self.assertEqual(summary["actual"]["Half Day"], 1)
		self.assertEqual(summary["threshold"]["Present"], 2)

	def test_a_month_with_no_attendance_on_the_shift_is_inconclusive_not_clean(self):
		"""Examining nothing is not evidence of no delta — the gate must never read as a pass."""
		report = classifier_delta(2099, 7, self.shift)

		self.assertEqual(report["days_examined"], 0)
		self.assertFalse(report["conclusive"])
		self.assertEqual(report["verdict"], "inconclusive")

	def test_a_month_whose_days_cannot_be_replayed_is_inconclusive(self):
		"""Hand-entered Attendance has no check-ins to replay through the upstream rule, so the gate
		has verified nothing about it. Reporting 'no delta' there would be a false green."""
		frappe.get_doc(
			{
				"doctype": "Attendance",
				"employee": self.employee,
				"attendance_date": "2099-08-03",
				"shift": self.shift,
				"status": "Present",
				"company": frappe.db.get_value("Employee", self.employee, "company"),
			}
		).insert()

		report = classifier_delta(2099, 8, self.shift)

		self.assertEqual(report["days_examined"], 0)
		self.assertEqual(len(report["skipped_no_checkins"]), 1)
		self.assertFalse(report["conclusive"])
		self.assertEqual(report["verdict"], "inconclusive")

	def test_a_replayable_matching_day_is_reported_as_a_conclusive_pass(self):
		self.make_day("2099-09-01", "08:00:00", "17:30:00")

		report = classifier_delta(2099, 9, self.shift)

		self.assertTrue(report["conclusive"])
		self.assertEqual(report["verdict"], "no-delta")
