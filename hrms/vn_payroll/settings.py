# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# For license information, please see license.txt
"""Đọc `MVL Payroll Settings` (Single) thành MVLConfig cho engine."""

import frappe

from hrms.vn_payroll.mvl import MVLConfig


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
	)
