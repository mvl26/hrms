# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# See license.txt
"""Tích hợp: Salary Slip dùng structure MVL → engine gán component + net_pay đúng.

Tự dựng NV + SSA + chấm công đủ tháng, chạy qua harness rollback. Tháng 6/2099 không có Holiday List
phủ → total_working_days = 30; chấm đủ 30 ngày Present → payment_days = 30 → I = base (đi làm đủ công).
"""

import frappe
from frappe.tests.utils import FrappeTestCase, change_settings

from erpnext.setup.doctype.employee.test_employee import make_employee

from hrms.tests.isolation import PerTestRollback
from hrms.tests.vn_test_utils import default_company
from hrms.vn_payroll.setup_mvl import ensure_mvl_defaults, structure_for_type


def ensure_fiscal_year_2099():
	# Salary Slip.compute_year_to_date cần Fiscal Year phủ kỳ; 2099 chưa có trên site.
	if not frappe.db.exists("Fiscal Year", "2099"):
		frappe.get_doc(
			{
				"doctype": "Fiscal Year",
				"year": "2099",
				"year_start_date": "2099-01-01",
				"year_end_date": "2099-12-31",
			}
		).insert(ignore_permissions=True)


def make_ssa(employee, **kw):
	# mỗi loại lương một cấu trúc → cấu trúc suy từ custom_salary_type (mặc định Chính thức)
	doc = frappe.get_doc(
		{
			"doctype": "Salary Structure Assignment",
			"employee": employee,
			"company": default_company(),
			"salary_structure": structure_for_type(kw.get("custom_salary_type", "Chính thức")),
			"from_date": "2099-06-01",
			**kw,
		}
	)
	doc.submit()
	return doc


def mark_full_month(employee):
	for d in range(1, 31):
		# checkin phủ cả buổi → ngày ăn trưa (số ngày ăn suy từ checkin, không phải số công).
		# Phải tạo TRƯỚC Attendance: cờ custom_lunch được chốt trong validate của Attendance từ
		# checkin của chính ngày đó (attendance.py: set_lunch_flag), tạo checkin sau thì cờ đã
		# bằng 0 và phụ cấp ăn trưa trên phiếu lương ra 0. Ngoài đời checkin cũng có trước.
		for hm in ("08:00:00", "17:30:00"):
			frappe.get_doc(
				{"doctype": "Employee Checkin", "employee": employee, "time": f"2099-06-{d:02d} {hm}"}
			).insert()
		att = frappe.get_doc(
			{
				"doctype": "Attendance",
				"employee": employee,
				"attendance_date": f"2099-06-{d:02d}",
				"custom_attendance_code": "X",
			}
		)
		att.insert()
		att.submit()


def make_slip(employee, salary_type="Chính thức"):
	ss = frappe.new_doc("Salary Slip")
	ss.employee = employee
	ss.salary_structure = structure_for_type(salary_type)
	ss.start_date = "2099-06-01"
	ss.end_date = "2099-06-30"
	ss.insert()  # validate → apply_mvl
	return ss


