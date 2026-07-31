# Copyright (c) 2026, Miyano Việt Nam.
"""Đóng gói: cấu hình MVL tự có khi cài/migrate app, và phiếu lương render được."""

import frappe
from frappe.tests.utils import FrappeTestCase, change_settings

from erpnext.setup.doctype.employee.test_employee import make_employee

from hrms import hooks
from hrms.tests.isolation import PerTestRollback
from hrms.tests.vn_test_utils import default_company
from hrms.vn_payroll.setup_mvl import ensure_mvl_defaults
from hrms.vn_payroll.test_salary_slip_mvl import ensure_fiscal_year_2099, make_slip, make_ssa, mark_full_month


class TestMVLPackaging(PerTestRollback, FrappeTestCase):
	def test_ensure_mvl_defaults_wired_to_after_migrate(self):
		self.assertIn("hrms.vn_payroll.setup_mvl.ensure_mvl_defaults", hooks.after_migrate)

	def test_ensure_mvl_defaults_wired_to_after_install(self):
		# cấu hình lương phải CÓ SẴN ngay khi cài app, không chờ migrate đầu
		self.assertIn("hrms.vn_payroll.setup_mvl.ensure_mvl_defaults", hooks.after_install)

	def test_structures_and_components_idempotent_no_duplicates(self):
		# chạy lại (mỗi migrate) KHÔNG nhân đôi row → cấu trúc/component vẫn sửa được, self-heal an toàn
		from hrms.vn_payroll.setup_mvl import STRUCTURES

		ensure_mvl_defaults()
		before = {
			name: (
				len(frappe.get_doc("Salary Structure", name).earnings),
				len(frappe.get_doc("Salary Structure", name).deductions),
			)
			for name in STRUCTURES
		}
		ensure_mvl_defaults()  # lần 2
		for name, (ne, nd) in before.items():
			doc = frappe.get_doc("Salary Structure", name)
			self.assertEqual((len(doc.earnings), len(doc.deductions)), (ne, nd), name)

	def test_accounting_config_packaged(self):
		# cài/migrate phải TỰ dựng cấu hình hạch toán → Payroll Entry ra bút toán ngay, không chạy execute tay
		ensure_mvl_defaults()
		from hrms.vn_payroll.setup_mvl import COMPONENT_ACCOUNT_NUMBERS, STRUCTURE_NAMES

		mirror = "Chi phí thuế & BHXH DN nộp thay"
		self.assertTrue(frappe.db.exists("Salary Component", mirror))  # component gương (= Q+S+R)
		for s in STRUCTURE_NAMES:  # gương có trong mọi cấu trúc → mọi loại lương hạch toán được
			self.assertTrue(
				frappe.db.exists(
					"Salary Detail",
					{"parent": s, "parenttype": "Salary Structure", "salary_component": mirror},
				),
				s,
			)
		# field cư trú (Bán thời gian 10%/20%) tự có khi cài
		self.assertTrue(frappe.db.exists("Custom Field", "Salary Structure Assignment-custom_is_resident"))
		# map Salary Component ↔ TK GL (chỉ kiểm khi CoA của company có TK — Miyano có; CI có thể không)
		company = frappe.defaults.get_defaults().get("company") or frappe.db.get_value("Company", {}, "name")
		for comp, num in COMPONENT_ACCOUNT_NUMBERS.items():
			if frappe.db.exists("Account", {"account_number": num, "company": company, "is_group": 0}):
				self.assertTrue(
					frappe.db.exists("Salary Component Account", {"parent": comp, "company": company}), comp
				)

	def test_payslip_print_format_installed(self):
		ensure_mvl_defaults()
		self.assertTrue(frappe.db.exists("Print Format", "Phiếu lương MVL"))
		self.assertEqual(frappe.db.get_value("Print Format", "Phiếu lương MVL", "doc_type"), "Salary Slip")

	def test_mvl_is_default_print_format(self):
		# nút In của Salary Slip phải mặc định ra phiếu MVL đầy đủ, không phải mẫu chuẩn Frappe
		ensure_mvl_defaults()
		self.assertEqual(
			frappe.db.get_value(
				"Property Setter", {"doc_type": "Salary Slip", "property": "default_print_format"}, "value"
			),
			"Phiếu lương MVL",
		)

	@change_settings("Payroll Settings", {"payroll_based_on": "Attendance"})
	def test_payslip_renders_with_amounts(self):
		ensure_fiscal_year_2099()
		ensure_mvl_defaults()
		emp = make_employee("mvl_print@codes.com", company=default_company())
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
