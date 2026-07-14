# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# See license.txt
"""Tests for the on-demand VN Holiday List generator (weekly-off + solar public holidays;
Tết/Giỗ Tổ are entered manually). Runs via the rollback harness — writes are rolled back."""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import getdate

import erpnext

from hrms.setup_vn_holiday import SOLAR_HOLIDAYS, create_vn_holiday_list


class TestSetupVNHoliday(FrappeTestCase):
	def setUp(self):
		self.company = erpnext.get_default_company() or frappe.get_all("Company", limit=1)[0].name
		self.year = 2027

	def _dates(self, name):
		return {
			getdate(r.holiday_date): r.weekly_off
			for r in frappe.get_all(
				"Holiday",
				filters={"parent": name, "parenttype": "Holiday List"},
				fields=["holiday_date", "weekly_off"],
			)
		}

	def test_creates_weekly_off_and_solar_holidays(self):
		name = create_vn_holiday_list(self.year, self.company, weekly_off_days=("Sunday",))
		dates = self._dates(name)
		# every Sunday of 2027 is a weekly_off row (~52)
		sundays = [d for d, wo in dates.items() if wo]
		self.assertGreaterEqual(len(sundays), 52)
		self.assertTrue(all(d.weekday() == 6 for d in sundays))  # 6 = Sunday
		# the fixed solar public holidays are present, weekly_off = 0
		for mm, dd in SOLAR_HOLIDAYS:
			key = getdate(f"{self.year}-{mm:02d}-{dd:02d}")
			self.assertIn(key, dates)
			self.assertEqual(dates[key], 0)

	def test_idempotent(self):
		name1 = create_vn_holiday_list(self.year, self.company, weekly_off_days=("Sunday",))
		n1 = len(self._dates(name1))
		name2 = create_vn_holiday_list(self.year, self.company, weekly_off_days=("Sunday",))
		self.assertEqual(name1, name2)
		self.assertEqual(len(self._dates(name2)), n1)  # no duplicate rows

	def test_two_weekly_off_days(self):
		name = create_vn_holiday_list(self.year, self.company, weekly_off_days=("Saturday", "Sunday"))
		wo = [d for d, w in self._dates(name).items() if w]
		self.assertTrue(any(d.weekday() == 5 for d in wo))  # Saturday present
		self.assertTrue(any(d.weekday() == 6 for d in wo))  # Sunday present

	def test_report_resolves_company_default_list(self):
		# an employee WITHOUT an explicit holiday_list must resolve the company default,
		# so the bảng công report can mark '-' on that employee's rest days.
		from erpnext.setup.doctype.employee.employee import get_holiday_list_for_employee

		name = create_vn_holiday_list(self.year, self.company, weekly_off_days=("Sunday",))
		frappe.db.set_value("Company", self.company, "default_holiday_list", name)
		emp = frappe.get_all("Employee", filters={"company": self.company}, limit=1)
		if not emp:
			self.skipTest("no employee for the default company")
		frappe.db.set_value("Employee", emp[0].name, "holiday_list", None)
		self.assertEqual(get_holiday_list_for_employee(emp[0].name, raise_exception=False), name)
