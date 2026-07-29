# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# See license.txt
"""Test báo cáo Bảng Lương MVL — gom Salary Slip đã submit thành bảng lương đủ cột + dòng tổng."""

import frappe
from frappe.tests.utils import FrappeTestCase, change_settings

from erpnext.setup.doctype.employee.test_employee import make_employee

from hrms.payroll.report.bang_luong_mvl.bang_luong_mvl import execute
from hrms.tests.isolation import PerTestRollback
from hrms.tests.vn_test_utils import default_company
from hrms.vn_payroll.setup_mvl import ensure_mvl_defaults
from hrms.vn_payroll.test_salary_slip_mvl import ensure_fiscal_year_2099, make_slip, make_ssa, mark_full_month


class TestBangLuongMVL(PerTestRollback, FrappeTestCase):
	@change_settings("Payroll Settings", {"payroll_based_on": "Attendance"})
	def test_report_rows_and_total(self):
		ensure_fiscal_year_2099()
		ensure_mvl_defaults()
		emp = make_employee("blmvl@codes.com", company=default_company())
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

		columns, data = execute(frappe._dict({"company": default_company(), "month": 6, "year": 2099}))
		labels = [c["label"] for c in columns]
		# CỘT GIỐNG HỆT Excel, đúng thứ tự: Mã NV, Họ tên, Loại, NET/GROSS, E, F, G, H, I ... T, U
		expected = [
			"Mã NV",
			"Họ tên",
			"Loại",
			"NET/GROSS",
			"Hệ số (E)",
			"Lương ngày công (F)",
			"Lương đóng BHXH (G)",
			"Số công (H)",
			"Lương thực tế (I)",
			"Phụ cấp ăn trưa (J)",
			"Tổng thu nhập (K)",
			"Giảm trừ bản thân (L)",
			"Số người phụ thuộc (M)",
			"Tổng giảm trừ (N)",
			"Thu nhập quy đổi (O)",
			"Thu nhập tính thuế (P)",
			"Thuế TNCN (Q)",
			"BH công ty (R)",
			"BH NLĐ (S)",
			"Thực lĩnh (T)",
			"TN chịu thuế kê khai (U)",
		]
		self.assertEqual(labels, expected)
		# KHÔNG còn cột thừa của ERP
		for gone in ("Công chuẩn", "Chi phí công ty"):
			self.assertNotIn(gone, labels)

		row = next(r for r in data if r.get("employee") == emp)
		self.assertEqual(row["work_type"], "Toàn thời gian")
		self.assertEqual(row["pay_mode"], "NET")
		self.assertEqual(row["work_i"], 25_000_000)  # I đi làm đủ
		self.assertEqual(row["tax_q"], 173_684)  # Q
		self.assertEqual(row["ins_company_r"], 5_375_000)  # R
		self.assertEqual(row["net_t"], ss.net_pay)  # T

		total = data[-1]
		self.assertEqual(total["employee_name"], "TỔNG CỘNG")
		self.assertGreaterEqual(total["net_t"], row["net_t"])

	def test_empty_when_no_period(self):
		self.assertEqual(execute(frappe._dict({"company": default_company()}))[1], [])
