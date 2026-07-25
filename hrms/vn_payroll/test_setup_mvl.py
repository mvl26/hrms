# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase

from hrms.vn_payroll.setup_mvl import (
	COMPONENTS,
	DEDUCTIONS,
	EARNINGS,
	SALARY_TYPES,
	STRUCTURE,
	ensure_mvl_defaults,
)


class TestSetupMVL(FrappeTestCase):
	def test_gross_not_offered_until_implemented(self):
		# GROSS chưa hiện thực → không được cho HR chọn (tránh ra phiếu sai âm thầm)
		self.assertNotIn("GROSS", SALARY_TYPES.split("\n"))
		self.assertIn("Chính thức", SALARY_TYPES.split("\n"))

	def test_every_money_column_is_a_component_in_the_structure(self):
		ensure_mvl_defaults()
		# mọi cột tiền của bảng lương là 1 Salary Component
		for name, *_ in COMPONENTS:
			self.assertTrue(frappe.db.exists("Salary Component", name), name)
		# và đều nằm trong cấu trúc "MVL Việt Nam" đúng bảng earnings/deductions
		doc = frappe.get_doc("Salary Structure", STRUCTURE)
		self.assertEqual({r.salary_component for r in doc.earnings}, set(EARNINGS))
		self.assertEqual({r.salary_component for r in doc.deductions}, set(DEDUCTIONS))

	def test_only_nonmoney_params_are_slip_fields(self):
		ensure_mvl_defaults()
		self.assertTrue(frappe.db.exists("Custom Field", "Salary Slip-custom_coefficient"))  # E
		self.assertTrue(frappe.db.exists("Custom Field", "Salary Slip-custom_dependents_slip"))  # M
		# các cột tiền cũ KHÔNG còn là field (đã thành component)
		for fn in ("custom_base_salary", "custom_gross_income", "custom_ins_company"):
			self.assertFalse(frappe.db.exists("Custom Field", f"Salary Slip-{fn}"), fn)

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
