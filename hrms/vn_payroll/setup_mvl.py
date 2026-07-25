# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# For license information, please see license.txt
"""Đóng gói cấu hình lương MVL vào app: tạo Salary Component + Salary Structure + custom fields +
seed tham số mặc định. Idempotent, KHÔNG ghi đè giá trị HR đã sửa (self-heal mỗi migrate).

Thiết kế payslip NET: lương theo công (I) + phụ cấp ăn (J) là Earning → gross = K. Thuế (Q) và BHXH
NLĐ (S) là Deduction `do_not_include_in_total` → hiện trên phiếu nhưng KHÔNG trừ vào net (công ty nộp
thay) ⇒ net_pay = K tự nhiên. BHXH công ty (R) + thu nhập kê khai (U) lưu ở custom field của slip.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from hrms.vn_payroll.mvl import default_config

STRUCTURE = "MVL Việt Nam"

# Mọi cột tiền của bảng lương MVL là một Salary Component (auto-sinh trong cấu trúc). Chỉ Lương theo
# công (I) + Phụ cấp ăn (J) là khoản THẬT cộng vào lương; còn lại do_not_include_in_total → hiện trên
# lưới phiếu để đọc đủ như bảng lương nhưng KHÔNG làm sai tổng (thuế/BHXH do công ty nộp thay).
# (tên, loại, is_tax_applicable, do_not_include_in_total)
COMPONENTS = [
	("Lương ngày công", "Earning", 0, 1),  # F — mức lương/công (tham chiếu)
	("Lương đóng BHXH", "Earning", 0, 1),  # G
	("Lương theo công", "Earning", 1, 0),  # I — thật, cộng lương
	("Phụ cấp ăn trưa", "Earning", 0, 0),  # J — thật, miễn thuế
	("Tiền thưởng", "Earning", 1, 0),  # HR tự điền — thật, chịu thuế, cộng lương
	("Tổng thu nhập", "Earning", 0, 1),  # K
	("Thu nhập quy đổi", "Earning", 0, 1),  # O
	("Thu nhập tính thuế", "Earning", 0, 1),  # P
	("Thu nhập chịu thuế kê khai", "Earning", 0, 1),  # U
	("Giảm trừ bản thân", "Deduction", 0, 1),  # L
	("Tổng giảm trừ gia cảnh", "Deduction", 0, 1),  # N
	("Thuế TNCN (nộp thay)", "Deduction", 0, 1),  # Q — công ty nộp thay
	("BHXH - NLĐ (nộp thay)", "Deduction", 0, 1),  # S
	("BHXH - Công ty", "Deduction", 0, 1),  # R
]
EARNINGS = [c[0] for c in COMPONENTS if c[1] == "Earning"]
DEDUCTIONS = [c[0] for c in COMPONENTS if c[1] == "Deduction"]
# Khoản THẬT cộng vào net (NET mode). GROSS thêm Thuế/BHXH NLĐ vào deduction — xử lý ở apply_mvl.
REAL_EARNINGS = ("Lương theo công", "Phụ cấp ăn trưa", "Tiền thưởng")
# Component HR TỰ ĐIỀN — engine đọc chứ KHÔNG ghi đè.
BONUS_COMPONENT = "Tiền thưởng"

# GROSS bị BỎ khỏi lựa chọn: engine chưa hiện thực nhánh GROSS (r.P/r.Q về 0, J=0) trong khi hook lại
# nối thuế/BHXH thành trừ thật → phiếu GROSS sai âm thầm. Miyano trả TOÀN NET. Thêm lại khi làm xong GROSS.
SALARY_TYPES = "\n".join(
	[
		"Chính thức",
		"Thử việc",
		"Parttime cư trú",
		"Parttime nước ngoài",
		"Parttime cam kết 08",
		"Khoán",
	]
)


def ensure_components():
	for name, ctype, taxable, do_not_include in COMPONENTS:
		if frappe.db.exists("Salary Component", name):
			# self-heal: engine điền amount khi validate, nên component KHÔNG được biến mất khi = 0
			frappe.db.set_value("Salary Component", name, "remove_if_zero_valued", 0)
			continue
		frappe.get_doc(
			{
				"doctype": "Salary Component",
				"salary_component": name,
				"salary_component_abbr": None,
				"type": ctype,
				"is_tax_applicable": taxable,
				"do_not_include_in_total": do_not_include,
				"depends_on_payment_days": 0,  # engine đã tính theo công, không để Frappe prorate lại
				"remove_if_zero_valued": 0,  # giữ lại dù amount = 0 → apply_mvl mới có row để điền
				"description": "Tự sinh cho lương MVL (đừng xoá).",
			}
		).insert(ignore_permissions=True)


def ensure_structure():
	"""Tạo/đồng bộ cấu trúc MVL: mọi component trong COMPONENTS phải có mặt ở đúng bảng (idempotent)."""
	if not frappe.db.exists("Salary Structure", STRUCTURE):
		frappe.get_doc(
			{
				"doctype": "Salary Structure",
				"name": STRUCTURE,
				"company": frappe.defaults.get_defaults().get("company")
				or frappe.db.get_value("Company", {}, "name"),
				"is_active": "Yes",
				"payroll_frequency": "Monthly",
			}
		).insert(ignore_permissions=True)

	doc = frappe.get_doc("Salary Structure", STRUCTURE)
	changed = False
	for table, names in (("earnings", EARNINGS), ("deductions", DEDUCTIONS)):
		present = {r.salary_component for r in doc.get(table)}
		for name in names:
			if name not in present:
				doc.append(table, {"salary_component": name, "amount": 0})
				changed = True
	if changed:
		if doc.docstatus == 1:
			doc.db_set("docstatus", 0)  # cho phép sửa rồi submit lại
		doc.flags.ignore_validate_update_after_submit = True
		doc.save(ignore_permissions=True)
		doc.db_set("docstatus", 1)  # submit để dùng trong Salary Structure Assignment


# Tham số KHÔNG phải tiền (không làm Salary Component được): hệ số E, số phụ thuộc M, loại lương.
# Mọi cột TIỀN (F,G,K,L,N,O,P,Q,R,S,U) là Salary Component. Số công H = payment_days native.
def _slip_breakdown_fields():
	ro = {"read_only": 1}

	def f(fieldname, label, fieldtype, after):
		return {"fieldname": fieldname, "label": label, "fieldtype": fieldtype, "insert_after": after, **ro}

	return [
		{
			"fieldname": "custom_mvl_section",
			"fieldtype": "Section Break",
			"label": "Chi tiết lương MVL",
			"insert_after": "net_pay",
		},
		f("custom_salary_type", "Loại lương", "Data", "custom_mvl_section"),
		f("custom_coefficient", "Hệ số lương (E)", "Float", "custom_salary_type"),
		f("custom_dependents_slip", "Số người phụ thuộc (M)", "Int", "custom_coefficient"),
		f("custom_lunch_days", "Số ngày ăn trưa", "Int", "custom_dependents_slip"),
	]


# Custom field tiền cũ (nay đã chuyển thành Salary Component) → gỡ khỏi phiếu khi migrate/execute.
OBSOLETE_SLIP_FIELDS = [
	"custom_base_salary",
	"custom_bhxh_salary_slip",
	"custom_gross_income",
	"custom_personal_deduction",
	"custom_total_deduction",
	"custom_converted_income",
	"custom_taxable_income_gross",
	"custom_taxable_income",
	"custom_ins_company",
	"custom_mvl_col1",
	"custom_mvl_col2",
]


def ensure_custom_fields():
	# create_custom_fields / delete đều chạy ALTER TABLE (DDL) → ImplicitCommitError trong transaction
	# của test. Guard: đã đúng trạng thái (field mới có + field tiền cũ đã gỡ) thì thôi. Chỉ đụng schema
	# khi chưa đúng → chạy lúc migrate/execute (ngoài test); test dựa vào migrate đã dọn sẵn.
	ready = frappe.db.exists("Custom Field", "Salary Slip-custom_lunch_days") and not frappe.db.exists(
		"Custom Field", "Salary Slip-custom_base_salary"
	)
	if ready:
		return
	for fn in OBSOLETE_SLIP_FIELDS:
		frappe.delete_doc_if_exists("Custom Field", f"Salary Slip-{fn}")
	create_custom_fields(
		{
			"Salary Structure Assignment": [
				{
					"fieldname": "custom_mvl_section",
					"fieldtype": "Section Break",
					"label": "Cấu hình lương MVL",
					"insert_after": "base",
				},
				{
					"fieldname": "custom_salary_type",
					"fieldtype": "Select",
					"label": "Loại lương",
					"options": SALARY_TYPES,
					"default": "Chính thức",
					"insert_after": "custom_mvl_section",
				},
				{
					"fieldname": "custom_bhxh_salary",
					"fieldtype": "Currency",
					"label": "Lương đóng BHXH (G)",
					"description": "Để trống → không đóng BHXH (thử việc, parttime, khoán).",
					"insert_after": "custom_salary_type",
				},
				{
					"fieldname": "custom_dependents",
					"fieldtype": "Int",
					"label": "Số người phụ thuộc",
					"insert_after": "custom_bhxh_salary",
				},
				{
					"fieldname": "custom_register_personal_deduction",
					"fieldtype": "Check",
					"label": "Đăng ký giảm trừ bản thân",
					"insert_after": "custom_dependents",
				},
				{
					"fieldname": "custom_lunch_days_override",
					"fieldtype": "Int",
					"label": "Số ngày ăn (nếu khác số công)",
					"description": "Để trống → dùng số công thực tế (payment_days).",
					"insert_after": "custom_register_personal_deduction",
				},
			],
			"Salary Slip": _slip_breakdown_fields(),
		},
		ignore_validate=True,
	)


def ensure_settings():
	"""Seed tham số + biểu thuế/gross-up CHỈ khi chưa có (không ghi đè giá trị HR đã sửa)."""
	s = frappe.get_single("MVL Payroll Settings")
	cfg = default_config()
	if not s.personal_deduction:
		s.personal_deduction = cfg.personal_deduction
		s.dependent_deduction = cfg.dependent_deduction
		s.lunch_rate_per_day = cfg.lunch_rate
		s.insurance_company_rate = cfg.ins_company
		s.insurance_employee_rate = cfg.ins_employee
		s.probation_coefficient = cfg.probation_coef
	if not s.tax_brackets:
		for threshold, rate, subtract in cfg.tax_brackets:
			s.append(
				"tax_brackets",
				{
					"threshold_upto": None if threshold == float("inf") else threshold,
					"rate": rate * 100,
					"subtract": subtract,
				},
			)
	if not s.grossup_brackets:
		for threshold, subtract, divisor in cfg.grossup_brackets:
			s.append(
				"grossup_brackets",
				{
					"threshold_upto": None if threshold == float("inf") else threshold,
					"subtract": subtract,
					"divisor": divisor,
				},
			)
	s.save(ignore_permissions=True)


PRINT_FORMAT = "Phiếu lương MVL"


def ensure_default_print_format():
	"""Đặt "Phiếu lương MVL" làm print format mặc định của Salary Slip → nút In hiện phiếu đủ thành
	phần thay vì mẫu chuẩn của Frappe (chỉ có lưới earnings/deductions)."""
	if not frappe.db.exists("Print Format", PRINT_FORMAT):
		return  # print format là standard doc, đồng bộ khi migrate/reload — chưa có thì bỏ qua
	existing = frappe.db.get_value(
		"Property Setter", {"doc_type": "Salary Slip", "property": "default_print_format"}, "name"
	)
	if existing:
		frappe.db.set_value("Property Setter", existing, "value", PRINT_FORMAT)
		return
	frappe.get_doc(
		{
			"doctype": "Property Setter",
			"doctype_or_field": "DocType",
			"doc_type": "Salary Slip",
			"property": "default_print_format",
			"value": PRINT_FORMAT,
			"property_type": "Data",
		}
	).insert(ignore_permissions=True)


def ensure_mvl_defaults():
	"""Điểm vào duy nhất: gọi khi after_install / after_migrate và trong test."""
	ensure_components()
	ensure_custom_fields()
	ensure_structure()
	ensure_settings()
	ensure_default_print_format()
