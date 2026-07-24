# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase

from hrms.vn_payroll.setup_mvl import STRUCTURE, ensure_mvl_defaults


class TestSetupMVL(FrappeTestCase):
	def test_creates_components_structure_and_custom_fields(self):
		ensure_mvl_defaults()
		for c in ("Lương theo công", "Phụ cấp ăn trưa", "Thuế TNCN (nộp thay)", "BHXH - NLĐ (nộp thay)"):
			self.assertTrue(frappe.db.exists("Salary Component", c), c)
		self.assertTrue(frappe.db.exists("Salary Structure", STRUCTURE))
		self.assertTrue(frappe.db.exists("Custom Field", "Salary Structure Assignment-custom_salary_type"))
		# phiếu lương phải có đủ mọi thành phần F..U của bảng lương
		for fn in (
			"custom_base_salary",
			"custom_coefficient",
			"custom_gross_income",
			"custom_total_deduction",
			"custom_converted_income",
			"custom_taxable_income_gross",
			"custom_taxable_income",
			"custom_ins_company",
		):
			self.assertTrue(frappe.db.exists("Custom Field", f"Salary Slip-{fn}"), fn)

	def test_lunch_component_is_tax_exempt(self):
		ensure_mvl_defaults()
		self.assertEqual(frappe.db.get_value("Salary Component", "Phụ cấp ăn trưa", "is_tax_applicable"), 0)

	def test_tax_and_insurance_do_not_reduce_net(self):
		ensure_mvl_defaults()
		for c in ("Thuế TNCN (nộp thay)", "BHXH - NLĐ (nộp thay)"):
			self.assertEqual(frappe.db.get_value("Salary Component", c, "do_not_include_in_total"), 1, c)

	def test_idempotent_and_non_destructive(self):
		ensure_mvl_defaults()
		frappe.db.set_single_value("MVL Payroll Settings", "lunch_rate_per_day", 40_000)
		ensure_mvl_defaults()  # chạy lại không được ghi đè giá trị đã sửa
		self.assertEqual(frappe.db.get_single_value("MVL Payroll Settings", "lunch_rate_per_day"), 40_000)
		# không nhân đôi bậc thuế
		s = frappe.get_single("MVL Payroll Settings")
		self.assertEqual(len(s.tax_brackets), 5)
