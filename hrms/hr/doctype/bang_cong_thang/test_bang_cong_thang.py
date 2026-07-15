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

	def test_populate_personal_leave_total(self):
		# code N (nghỉ việc riêng có lương) must land in the personal_leave totals column
		emp = frappe.db.get_value("Employee", {"company": self.company}, "name")
		if not emp:
			self.skipTest("no employee in company")
		Y, M = 2097, 2
		self._seed_attendance(emp, Y, M, 7, custom_attendance_code="N")

		sheet = self._sheet(month=str(M), year=Y)
		sheet.insert()
		sheet.populate_from_attendance()

		row = next((r for r in sheet.employees if r.employee == emp), None)
		self.assertIsNotNone(row, "seeded employee missing from the sheet")
		self.assertEqual(row.d07, "N")
		self.assertEqual(row.personal_leave, 1.0)  # full-day personal leave = 1.0

	def test_populate_blocked_after_submit(self):
		sheet = self._sheet(month="9", year=2097)
		sheet.insert()
		sheet.submit()
		self.assertRaises(frappe.ValidationError, sheet.populate_from_attendance)

	def test_sheet_is_payroll_neutral_never_writes_attendance(self):
		# creating + populating + submitting the sheet must not create or modify ANY Attendance
		emp = frappe.db.get_value("Employee", {"company": self.company}, "name")
		if not emp:
			self.skipTest("no employee in company")
		Y, M = 2097, 10
		self._seed_attendance(emp, Y, M, 3, custom_attendance_code="P")
		att = frappe.db.get_value(
			"Attendance", {"employee": emp, "attendance_date": f"{Y}-{M:02d}-03"},
			["name", "status", "leave_type", "half_day_status"], as_dict=True,
		)
		before_count = frappe.db.count("Attendance")

		sheet = self._sheet(month=str(M), year=Y)
		sheet.insert()
		sheet.populate_from_attendance()
		sheet.save()
		sheet.submit()

		self.assertEqual(frappe.db.count("Attendance"), before_count)  # no new Attendance rows
		after = frappe.db.get_value(
			"Attendance", att.name, ["status", "leave_type", "half_day_status"], as_dict=True
		)
		# payroll-relevant fields on the existing Attendance are byte-identical
		self.assertEqual(after.status, att.status)
		self.assertEqual(after.leave_type, att.leave_type)
		self.assertEqual(after.half_day_status, att.half_day_status)

	def test_submit_and_cancel_lifecycle(self):
		sheet = self._sheet(month="11", year=2097)
		sheet.insert()
		sheet.submit()
		self.assertEqual(sheet.docstatus, 1)
		sheet.cancel()
		self.assertEqual(sheet.docstatus, 2)

	def test_print_format_renders(self):
		emp = frappe.db.get_value("Employee", {"company": self.company}, "name")
		if not emp:
			self.skipTest("no employee in company")
		Y, M = 2097, 12
		self._seed_attendance(emp, Y, M, 2, custom_attendance_code="X")
		sheet = self._sheet(month=str(M), year=Y)
		sheet.insert()
		sheet.populate_from_attendance()
		sheet.save()

		html = frappe.get_print("Bang Cong Thang", sheet.name, print_format="Bang Cong Thang")
		self.assertIn("BẢNG CHẤM CÔNG THÁNG", html)
		self.assertIn("NGƯỜI CHẤM CÔNG", html)  # sign box 1
		self.assertIn("PHÒNG NHÂN SỰ", html)  # sign box 2
		self.assertIn("Chú thích", html)  # symbol legend
