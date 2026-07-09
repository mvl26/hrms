# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase

from hrms.setup_vn_defaults import check_fixture_master_data, ensure_defaults


class TestSetupVnDefaults(FrappeTestCase):
	def test_ensure_defaults_creates_workflow_and_role(self):
		# Remove the workflow so ensure_defaults() has to recreate it (self-healing path)
		frappe.db.delete("Workflow", {"name": "Cong Tac Approval"})
		self.assertFalse(frappe.db.exists("Workflow", "Cong Tac Approval"))

		summary = ensure_defaults()
		self.assertTrue(frappe.db.exists("Workflow", "Cong Tac Approval"))
		self.assertTrue(frappe.db.exists("Role", "COO"))
		self.assertTrue(summary["workflow"])
		self.assertTrue(summary["coo_role"])

	def test_ensure_defaults_is_idempotent(self):
		ensure_defaults()
		ensure_defaults()  # must not raise or duplicate
		self.assertEqual(frappe.db.count("Workflow", {"name": "Cong Tac Approval"}), 1)
		self.assertEqual(frappe.db.count("Role", {"name": "COO"}), 1)

	def test_fixture_master_data_present(self):
		# All fork fixtures are synced on this site → nothing missing
		self.assertEqual(check_fixture_master_data(), {})

	def test_ensure_defaults_is_payroll_neutral(self):
		before = {dt: frappe.db.count(dt) for dt in ("Attendance", "Salary Slip", "Employee Checkin")}
		ensure_defaults()
		after = {dt: frappe.db.count(dt) for dt in ("Attendance", "Salary Slip", "Employee Checkin")}
		self.assertEqual(before, after)
