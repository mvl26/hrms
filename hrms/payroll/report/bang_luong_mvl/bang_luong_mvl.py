# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# For license information, please see license.txt
"""Bảng lương MVL — bảng lương tháng đủ mọi cột như file Excel gốc (docs/Cong_thuc_tinh_luong_MVL.md).

Đọc thẳng các Salary Slip ĐÃ SUBMIT dùng cấu trúc "MVL Việt Nam" trong kỳ: mỗi cột tiền là một Salary
Component nên bảng chỉ gom lại theo hàng (nhân viên) × cột (thành phần). Read-only. Có dòng TỔNG CỘNG.
"""

import frappe
from frappe import _
from frappe.utils import cint, flt, get_first_day, get_last_day, getdate

from hrms.vn_payroll.setup_mvl import STRUCTURE

# (key báo cáo, nhãn cột, tên Salary Component) — theo thứ tự bảng lương Excel
COMPONENT_COLUMNS = [
	("base_f", "Lương ngày công (F)", "Lương ngày công"),
	("bhxh_g", "Lương đóng BHXH (G)", "Lương đóng BHXH"),
	("work_i", "Lương theo công (I)", "Lương theo công"),
	("lunch_j", "Phụ cấp ăn (J)", "Phụ cấp ăn trưa"),
	("gross_k", "Tổng thu nhập (K)", "Tổng thu nhập"),
	("personal_l", "Giảm trừ bản thân (L)", "Giảm trừ bản thân"),
	("deduction_n", "Tổng giảm trừ (N)", "Tổng giảm trừ gia cảnh"),
	("converted_o", "TN quy đổi (O)", "Thu nhập quy đổi"),
	("taxable_p", "TN tính thuế (P)", "Thu nhập tính thuế"),
	("tax_q", "Thuế TNCN (Q)", "Thuế TNCN (nộp thay)"),
	("ins_company_r", "BHXH Cty (R)", "BHXH - Công ty"),
	("ins_employee_s", "BHXH NLĐ (S)", "BHXH - NLĐ (nộp thay)"),
	("declared_u", "TN chịu thuế kê khai (U)", "Thu nhập chịu thuế kê khai"),
]


def execute(filters=None):
	filters = frappe._dict(filters or {})
	return get_columns(), get_data(filters)


def get_columns():
	col = [
		{
			"label": _("Mã NV"),
			"fieldname": "employee",
			"fieldtype": "Link",
			"options": "Employee",
			"width": 110,
		},
		{"label": _("Họ tên"), "fieldname": "employee_name", "fieldtype": "Data", "width": 160},
		{"label": _("Loại lương"), "fieldname": "salary_type", "fieldtype": "Data", "width": 110},
		{
			"label": _("Hệ số (E)"),
			"fieldname": "coefficient",
			"fieldtype": "Float",
			"width": 70,
			"precision": 2,
		},
		{
			"label": _("Công chuẩn"),
			"fieldname": "total_days",
			"fieldtype": "Float",
			"width": 80,
			"precision": 1,
		},
		{
			"label": _("Công (H)"),
			"fieldname": "worked_days",
			"fieldtype": "Float",
			"width": 75,
			"precision": 1,
		},
	]
	# F, G ngay sau công chuẩn/H trong file gốc, nhưng gom cột tiền theo COMPONENT_COLUMNS cho gọn
	for key, label, _comp in COMPONENT_COLUMNS[:2]:
		col.append({"label": _(label), "fieldname": key, "fieldtype": "Currency", "width": 120})
	col.append({"label": _("Phụ thuộc (M)"), "fieldname": "dependents", "fieldtype": "Int", "width": 80})
	for key, label, _comp in COMPONENT_COLUMNS[2:]:
		col.append({"label": _(label), "fieldname": key, "fieldtype": "Currency", "width": 120})
	col.append({"label": _("THỰC LĨNH (T)"), "fieldname": "net_t", "fieldtype": "Currency", "width": 130})
	col.append(
		{"label": _("Chi phí công ty"), "fieldname": "company_cost", "fieldtype": "Currency", "width": 130}
	)
	return col


def get_data(filters):
	if not (filters.month and filters.year):
		return []
	start = get_first_day(getdate(f"{cint(filters.year)}-{cint(filters.month):02d}-01"))
	end = get_last_day(start)

	slip_filters = {
		"docstatus": 1,
		"salary_structure": STRUCTURE,
		"start_date": [">=", start],
		"end_date": ["<=", end],
	}
	if filters.company:
		slip_filters["company"] = filters.company
	if filters.department:
		slip_filters["department"] = filters.department

	slips = frappe.get_all(
		"Salary Slip",
		filters=slip_filters,
		fields=[
			"name",
			"employee",
			"employee_name",
			"custom_salary_type",
			"custom_coefficient",
			"custom_dependents_slip",
			"total_working_days",
			"payment_days",
			"net_pay",
		],
		order_by="employee",
	)
	if not slips:
		return []

	amounts = component_amounts([s.name for s in slips])
	comp_by_key = {key: comp for key, _label, comp in COMPONENT_COLUMNS}

	data, totals = [], frappe._dict()
	for s in slips:
		row = frappe._dict(
			employee=s.employee,
			employee_name=s.employee_name,
			salary_type=s.custom_salary_type,
			coefficient=s.custom_coefficient,
			total_days=s.total_working_days,
			worked_days=s.payment_days,
			dependents=s.custom_dependents_slip,
			net_t=flt(s.net_pay),
		)
		for key, comp in comp_by_key.items():
			row[key] = flt(amounts.get(s.name, {}).get(comp))
		# chi phí công ty = thực lĩnh + thuế + BHXH NLĐ nộp thay + BHXH công ty
		row.company_cost = row.net_t + row.tax_q + row.ins_employee_s + row.ins_company_r
		data.append(row)
		for f in (*comp_by_key, "net_t", "company_cost"):
			totals[f] = totals.get(f, 0.0) + row[f]

	if data:
		total_row = frappe._dict(employee_name=_("TỔNG CỘNG"), **totals)
		data.append(total_row)
	return data


def component_amounts(slip_names):
	"""{slip: {component: amount}} cho mọi Salary Detail của các slip."""
	rows = frappe.get_all(
		"Salary Detail",
		filters={"parent": ["in", slip_names], "parenttype": "Salary Slip"},
		fields=["parent", "salary_component", "amount"],
	)
	out = {}
	for r in rows:
		out.setdefault(r.parent, {})[r.salary_component] = r.amount
	return out
