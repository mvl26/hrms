# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# For license information, please see license.txt
"""Cong Tac (Business Trip) — a multi-person trip request driven by a Frappe Workflow
(Nháp -> Chờ COO duyệt -> COO đã duyệt -> Đã ra QĐ -> Hoàn tất). Desk-only; never touches
Attendance or payroll. Trip expenses are separate per-traveler Expense Claims linked back here."""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate


class CongTac(Document):
	def validate(self):
		self.validate_dates()
		self.validate_travelers()

	def validate_dates(self):
		if self.from_date and self.to_date and getdate(self.from_date) > getdate(self.to_date):
			frappe.throw(_("Từ ngày không được sau Đến ngày."))

	def validate_travelers(self):
		if not self.travelers:
			frappe.throw(_("Vui lòng thêm ít nhất một người đi công tác."))

	def before_submit(self):
		if not self.approver_coo:
			frappe.throw(_("Cần chọn người duyệt (COO) trước khi trình duyệt."))
