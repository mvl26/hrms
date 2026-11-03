# Copyright (c) 2026, Miyano Việt Nam.
"""Đọc `MVL Payroll Settings` (Single) thành MVLConfig cho engine."""

import frappe

from hrms.vn_payroll.mvl import MVLConfig, default_config


def config_from_settings() -> MVLConfig:
	s = frappe.get_single("MVL Payroll Settings")
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
		# chưa migrate field → dùng mặc định thay vì 0 (deploy lệch không được im lặng bỏ KPCĐ)
		union_fee_rate=default_config().union_fee_rate
		if s.get("union_fee_rate") is None
		else s.union_fee_rate,
	)
