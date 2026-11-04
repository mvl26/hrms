# Copyright (c) 2026, Miyano Việt Nam.
"""Gộp `MVL Payroll Settings` vào `Payroll Settings` — payroll chỉ còn MỘT trang cài đặt (2026-11-04).

Tham số engine MVL (giảm trừ, ăn trưa, hệ số thử việc, tỷ lệ BH/KPCĐ, biểu thuế + biểu quy đổi NET)
nay là tab "Lương Miyano (VN)" của Payroll Settings, cùng fieldname với bản cũ. Patch này:

1. chép NGUYÊN chuỗi giá trị trong `tabSingles` của bản cũ sang Payroll Settings (SQL thô, không
   qua meta: không đổi kiểu, không làm tròn, không phụ thuộc thứ tự đồng bộ doctype);
2. chuyển các dòng bậc thuế / bậc quy đổi sang cha mới — bản cũ là số HR đang dùng nên THẮNG mọi
   giá trị mặc định đã lỡ seed vào Payroll Settings (không nhân đôi bậc);
3. xoá giá trị + bản ghi DocType cũ.

KPCĐ bản cũ chưa từng lưu (trên miyano) thì ghi đúng tỷ lệ engine đang dùng (mặc định 2%): để
trống thì Payroll Settings đọc ra 0.0 — là "không thu KPCĐ", sai.

Không `git revert` được (đã xoá doctype cũ). Muốn quay lại thì khôi phục doctype cũ rồi chép ngược.
"""

import frappe

from hrms.vn_payroll.mvl import default_config

OLD = "MVL Payroll Settings"
TARGET = "Payroll Settings"

SCALAR_FIELDS = (
	"personal_deduction",
	"dependent_deduction",
	"lunch_rate_per_day",
	"probation_coefficient",
	"insurance_company_rate",
	"insurance_employee_rate",
	"union_fee_rate",
)
TABLES = (("Mvl Tax Bracket", "tax_brackets"), ("Mvl Grossup Bracket", "grossup_brackets"))


def execute():
	move_scalar_values()
	for child, fieldname in TABLES:
		move_rows(child, fieldname)
	frappe.db.delete("Singles", {"doctype": OLD})
	if frappe.db.exists("DocType", OLD):
		frappe.delete_doc("DocType", OLD, force=True, ignore_permissions=True, ignore_missing=True)
	frappe.clear_cache(doctype=TARGET)


def move_scalar_values():
	rows = frappe.db.sql(
		"select field, value from `tabSingles` where doctype = %s and field in %s",
		(OLD, SCALAR_FIELDS),
	)
	if not rows:
		return
	values = dict(rows)
	# KPCĐ bản cũ chưa từng lưu (miyano) → engine đang dùng mặc định. Ghi rõ số đó: sang Payroll
	# Settings trường đã có trong meta kiểu Float, ô trống đọc thành 0.0 = âm thầm không thu KPCĐ.
	if values.get("union_fee_rate") is None:
		values["union_fee_rate"] = default_config().union_fee_rate
	for field, value in values.items():
		set_raw(field, value)


def set_raw(field: str, value):
	frappe.db.delete("Singles", {"doctype": TARGET, "field": field})
	frappe.db.sql(
		"insert into `tabSingles` (doctype, field, value) values (%s, %s, %s)", (TARGET, field, value)
	)


def move_rows(child: str, fieldname: str):
	if not frappe.db.count(child, {"parenttype": OLD, "parentfield": fieldname}):
		return
	frappe.db.delete(child, {"parenttype": TARGET, "parentfield": fieldname})
	frappe.db.sql(
		f"update `tab{child}` set parent = %s, parenttype = %s where parenttype = %s and parentfield = %s",
		(TARGET, TARGET, OLD, fieldname),
	)
