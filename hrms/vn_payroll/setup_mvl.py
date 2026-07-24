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


def ensure_custom_fields():
	# create_custom_fields chạy ALTER TABLE (DDL) → không gọi được trong transaction của test
	# (ImplicitCommitError). Guard: đã cài rồi thì thôi. Cài lần đầu chạy ngoài test (migrate/execute).
	if frappe.db.exists("Custom Field", "Salary Structure Assignment-custom_salary_type"):
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
			"Salary Slip": [
				{
					"fieldname": "custom_mvl_section",
					"fieldtype": "Section Break",
					"label": "MVL — kê khai",
					"insert_after": "net_pay",
				},
				{
					"fieldname": "custom_taxable_income",
					"fieldtype": "Currency",
					"label": "Thu nhập chịu thuế kê khai (U)",
					"read_only": 1,
					"insert_after": "custom_mvl_section",
				},
				{
					"fieldname": "custom_ins_company",
					"fieldtype": "Currency",
					"label": "BHXH - Công ty (R)",
					"read_only": 1,
					"insert_after": "custom_taxable_income",
				},
			],
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
