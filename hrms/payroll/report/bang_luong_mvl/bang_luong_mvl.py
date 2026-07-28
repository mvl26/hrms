# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# For license information, please see license.txt
"""Bảng lương MVL — CỘT GIỐNG HỆT file Excel gốc (docs/Cong_thuc_tinh_luong_MVL.md).

Đọc thẳng Salary Slip ĐÃ SUBMIT dùng MỘT trong các cấu trúc MVL (mỗi loại lương một cấu trúc) trong kỳ.
Mỗi cột tiền là một Salary Component → chỉ gom theo hàng (nhân viên) × cột. Read-only, có dòng TỔNG CỘNG.

Thứ tự cột đúng như Excel: Mã NV (ID, không bỏ được) · Họ tên · Loại (Toàn/Bán thời gian) · NET/GROSS ·
Hệ số E · Lương ngày công F · Lương đóng BHXH G · Số công H · Lương thực tế I · Phụ cấp ăn J ·
Tổng thu nhập K · Giảm trừ bản thân L · Số phụ thuộc M · Tổng giảm trừ N · TN quy đổi O · TN tính thuế P ·
Thuế TNCN Q · BH công ty R · BH NLĐ S · Thực lĩnh T · TN chịu thuế kê khai U.
"""

import frappe
from frappe import _
from frappe.utils import cint, flt, get_first_day, get_last_day, getdate

from hrms.vn_payroll.setup_mvl import STRUCTURE_NAMES

# (fieldname, nhãn, kiểu, tên Salary Component | None, width). Thứ tự = thứ tự cột Excel.
COLUMNS = [
	("employee", "Mã NV", "Link", None, 110),
	("employee_name", "Họ tên", "Data", None, 150),
	("work_type", "Loại", "Data", None, 100),
	("pay_mode", "NET/GROSS", "Data", None, 80),
	("coefficient", "Hệ số (E)", "Float", None, 65),
	("base_f", "Lương ngày công (F)", "Currency", "Lương ngày công", 120),
	("bhxh_g", "Lương đóng BHXH (G)", "Currency", "Lương đóng BHXH", 120),
	("worked_days", "Số công (H)", "Float", None, 75),
	("work_i", "Lương thực tế (I)", "Currency", "Lương theo công", 120),
	("lunch_j", "Phụ cấp ăn trưa (J)", "Currency", "Phụ cấp ăn trưa", 110),
	("gross_k", "Tổng thu nhập (K)", "Currency", "Tổng thu nhập", 120),
	("personal_l", "Giảm trừ bản thân (L)", "Currency", "Giảm trừ bản thân", 120),
	("dependents", "Số người phụ thuộc (M)", "Int", None, 90),
	("deduction_n", "Tổng giảm trừ (N)", "Currency", "Tổng giảm trừ gia cảnh", 120),
	("converted_o", "Thu nhập quy đổi (O)", "Currency", "Thu nhập quy đổi", 120),
	("taxable_p", "Thu nhập tính thuế (P)", "Currency", "Thu nhập tính thuế", 120),
	("tax_q", "Thuế TNCN (Q)", "Currency", "Thuế TNCN (nộp thay)", 110),
	("ins_company_r", "BH công ty (R)", "Currency", "BHXH - Công ty", 110),
	("ins_employee_s", "BH NLĐ (S)", "Currency", "BHXH - NLĐ (nộp thay)", 110),
	("net_t", "Thực lĩnh (T)", "Currency", None, 130),
	("declared_u", "TN chịu thuế kê khai (U)", "Currency", "Thu nhập chịu thuế kê khai", 130),
]


def execute(filters=None):
	filters = frappe._dict(filters or {})
	return get_columns(), get_data(filters)


def get_columns():
	return [
		{"label": _(label), "fieldname": key, "fieldtype": ftype, "width": width}
		| ({"options": "Employee"} if key == "employee" else {})
		| ({"precision": 2} if key == "coefficient" else {})
		for key, label, ftype, _comp, width in COLUMNS
	]


def work_type(salary_type: str) -> str:
	# hiện đúng loại lao động (Chính thức/Thử việc/Bán thời gian/Khoán/Chuyên gia); gộp 2 loại toàn thời gian.
	return "Toàn thời gian" if salary_type in ("Chính thức", "Thử việc") else (salary_type or "")


def pay_mode(salary_type: str) -> str:
	return "GROSS" if salary_type == "GROSS" else "NET"


def get_data(filters):
	if not (filters.month and filters.year):
		return []
	start = get_first_day(getdate(f"{cint(filters.year)}-{cint(filters.month):02d}-01"))
	end = get_last_day(start)

	slip_filters = {
		"docstatus": 1,
		"salary_structure": ["in", list(STRUCTURE_NAMES)],
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
			"payment_days",
			"net_pay",
		],
		order_by="employee",
	)
	if not slips:
		return []

	amounts = component_amounts([s.name for s in slips])
	money_cols = [(key, comp) for key, _l, ftype, comp, _w in COLUMNS if ftype == "Currency"]

	data, totals = [], frappe._dict()
	for s in slips:
		row = frappe._dict(
			employee=s.employee,
			employee_name=s.employee_name,
			work_type=work_type(s.custom_salary_type),
			pay_mode=pay_mode(s.custom_salary_type),
			coefficient=s.custom_coefficient,
			worked_days=s.payment_days,
			dependents=s.custom_dependents_slip,
			net_t=flt(s.net_pay),
		)
		for key, comp in money_cols:
			if comp:  # cột tiền lấy từ component; net_t lấy net_pay ở trên
				row[key] = flt(amounts.get(s.name, {}).get(comp))
		data.append(row)
		for key, _comp in money_cols:
			totals[key] = totals.get(key, 0.0) + flt(row.get(key))

	if data:
		data.append(frappe._dict(employee_name=_("TỔNG CỘNG"), **totals))
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
