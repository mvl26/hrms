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
		self.validate_approver()

	def validate_dates(self):
		if self.from_date and self.to_date and getdate(self.from_date) > getdate(self.to_date):
			frappe.throw(_("Từ ngày không được sau Đến ngày."))

	def validate_travelers(self):
		if not self.travelers:
			frappe.throw(_("Vui lòng thêm ít nhất một người đi công tác."))

	def validate_approver(self):
		# Người duyệt (COO) bắt buộc trước khi rời trạng thái Nháp (trình duyệt qua workflow).
		if self.workflow_state and self.workflow_state != "Nháp" and not self.approver_coo:
			frappe.throw(_("Cần chọn người duyệt (COO) trước khi trình duyệt."))

	# --- notifications / assignment on workflow state change ---
	def on_update(self):
		self.notify_on_state_change()

	def on_update_after_submit(self):
		self.notify_on_state_change()

	def notify_on_state_change(self):
		"""Assign a ToDo (+ bell notification) to the right actor when the workflow moves on."""
		if not self.has_value_changed("workflow_state"):
			return
		state = self.workflow_state
		if state == "Chờ COO duyệt":
			self.assign_actor(self.approver_coo, _("Duyệt đề nghị công tác {0}").format(self.name))
		elif state == "COO đã duyệt":
			for user in self.hr_manager_users():
				self.assign_actor(user, _("Ra QĐ cử đi công tác {0}").format(self.name))
		elif state == "Đã ra QĐ":
			self.assign_actor(
				self.employee_user(self.registered_by),
				_("Làm đề nghị thanh toán công tác {0}").format(self.name),
			)

	def assign_actor(self, user, description):
		if not user:
			return
		if frappe.get_all(
			"ToDo",
			filters={"reference_type": "Cong Tac", "reference_name": self.name, "allocated_to": user, "status": "Open"},
			limit=1,
		):
			return  # already assigned — don't duplicate
		from frappe.desk.form.assign_to import add as assign_add

		assign_add({"assign_to": [user], "doctype": "Cong Tac", "name": self.name, "description": description})

	def hr_manager_users(self):
		users = frappe.get_all("Has Role", filters={"role": "HR Manager", "parenttype": "User"}, pluck="parent")
		return [u for u in set(users) if frappe.db.get_value("User", u, "enabled")]

	def employee_user(self, employee):
		return frappe.db.get_value("Employee", employee, "user_id") if employee else None
