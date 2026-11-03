# Copyright (c) 2026, Miyano Việt Nam.
"""Bảng lương MVL — CỘT GIỐNG HỆT mẫu `docs/Salary_template_clean.xlsx` (09/2026), hàng 8.

Đọc thẳng Salary Slip ĐÃ SUBMIT dùng MỘT trong các cấu trúc MVL (mỗi loại lương một cấu trúc) trong kỳ.
Mỗi cột tiền là một Salary Component → chỉ gom theo hàng (nhân viên) x cột. Read-only, có dòng TỔNG CỘNG.

Thứ tự và nhãn cột đúng như mẫu (A STT ↔ Mã NV trên màn hình, B…Z). Fieldname giữ chữ cột của bảng
06/2026 (`work_i`, `gross_k`, …) vì bộ xuất Excel và test đọc theo fieldname; chỉ nhãn theo mẫu mới.
"""

import frappe
from frappe import _
from frappe.utils import cint, flt, get_first_day, get_last_day, getdate

from hrms.vn_payroll.setup_mvl import STRUCTURE_NAMES

# Nhãn dòng cuối bảng. Hằng số vì bộ xuất Excel (`hrms/vn_payroll/salary_xlsx.py`) in đậm đúng
# dòng này — hai nơi gõ tay hai chuỗi là sớm muộn lệch nhau.
TOTAL_LABEL = "TỔNG CỘNG"

# (fieldname, nhãn, kiểu, tên Salary Component | None, width). Thứ tự = thứ tự cột Excel.
COLUMNS = [
	("employee", "Mã NV", "Link", None, 110),
	("employee_name", "Họ tên", "Data", None, 150),
	("work_type", "Loại Hợp đồng", "Data", None, 100),
	("pay_mode", "Loại Hợp đồng (Status)", "Data", None, 80),
	("coefficient", "Hệ số lương", "Float", None, 65),
	("base_f", "Lương tháng", "Currency", "Lương ngày công", 120),
	("bhxh_g", "Lương đóng BHXH", "Currency", "Lương đóng BHXH", 120),
	("worked_days", "Số công làm việc", "Float", None, 75),
	("work_i", "Lương thực tế", "Currency", "Lương theo công", 120),
	("lunch_j", "Phụ cấp ăn trưa", "Currency", "Phụ cấp ăn trưa", 110),
	("phone", "Hỗ trợ điện thoại", "Currency", "Hỗ trợ điện thoại", 110),
	("fuel", "Hỗ trợ xăng xe, đi lại", "Currency", "Hỗ trợ xăng xe", 110),
	("kpi_bonus", "Thưởng KPI", "Currency", "Thưởng KPI", 110),
	("holiday_bonus", "Thưởng (Lễ/Tết)", "Currency", "Tiền thưởng", 110),
	("gross_k", "Lương thực lĩnh chưa trừ thuế TNCN, BHXH", "Currency", "Tổng thu nhập", 130),
	("personal_l", "Giảm trừ bản thân", "Currency", "Giảm trừ bản thân", 120),
	("dependents", "Số người phụ thuộc", "Int", None, 90),
	("deduction_n", "Tổng các khoản giảm trừ", "Currency", "Tổng giảm trừ gia cảnh", 120),
	("converted_o", "Thu nhập làm căn cứ quy đổi", "Currency", "Thu nhập quy đổi", 120),
	("taxable_p", "Thu nhập tính thuế", "Currency", "Thu nhập tính thuế", 120),
	("tax_q", "Thuế TNCN/PIT", "Currency", "Thuế TNCN (nộp thay)", 110),
	("ins_company_r", "Bảo hiểm công ty trả", "Currency", "BHXH - Công ty", 110),
	("ins_employee_s", "Bảo hiểm NLĐ trả", "Currency", "BHXH - NLĐ (nộp thay)", 110),
	("union_fee", "KPCĐ", "Currency", "KPCĐ - Công ty", 100),
	("net_t", "Thực lĩnh sau khi trừ TNCN, BHXH", "Currency", None, 130),
	("declared_u", "Thu nhập chịu thuế", "Currency", "Thu nhập chịu thuế kê khai", 130),
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
		# Mặc định CHỈ phiếu đã duyệt: bảng lương là chứng từ đem trình ký, lẫn phiếu chưa chốt vào
		# là ký lên số có thể còn đổi. Bật `include_drafts` để soát trước khi duyệt — khi đó bản
		# xuất Excel tự đóng dấu cảnh báo lên tiêu đề (xem `salary_xlsx.subtitle_line`).
		"docstatus": ["in", [0, 1]] if cint(filters.include_drafts) else 1,
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
			"total_working_days",
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
			# không phải cột: bộ xuất Excel in dòng "Số công làm việc chuẩn" từ đây
			standard_days=s.total_working_days,
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
		data.append(frappe._dict(employee_name=_(TOTAL_LABEL), **totals))
	return data


def component_amounts(slip_names):
	"""{slip: {component: tổng amount}} cho mọi Salary Detail của các slip.

	Cộng dồn: một component có thể có nhiều row trên cùng phiếu (row gõ tay + row Additional Salary)."""
	rows = frappe.get_all(
		"Salary Detail",
		filters={"parent": ["in", slip_names], "parenttype": "Salary Slip"},
		fields=["parent", "salary_component", "amount"],
	)
	out = {}
	for r in rows:
		per_slip = out.setdefault(r.parent, {})
		per_slip[r.salary_component] = flt(per_slip.get(r.salary_component)) + flt(r.amount)
	return out
