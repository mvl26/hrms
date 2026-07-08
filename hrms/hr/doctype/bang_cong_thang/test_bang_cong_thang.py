# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase


class TestBangCongThang(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.company = frappe.db.get_value("Company", {}, "name")

	def _sheet(self, month="4", year=2097, department=None):
		return frappe.get_doc(
			{
				"doctype": "Bang Cong Thang",
				"company": self.company,
				"department": department,
				"month": month,
				"year": year,
			}
		)

	def test_validate_derives_period_dates(self):
		d = self._sheet(month="4", year=2097)
		d.insert()
		self.assertEqual(str(d.from_date), "2097-04-01")
		self.assertEqual(str(d.to_date), "2097-04-30")  # April = 30 days

	def test_no_duplicate_sheet_per_unit_month(self):
		self._sheet(month="5", year=2097).insert()
		dup = self._sheet(month="5", year=2097)
		self.assertRaises(frappe.ValidationError, dup.insert)

	def test_different_month_is_allowed(self):
		self._sheet(month="6", year=2097).insert()
		self._sheet(month="7", year=2097).insert()  # different month -> no duplicate
