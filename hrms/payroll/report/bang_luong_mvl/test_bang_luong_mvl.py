# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# See license.txt
"""Test báo cáo Bảng Lương MVL — gom Salary Slip đã submit thành bảng lương đủ cột + dòng tổng."""

import frappe
from frappe.tests.utils import FrappeTestCase, change_settings

from erpnext.setup.doctype.employee.test_employee import make_employee
from hrms.payroll.report.bang_luong_mvl.bang_luong_mvl import execute
from hrms.vn_payroll.setup_mvl import ensure_mvl_defaults
from hrms.vn_payroll.test_salary_slip_mvl import ensure_fiscal_year_2099, make_slip, make_ssa, mark_full_month


class TestBangLuongMVL(FrappeTestCase):
	@change_settings("Payroll Settings", {"payroll_based_on": "Attendance"})
	def test_report_rows_and_total(self):
		ensure_fiscal_year_2099()
		ensure_mvl_defaults()
		emp = make_employee("blmvl@codes.com", company="Miyano")
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

		columns, data = execute(frappe._dict({"company": "Miyano", "month": 6, "year": 2099}))
		labels = {c["label"] for c in columns}
		# đủ các cột chính của bảng lương
		for lbl in (
			"Lương theo công (I)",
			"Thuế TNCN (Q)",
			"BHXH Cty (R)",
			"THỰC LĨNH (T)",
			"Chi phí công ty",
		):
			self.assertIn(lbl, labels, lbl)

		row = next(r for r in data if r.get("employee") == emp)
		self.assertEqual(row["work_i"], 25_000_000)  # I đi làm đủ
		self.assertEqual(row["tax_q"], 173_684)  # Q
		self.assertEqual(row["ins_company_r"], 5_375_000)  # R
		self.assertEqual(row["net_t"], ss.net_pay)  # T
		# chi phí công ty = T + Q + S + R
		self.assertEqual(row["company_cost"], ss.net_pay + 173_684 + 2_625_000 + 5_375_000)

		total = data[-1]
		self.assertEqual(total["employee_name"], "TỔNG CỘNG")
		self.assertGreaterEqual(total["net_t"], row["net_t"])

	def test_empty_when_no_period(self):
		self.assertEqual(execute(frappe._dict({"company": "Miyano"}))[1], [])
