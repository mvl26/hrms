# Copyright (c) 2026, Miyano Việt Nam.
import frappe
from frappe.tests.utils import FrappeTestCase

from hrms.setup_vn_defaults import check_fixture_master_data, ensure_defaults
from hrms.tests.isolation import PerTestRollback


class TestSetupVnDefaults(PerTestRollback, FrappeTestCase):
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

	def test_hooks_fixture_filters_match_fixture_files(self):
		# A fixtures `name in [...]` filter must list exactly the records in its JSON file, else a
		# `bench export-fixtures` would silently drop the records missing from the filter.
		import hrms.hooks as hooks
		from hrms.setup_vn_defaults import _fixture_names

		for entry in hooks.fixtures:
			if not isinstance(entry, dict):
				continue
			name_filter = (entry.get("filters") or {}).get("name")
			if not (isinstance(name_filter, list | tuple) and name_filter and name_filter[0] == "in"):
				continue
			filtered = set(name_filter[1])
			file_names = set(_fixture_names(frappe.scrub(entry["dt"])))
			self.assertEqual(
				filtered,
				file_names,
				f"hooks.py fixtures filter for {entry['dt']} is out of sync with its fixture file",
			)
