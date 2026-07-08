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

	def _seed_attendance(self, emp, year, month, day, **codes):
		frappe.get_doc(
			{
				"doctype": "Attendance",
				"employee": emp,
				"company": self.company,
				"attendance_date": f"{year}-{month:02d}-{day:02d}",
				**codes,
			}
		).insert()

	def test_populate_snapshots_attendance(self):
		emp = frappe.db.get_value("Employee", {"company": self.company}, "name")
		if not emp:
			self.skipTest("no employee in company")
		Y, M = 2097, 8
		self._seed_attendance(emp, Y, M, 4, custom_attendance_code="X")
		self._seed_attendance(emp, Y, M, 5, custom_attendance_code="P")
		self._seed_attendance(emp, Y, M, 6, custom_attendance_code="1/2P")

		sheet = self._sheet(month=str(M), year=Y)
		sheet.insert()
		n = sheet.populate_from_attendance()
		self.assertGreaterEqual(n, 1)

		row = next((r for r in sheet.employees if r.employee == emp), None)
		self.assertIsNotNone(row, "seeded employee missing from the sheet")
		self.assertEqual(row.d04, "X")
		self.assertEqual(row.d05, "P")
		self.assertEqual(row.d06, "1/2P")
		# Công = X 1.0 + 1/2P 0.5 = 1.5 ; Phép = P 1.0 + 1/2P 0.5 = 1.5
		self.assertEqual(row.cong, 1.5)
		self.assertEqual(row.phep, 1.5)

	def test_populate_blocked_after_submit(self):
		sheet = self._sheet(month="9", year=2097)
		sheet.insert()
		sheet.submit()
		self.assertRaises(frappe.ValidationError, sheet.populate_from_attendance)
