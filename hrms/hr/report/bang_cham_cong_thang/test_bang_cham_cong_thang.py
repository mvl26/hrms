# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import getdate

from hrms.hr.report.bang_cham_cong_thang.bang_cham_cong_thang import execute


class TestBangChamCongThang(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.emp = frappe.db.get_value("Employee", {}, "name")
		cls.year, cls.month = 2099, 3  # far future to avoid colliding with any real/test data

	def _mk(self, day, **codes):
		att = frappe.get_doc(
			{
				"doctype": "Attendance",
				"employee": self.emp,
				"attendance_date": getdate(f"{self.year}-{self.month:02d}-{day:02d}"),
				**codes,
			}
		)
		att.insert()  # draft; bridge fills native fields + display code
		return att

	def test_pivot_cells_and_category_totals(self):
		self._mk(5, custom_attendance_code="X")  # full work
		self._mk(6, custom_attendance_code="P")  # full annual leave
		self._mk(7, custom_morning_code="X", custom_afternoon_code="P")  # half work / half leave

		columns, data = execute({"month": self.month, "year": self.year})

		# category column order comes from get_categories: Công=cat_0, Phép=cat_1
		labels = {c["fieldname"]: c["label"] for c in columns}
		self.assertEqual(labels["cat_0"], "Công")
		self.assertEqual(labels["cat_1"], "Phép")

		row = next(r for r in data if r["employee"] == self.emp)
		self.assertEqual(row["day_5"], "X")
		self.assertEqual(row["day_6"], "P")
		self.assertEqual(row["day_7"], "X/P")
		# Công = X(1.0) + half X(0.5) = 1.5 ; Phép = P(1.0) + half P(0.5) = 1.5
		self.assertEqual(row["cat_0"], 1.5)
		self.assertEqual(row["cat_1"], 1.5)
