import frappe


def execute():
	"""Cong Tac (+Traveler) -> Business Trip (+Traveler). pre_model_sync so tables/links are renamed
	before the renamed JSON syncs. The Workflow record keeps its name 'Cong Tac Approval' (record
	name) but its document_type is re-pointed."""
	for old, new in [
		("Cong Tac Traveler", "Business Trip Traveler"),
		("Cong Tac", "Business Trip"),
	]:
		if frappe.db.exists("DocType", old) and not frappe.db.exists("DocType", new):
			frappe.rename_doc("DocType", old, new, force=True)

	# rename_doc may not update child-row parenttype
	if frappe.db.table_exists("Business Trip Traveler"):
		frappe.db.sql(
			"UPDATE `tabBusiness Trip Traveler` SET parenttype = 'Business Trip' WHERE parenttype = 'Cong Tac'"
		)

	# workflow document_type + Expense Claim link option (rename_doc updates Links; pin for idempotency)
	if frappe.db.exists("Workflow", "Cong Tac Approval"):
		frappe.db.set_value("Workflow", "Cong Tac Approval", "document_type", "Business Trip")
	if frappe.db.exists("Custom Field", "Expense Claim-custom_business_trip"):
		frappe.db.set_value("Custom Field", "Expense Claim-custom_business_trip", "options", "Business Trip")
