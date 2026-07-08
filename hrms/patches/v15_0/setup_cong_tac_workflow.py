"""Idempotently create the approval workflow for Công Tác (business trip):
Role "COO" (new; HCNSPC = existing HR Manager), the custom Workflow States/Actions, and the
Workflow "Cong Tac Approval". Runs as a patch (deploys to all sites) and is safe to re-run.
"""

import frappe

STATES = {
	"Nháp": "Warning",
	"Chờ COO duyệt": "Warning",
	"COO đã duyệt": "Success",
	"Đã ra QĐ": "Success",
	"Hoàn tất": "Success",
	"Từ chối": "Danger",
}
ACTIONS = ["Gửi duyệt", "Duyệt", "Từ chối", "Ra QĐ", "Hoàn tất"]


def execute():
	ensure_workflow()


def ensure_workflow():
	if not frappe.db.exists("Role", "COO"):
		frappe.get_doc({"doctype": "Role", "role_name": "COO", "desk_access": 1}).insert(ignore_permissions=True)

	for name, style in STATES.items():
		if not frappe.db.exists("Workflow State", name):
			frappe.get_doc(
				{"doctype": "Workflow State", "workflow_state_name": name, "style": style}
			).insert(ignore_permissions=True)

	for name in ACTIONS:
		if not frappe.db.exists("Workflow Action Master", name):
			frappe.get_doc(
				{"doctype": "Workflow Action Master", "workflow_action_name": name}
			).insert(ignore_permissions=True)

	if frappe.db.exists("Workflow", "Cong Tac Approval"):
		return

	frappe.get_doc(
		{
			"doctype": "Workflow",
			"workflow_name": "Cong Tac Approval",
			"document_type": "Cong Tac",
			"is_active": 1,
			"workflow_state_field": "workflow_state",
			"send_email_alert": 0,
			"states": [
				{"state": "Nháp", "doc_status": "0", "allow_edit": "HR User"},
				{"state": "Chờ COO duyệt", "doc_status": "0", "allow_edit": "HR User"},
				{"state": "COO đã duyệt", "doc_status": "1", "allow_edit": "HR Manager"},
				{"state": "Đã ra QĐ", "doc_status": "1", "allow_edit": "HR Manager"},
				{"state": "Hoàn tất", "doc_status": "1", "allow_edit": "HR Manager"},
				{"state": "Từ chối", "doc_status": "0", "allow_edit": "HR User"},
			],
			"transitions": [
				{"state": "Nháp", "action": "Gửi duyệt", "next_state": "Chờ COO duyệt", "allowed": "HR User"},
				{"state": "Chờ COO duyệt", "action": "Duyệt", "next_state": "COO đã duyệt", "allowed": "COO"},
				{"state": "Chờ COO duyệt", "action": "Từ chối", "next_state": "Từ chối", "allowed": "COO"},
				{"state": "COO đã duyệt", "action": "Ra QĐ", "next_state": "Đã ra QĐ", "allowed": "HR Manager"},
				{"state": "Đã ra QĐ", "action": "Hoàn tất", "next_state": "Hoàn tất", "allowed": "HR Manager"},
			],
		}
	).insert(ignore_permissions=True)
