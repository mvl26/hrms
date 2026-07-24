# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# See license.txt
"""Tích hợp: Salary Slip dùng structure MVL → engine gán component + net_pay đúng.

Tự dựng NV + SSA + chấm công đủ tháng, chạy qua harness rollback. Tháng 6/2099 không có Holiday List
phủ → total_working_days = 30; chấm đủ 30 ngày Present → payment_days = 30 → I = base (đi làm đủ công).
"""

import frappe
from frappe.tests.utils import FrappeTestCase, change_settings

from erpnext.setup.doctype.employee.test_employee import make_employee
from hrms.vn_payroll.setup_mvl import STRUCTURE, ensure_mvl_defaults


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
	doc = frappe.get_doc(
		{
			"doctype": "Salary Structure Assignment",
			"employee": employee,
			"company": "Miyano",
			"salary_structure": STRUCTURE,
			"from_date": "2099-06-01",
			**kw,
		}
	)
	doc.submit()
	return doc


def mark_full_month(employee):
	for d in range(1, 31):
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
		# checkin phủ cả buổi → ngày ăn trưa (số ngày ăn suy từ checkin, không phải số công)
		for hm in ("08:00:00", "17:30:00"):
			frappe.get_doc(
				{"doctype": "Employee Checkin", "employee": employee, "time": f"2099-06-{d:02d} {hm}"}
			).insert()


def make_slip(employee):
	ss = frappe.new_doc("Salary Slip")
	ss.employee = employee
	ss.salary_structure = STRUCTURE
	ss.start_date = "2099-06-01"
	ss.end_date = "2099-06-30"
	ss.insert()  # validate → apply_mvl
	return ss


class TestSalarySlipMVL(FrappeTestCase):
	@change_settings("Payroll Settings", {"payroll_based_on": "Attendance"})
	def test_chinh_thuc_full_month(self):
		ensure_fiscal_year_2099()
		ensure_mvl_defaults()
		emp = make_employee("mvl_ft@codes.com", company="Miyano")
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
		# O = K − 21.7tr − J = 25tr − 21.7tr = 3.3tr (J triệt tiêu) → Q = 173.684 bất kể J
		self.assertEqual(comp["Thuế TNCN (nộp thay)"], 173_684)
		self.assertEqual(comp["BHXH - NLĐ (nộp thay)"], 2_625_000)  # 25tr × 10.5%
		self.assertEqual(ss.custom_ins_company, 5_375_000)  # 25tr × 21.5%
		# NET: thuế + BHXH KHÔNG trừ vào net → net = K = I + J
		self.assertEqual(ss.net_pay, 25_000_000 + ss.payment_days * 35_000)

	@change_settings("Payroll Settings", {"payroll_based_on": "Attendance"})
	def test_net_tracks_payment_days(self):
		# nghỉ không lương vài ngày → I giảm theo payment_days, net theo I
		ensure_fiscal_year_2099()
		ensure_mvl_defaults()
		emp = make_employee("mvl_lwp@codes.com", company="Miyano")
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
		# I = ROUND(22tr / 30 × 27) = 19.800.000
		self.assertEqual(ss.payment_days, 27)
		self.assertEqual(comp["Lương theo công"], 19_800_000)
