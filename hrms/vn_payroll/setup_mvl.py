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

# (tên, loại, is_tax_applicable, do_not_include_in_total)
COMPONENTS = [
	("Lương theo công", "Earning", 1, 0),
	("Phụ cấp ăn trưa", "Earning", 0, 0),  # miễn thuế TNCN
	("Thuế TNCN (nộp thay)", "Deduction", 0, 1),  # công ty nộp thay → không trừ net
	("BHXH - NLĐ (nộp thay)", "Deduction", 0, 1),
]

SALARY_TYPES = "\n".join(
	[
		"Chính thức",
		"Thử việc",
		"Parttime cư trú",
		"Parttime nước ngoài",
		"Parttime cam kết 08",
		"Khoán",
		"GROSS",
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
	if frappe.db.exists("Salary Structure", STRUCTURE):
		return
	doc = frappe.get_doc(
		{
			"doctype": "Salary Structure",
			"name": STRUCTURE,
			"company": frappe.defaults.get_defaults().get("company")
			or frappe.db.get_value("Company", {}, "name"),
			"is_active": "Yes",
			"payroll_frequency": "Monthly",
			"earnings": [
				{"salary_component": "Lương theo công", "amount": 0},
				{"salary_component": "Phụ cấp ăn trưa", "amount": 0},
			],
			"deductions": [
				{"salary_component": "Thuế TNCN (nộp thay)", "amount": 0},
				{"salary_component": "BHXH - NLĐ (nộp thay)", "amount": 0},
			],
		}
	)
	doc.insert(ignore_permissions=True)
	doc.db_set("docstatus", 1)  # submit để dùng được trong Salary Structure Assignment


def _slip_breakdown_fields():
	"""Toàn bộ thành phần lương MVL hiện trên MỖI phiếu (đầy đủ như bảng lương Excel).

	Read-only, engine điền khi validate. I/J là Earning, Q/S là Deduction (nằm trong lưới component);
	các trường ở đây là số trung gian F..P + kê khai để phiếu lương in ra đủ mọi cột.
	"""
	ro = {"read_only": 1}

	def f(fieldname, label, fieldtype="Currency", after=None, **kw):
		return {
			"fieldname": fieldname,
			"label": label,
			"fieldtype": fieldtype,
			"insert_after": after,
			**ro,
			**kw,
		}

	return [
		{
			"fieldname": "custom_mvl_section",
			"fieldtype": "Section Break",
			"label": "Chi tiết lương MVL",
			"insert_after": "net_pay",
		},
		f("custom_salary_type", "Loại lương", "Data", "custom_mvl_section"),
		f("custom_coefficient", "Hệ số lương (E)", "Float", "custom_salary_type", precision="2"),
		f("custom_base_salary", "Lương ngày công (F)", "Currency", "custom_coefficient"),
		f("custom_bhxh_salary_slip", "Lương đóng BHXH (G)", "Currency", "custom_base_salary"),
		{
			"fieldname": "custom_mvl_col1",
			"fieldtype": "Column Break",
			"insert_after": "custom_bhxh_salary_slip",
		},
		f("custom_gross_income", "Tổng thu nhập (K)", "Currency", "custom_mvl_col1"),
		f("custom_personal_deduction", "Giảm trừ bản thân (L)", "Currency", "custom_gross_income"),
		f("custom_dependents_slip", "Số người phụ thuộc (M)", "Int", "custom_personal_deduction"),
		f("custom_total_deduction", "Tổng giảm trừ (N)", "Currency", "custom_dependents_slip"),
		{
			"fieldname": "custom_mvl_col2",
			"fieldtype": "Column Break",
			"insert_after": "custom_total_deduction",
		},
		f("custom_converted_income", "Thu nhập quy đổi (O)", "Currency", "custom_mvl_col2"),
		f("custom_taxable_income_gross", "Thu nhập tính thuế (P)", "Currency", "custom_converted_income"),
		f(
			"custom_taxable_income",
			"Thu nhập chịu thuế kê khai (U)",
			"Currency",
			"custom_taxable_income_gross",
		),
		f("custom_ins_company", "BHXH - Công ty (R)", "Currency", "custom_taxable_income"),
	]


def ensure_custom_fields():
	# create_custom_fields chạy ALTER TABLE (DDL) → không gọi được trong transaction của test
	# (ImplicitCommitError). Guard theo field MỚI NHẤT: đã cài đủ thì thôi. Cài lần đầu / khi thêm
	# field mới chạy ngoài test (migrate/execute); test dựa vào migrate đã cài sẵn.
	if frappe.db.exists("Custom Field", "Salary Slip-custom_base_salary"):
		return
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


def ensure_mvl_defaults():
	"""Điểm vào duy nhất: gọi khi after_install / after_migrate và trong test."""
	ensure_components()
	ensure_custom_fields()
	ensure_structure()
	ensure_settings()
