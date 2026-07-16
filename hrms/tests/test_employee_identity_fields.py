# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# See license.txt
"""Tests for the VN identity custom fields on Employee (spec/employee-vn-identity-fields.md).
Fixture-level only: creating Custom Fields at runtime would trigger DDL (implicit commit)
and break the rollback harness — applying to the site is the `bench migrate` deploy step."""

import json
import os

import frappe
from frappe.tests.utils import FrappeTestCase

FIXTURE_PATH = os.path.join(os.path.dirname(__file__), "..", "fixtures", "custom_field.json")

CCCD = "Employee-custom_citizen_id"
BHXH = "Employee-custom_social_insurance_no"


def load_fixture_fields():
	with open(FIXTURE_PATH) as f:
		return {row["name"]: row for row in json.load(f)}


class TestEmployeeIdentityFixtures(FrappeTestCase):
	def test_fixture_json_has_identity_fields(self):
		rows = load_fixture_fields()

		cccd = rows[CCCD]
		self.assertEqual(cccd["dt"], "Employee")
		self.assertEqual(cccd["fieldtype"], "Data")
		self.assertEqual(cccd["label"], "Số CCCD")
		self.assertEqual(cccd["insert_after"], "marital_status")
		self.assertEqual(cccd["unique"], 0)
		self.assertEqual(cccd["reqd"], 0)

		bhxh = rows[BHXH]
		self.assertEqual(bhxh["dt"], "Employee")
		self.assertEqual(bhxh["fieldtype"], "Data")
		self.assertEqual(bhxh["label"], "Số sổ BHXH")
		self.assertEqual(bhxh["insert_after"], "custom_citizen_id")

	def test_hooks_filter_includes_identity_fields(self):
		import hrms.hooks as hooks

		for entry in hooks.fixtures:
			if isinstance(entry, dict) and entry.get("dt") == "Custom Field":
				names = set(entry["filters"]["name"][1])
				self.assertIn(CCCD, names)
				self.assertIn(BHXH, names)
				return
		self.fail("no Custom Field fixtures entry in hooks.py")

	def test_insert_anchor_exists_on_employee(self):
		# marital_status phải tồn tại trên Employee để insert_after có hiệu lực
		self.assertTrue(frappe.get_meta("Employee").has_field("marital_status"))

	def test_tax_id_translated_to_mst(self):
		# "Tax ID" là source string dùng chung (Company/Customer/Supplier) -> dịch trung tính
		# "Mã số thuế", không phải "MST cá nhân" (sẽ lan sang form doanh nghiệp)
		path = os.path.join(os.path.dirname(__file__), "..", "translations", "vi.csv")
		with open(path, encoding="utf-8") as f:
			content = f.read()
		self.assertIn("Tax ID,Mã số thuế", content)
