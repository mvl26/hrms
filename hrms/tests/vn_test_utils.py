# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# For license information, please see license.txt
"""Tiện ích dùng chung cho test của lớp bản địa hoá VN (Miyano)."""

import frappe


def default_company() -> str:
	"""Công ty để dựng dữ liệu test — KHÔNG hardcode tên.

	Hardcode ``company="Miyano"`` làm test chỉ chạy được trên site miyano; trên ``test_site``
	của CI (chỉ có ``_Test Company``) mọi lời gọi vỡ với
	``LinkValidationError: Could not find Company: Miyano``, kéo theo hàng loạt lỗi dây chuyền
	(``Salary Slip None not found``, ``'NoneType' object has no attribute ...``).

	Xác định công ty y hệt cách ``hrms.vn_payroll.setup_mvl`` làm, để cấu trúc lương MVL và dữ
	liệu test luôn thuộc cùng một công ty.
	"""
	company = frappe.defaults.get_defaults().get("company") or frappe.db.get_value("Company", {}, "name")
	if not company:
		raise AssertionError("site chưa có Company nào để dựng dữ liệu test")
	return company
