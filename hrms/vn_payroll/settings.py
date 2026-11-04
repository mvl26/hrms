# Copyright (c) 2026, Miyano Việt Nam.
"""Đọc tab "Lương Miyano (VN)" của `Payroll Settings` (Single) thành MVLConfig cho engine.

Trước 2026-11-04 tham số nằm ở doctype riêng `MVL Payroll Settings`; patch
`merge_mvl_payroll_settings` đã chuyển sang đây để payroll chỉ còn MỘT trang cài đặt."""

import frappe

from hrms.vn_payroll.mvl import MVLConfig, default_config


def config_from_settings() -> MVLConfig:
	s = frappe.get_single("Payroll Settings")
	tax = [
		(b.threshold_upto or float("inf"), (b.rate or 0) / 100.0, b.subtract or 0)
		for b in sorted(s.tax_brackets, key=lambda b: b.threshold_upto or float("inf"))
	]
	grossup = [
		(b.threshold_upto or float("inf"), b.subtract or 0, b.divisor or 1)
		for b in sorted(s.grossup_brackets, key=lambda b: b.threshold_upto or float("inf"))
	]
	return MVLConfig(
		personal_deduction=s.personal_deduction,
		dependent_deduction=s.dependent_deduction,
		lunch_rate=s.lunch_rate_per_day,
		ins_company=s.insurance_company_rate,
		ins_employee=s.insurance_employee_rate,
		probation_coef=s.probation_coefficient,
		tax_brackets=tax,
		grossup_brackets=grossup,
		# Chưa từng lưu KPCĐ → mặc định, KHÔNG phải 0. Soi `tabSingles` chứ không `s.get(...) is None`:
		# trường Float có trong meta thì ô trống vẫn đọc ra 0.0 (= im lặng bỏ KPCĐ). Số 0 HR cố ý
		# lưu thì vẫn là 0.
		union_fee_rate=s.union_fee_rate if union_fee_saved() else default_config().union_fee_rate,
	)


def union_fee_saved() -> bool:
	return bool(
		frappe.db.sql(
			"select 1 from `tabSingles` where doctype = 'Payroll Settings' and field = 'union_fee_rate'"
		)
	)
