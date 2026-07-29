import frappe


def execute():
	"""Report Bang Cham Cong Thang -> Monthly Attendance Report. pre_model_sync so the record is
	renamed before the (renamed) report folder syncs a fresh one."""
	if frappe.db.exists("Report", "Bang Cham Cong Thang") and not frappe.db.exists(
		"Report", "Monthly Attendance Report"
	):
		frappe.rename_doc("Report", "Bang Cham Cong Thang", "Monthly Attendance Report", force=True)
