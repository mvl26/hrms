# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# See license.txt
"""Đóng gói: cấu hình MVL tự có khi cài/migrate app, và phiếu lương render được."""

import frappe
from frappe.tests.utils import FrappeTestCase, change_settings

from erpnext.setup.doctype.employee.test_employee import make_employee
from hrms import hooks
from hrms.vn_payroll.setup_mvl import STRUCTURE, ensure_mvl_defaults
from hrms.vn_payroll.test_salary_slip_mvl import ensure_fiscal_year_2099, make_slip, make_ssa, mark_full_month


class TestMVLPackaging(FrappeTestCase):
	def test_ensure_mvl_defaults_wired_to_after_migrate(self):
		self.assertIn("hrms.vn_payroll.setup_mvl.ensure_mvl_defaults", hooks.after_migrate)

	def test_payslip_print_format_installed(self):
		ensure_mvl_defaults()
		self.assertTrue(frappe.db.exists("Print Format", "Phiếu lương MVL"))
		self.assertEqual(frappe.db.get_value("Print Format", "Phiếu lương MVL", "doc_type"), "Salary Slip")

	@change_settings("Payroll Settings", {"payroll_based_on": "Attendance"})
	def test_payslip_renders_with_amounts(self):
		ensure_fiscal_year_2099()
		ensure_mvl_defaults()
		emp = make_employee("mvl_print@codes.com", company="Miyano")
		make_ssa(
			emp,
			base=25_000_000,
			custom_salary_type="Chính thức",
			custom_bhxh_salary=25_000_000,
			custom_dependents=1,
			custom_register_personal_deduction=1,
		)
		mark_full_month(emp)
		ss = make_slip(emp)
		ss.submit()

		html = frappe.get_print("Salary Slip", ss.name, print_format="Phiếu lương MVL")
		# phiếu phải in đủ mọi thành phần bảng lương F..U
		for label in (
			"PHIẾU LƯƠNG",
			"Lương ngày công (F)",
			"Tổng thu nhập (K)",
			"Tổng giảm trừ (N)",
			"Thu nhập tính thuế (P)",
			"THỰC LĨNH (T)",
			"kê khai (U)",
		):
			self.assertIn(label, html, label)