class TestSalarySlipMVL(PerTestRollback, FrappeTestCase):
	@change_settings("Payroll Settings", {"payroll_based_on": "Attendance"})
	def test_chinh_thuc_full_month(self):
		ensure_fiscal_year_2099()
		ensure_mvl_defaults()
		emp = make_employee("mvl_ft@codes.com", company=default_company())
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

		comp = {r.salary_component: r.amount for r in list(ss.earnings) + list(ss.deductions)}
		self.assertEqual(comp["Lương theo công"], 25_000_000)  # đi làm đủ 30/30 → I = base
		self.assertEqual(comp["Phụ cấp ăn trưa"], ss.payment_days * 35_000)
		# O = K - 21.7tr - J = 25tr - 21.7tr = 3.3tr (J triệt tiêu) → Q = 173.684 bất kể J
		self.assertEqual(comp["Thuế TNCN (nộp thay)"], 173_684)
		self.assertEqual(comp["BHXH - NLĐ (nộp thay)"], 2_625_000)  # 25tr x 10.5%
		self.assertEqual(comp["BHXH - Công ty"], 5_375_000)  # R = 25tr x 21.5%
		# gương chi phí (hạch toán) = Q + S + R → Nợ 6421 của bút toán accrual; KHÔNG cộng net
		self.assertEqual(comp["Chi phí thuế & BHXH DN nộp thay"], 173_684 + 2_625_000 + 5_375_000)
		# NET: thuế + BHXH + gương KHÔNG trừ/cộng vào net → net = K = I + J
		self.assertEqual(ss.net_pay, 25_000_000 + ss.payment_days * 35_000)
		# mọi cột tiền là Salary Component trong lưới (không phải field): F, G, K, N, O, R, U…
		self.assertEqual(comp["Lương ngày công"], 25_000_000)  # F
		self.assertEqual(comp["Lương đóng BHXH"], 25_000_000)  # G
		self.assertEqual(comp["Tổng thu nhập"], ss.net_pay)  # K = T (NET)
		self.assertEqual(comp["Tổng giảm trừ gia cảnh"], 21_700_000)  # N
		self.assertEqual(comp["Thu nhập quy đổi"], 3_300_000)  # O
		self.assertEqual(comp["Thu nhập chịu thuế kê khai"], 25_000_000 + 173_684 + 2_625_000)  # U = 25tr+Q+S
		# các cột do_not_include KHÔNG làm sai net
		self.assertEqual(ss.gross_pay, ss.net_pay)

	@change_settings("Payroll Settings", {"payroll_based_on": "Attendance"})
	def test_net_tracks_payment_days(self):
		# nghỉ không lương vài ngày → I giảm theo payment_days, net theo I
		ensure_fiscal_year_2099()
		ensure_mvl_defaults()
		emp = make_employee("mvl_lwp@codes.com", company=default_company())
		make_ssa(emp, base=22_000_000, custom_salary_type="Chính thức")
		for d in range(1, 31):
			code = "K" if d <= 3 else "X"  # 3 ngày nghỉ không lương
			att = frappe.get_doc(
				{
					"doctype": "Attendance",
					"employee": emp,
					"attendance_date": f"2099-06-{d:02d}",
					"custom_attendance_code": code,
				}
			)
			att.insert()
			att.submit()
		ss = make_slip(emp)

		comp = {r.salary_component: r.amount for r in ss.earnings}
		# I = ROUND(22tr / 30 x 27) = 19.800.000
		self.assertEqual(ss.payment_days, 27)
		self.assertEqual(comp["Lương theo công"], 19_800_000)

	@change_settings("Payroll Settings", {"payroll_based_on": "Attendance"})
	def test_probation_to_official_mid_month_blends_salary(self):
		# NV hết thử việc ngày 16 (Ngày chính thức = 2099-06-16) → hệ số blend theo công mỗi giai đoạn.
		# NV giữ MỘT cấu trúc chính thức từ đầu kỳ (thoả ERPNext); phần thử việc suy từ ngày chính thức.
		ensure_fiscal_year_2099()
		ensure_mvl_defaults()
		emp = make_employee("mvl_prob@codes.com", company=default_company())
		frappe.db.set_value("Employee", emp, "final_confirmation_date", "2099-06-16")
		make_ssa(emp, base=18_000_000, custom_salary_type="Chính thức")  # from 2099-06-01
		mark_full_month(emp)  # chấm đủ 30 ngày Present (không Holiday List → 30 công)
		ss = make_slip(emp, salary_type="Chính thức")
		comp = {r.salary_component: r.amount for r in ss.earnings}
		# I blend = 18tr/30 x (0.85x15 công thử việc + 1.0x15 công chính thức) = 16.650.000
		# KHÔNG phải 18tr (toàn chính thức) và KHÔNG phải 15.3tr (toàn thử việc)
		self.assertEqual(comp["Lương theo công"], 16_650_000)
		# hệ số E hiện trên phiếu là blend có trọng số: (0.85x15 + 1.0x15)/30 = 0.925
		self.assertEqual(ss.custom_coefficient, 0.925)

	@change_settings("Payroll Settings", {"payroll_based_on": "Attendance"})
	def test_bonus_and_lunch_days_on_slip(self):
		ensure_fiscal_year_2099()
		ensure_mvl_defaults()
		emp = make_employee("mvl_bonus@codes.com", company=default_company())
		make_ssa(
			emp,
			base=25_000_000,
			custom_salary_type="Chính thức",
			custom_bhxh_salary=25_000_000,
			custom_register_personal_deduction=1,
		)
		mark_full_month(emp)  # checkin 08:00-17:30 mỗi ngày → phủ trưa
		ss = make_slip(emp)
		base_net = ss.net_pay
		# dữ liệu ăn trưa hiện trên phiếu (checkin phủ trưa mỗi ngày công)
		self.assertEqual(ss.custom_lunch_days, ss.payment_days)

		# HR điền Tiền thưởng → engine đọc, không ghi đè
		for row in ss.earnings:
			if row.salary_component == "Tiền thưởng":
				row.amount = 5_000_000
		ss.save()
		comp = {r.salary_component: r.amount for r in ss.earnings + ss.deductions}
		self.assertEqual(comp["Tiền thưởng"], 5_000_000)  # giữ nguyên số HR nhập
		self.assertEqual(ss.net_pay, base_net + 5_000_000)  # thưởng cộng vào thực lĩnh
		self.assertEqual(comp["Tổng thu nhập"], base_net + 5_000_000)  # K gồm thưởng
		self.assertGreater(comp["Thuế TNCN (nộp thay)"], 0)  # thưởng chịu thuế
