# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# For license information, please see license.txt
"""Cầu nối engine MVL vào Salary Slip.

Chạy ở `doc_events["Salary Slip"]["validate"]` — SAU khi controller đã tính payment_days /
total_working_days và dựng các component từ Salary Structure. Ta đọc cấu hình NV (Salary Structure
Assignment) + số công, chạy engine, rồi ghi đè amount từng component và tổng gross/net. Chỉ tác động
lên slip dùng structure "MVL Việt Nam"; slip khác đi đường Frappe gốc.
"""

import frappe
from frappe.utils import flt, rounded

from hrms.vn_payroll.mvl import MVLInput, compute_mvl
from hrms.vn_payroll.settings import config_from_settings
from hrms.vn_payroll.setup_mvl import STRUCTURE

COMPONENT_FIELD = {
	"Lương theo công": "I",
	"Phụ cấp ăn trưa": "J",
	"Thuế TNCN (nộp thay)": "Q",
	"BHXH - NLĐ (nộp thay)": "S",
}


def get_mvl_assignment(doc) -> frappe._dict | None:
	"""Salary Structure Assignment hiệu lực của NV cho kỳ này (mới nhất, đã submit)."""
	period_end = doc.end_date or doc.start_date
	rows = frappe.get_all(
		"Salary Structure Assignment",
		filters={
			"employee": doc.employee,
			"salary_structure": STRUCTURE,
			"docstatus": 1,
			"from_date": ["<=", period_end],
		},
		fields=[
			"base",
			"custom_salary_type",
			"custom_bhxh_salary",
			"custom_dependents",
			"custom_register_personal_deduction",
			"custom_lunch_days_override",
		],
		order_by="from_date desc",
		limit=1,
	)
	return rows[0] if rows else None


def apply_mvl(doc, method=None):
	if doc.salary_structure != STRUCTURE:
		return
	ssa = get_mvl_assignment(doc)
	if not ssa:
		return
	standard_days = flt(doc.total_working_days)
	if not standard_days:
		return  # tránh chia 0 khi kỳ toàn ngày nghỉ

	inp = MVLInput(
		salary_type=ssa.custom_salary_type or "Chính thức",
		base=flt(ssa.base),
		bhxh_salary=flt(ssa.custom_bhxh_salary),
		dependents=int(ssa.custom_dependents or 0),
		register_personal_deduction=bool(ssa.custom_register_personal_deduction),
		lunch_days=flt(ssa.custom_lunch_days_override) or flt(doc.payment_days),
		standard_days=standard_days,
		worked_days=flt(doc.payment_days),
	)
	r = compute_mvl(inp, config_from_settings())
	amounts = {name: getattr(r, field) for name, field in COMPONENT_FIELD.items()}

	# Với NET, thuế + BHXH NLĐ do công ty nộp thay → KHÔNG trừ vào tiền NV nhận. Ép cờ ngay trên
	# row của slip (không tin cờ kế thừa từ component — Frappe recompute lúc submit đọc cờ trên row).
	deduct_from_net = inp.salary_type == "GROSS"
	for row in list(doc.earnings) + list(doc.deductions):
		if row.salary_component in amounts:
			row.amount = amounts[row.salary_component]
			row.default_amount = amounts[row.salary_component]
			if row.parentfield == "deductions":
				row.do_not_include_in_total = 0 if deduct_from_net else 1

	gross = sum(flt(row.amount) for row in doc.earnings)
	deduction = sum(flt(row.amount) for row in doc.deductions if not row.do_not_include_in_total)
	rate = flt(doc.exchange_rate) or 1.0

	doc.gross_pay = gross
	doc.total_deduction = deduction
	doc.net_pay = gross - deduction
	doc.rounded_total = rounded(doc.net_pay)
	doc.base_gross_pay = gross * rate
	doc.base_total_deduction = deduction * rate
	doc.base_net_pay = doc.net_pay * rate
	doc.base_rounded_total = rounded(doc.base_net_pay)

	# Kê khai (không hiện thành deduction để khỏi trừ net)
	doc.custom_taxable_income = r.U
	doc.custom_ins_company = r.R
