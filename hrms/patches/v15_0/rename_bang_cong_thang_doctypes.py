import frappe


def execute():
	"""Bang Cong Thang (+Detail) -> Monthly Attendance Sheet (+Detail). pre_model_sync so tables/
	links are renamed before the renamed JSON syncs. Child first, then parent."""
	for old, new in [
		("Bang Cong Thang Detail", "Monthly Attendance Sheet Detail"),
		("Bang Cong Thang", "Monthly Attendance Sheet"),
	]:
		if frappe.db.exists("DocType", old) and not frappe.db.exists("DocType", new):
			frappe.rename_doc("DocType", old, new, force=True)

	# rename_doc may not update child-row parenttype -> fix it explicitly
	if frappe.db.table_exists("Monthly Attendance Sheet Detail"):
		frappe.db.sql(
			"UPDATE `tabMonthly Attendance Sheet Detail` "
			"SET parenttype = 'Monthly Attendance Sheet' WHERE parenttype = 'Bang Cong Thang'"
		)

	# the standard print format record
	if frappe.db.exists("Print Format", "Bang Cong Thang") and not frappe.db.exists(
		"Print Format", "Monthly Attendance Sheet"
	):
		frappe.rename_doc("Print Format", "Bang Cong Thang", "Monthly Attendance Sheet", force=True)
