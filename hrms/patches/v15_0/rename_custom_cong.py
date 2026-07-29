import frappe

TABLE = "tabAttendance"


def _has_col(col: str) -> bool:
	return bool(
		frappe.db.sql(
			"""SELECT 1 FROM information_schema.columns
			WHERE table_schema = DATABASE() AND table_name = %s AND column_name = %s""",
			(TABLE, col),
		)
	)


def execute():
	"""Attendance.custom_cong -> custom_work_credit (display-only công; payroll-invariant).

	post_model_sync: by now the fixture has created custom_work_credit; the old custom_cong column
	+ data still lingers -> carry data over, drop the stale Custom Field record + its column.
	"""
	if _has_col("custom_cong") and _has_col("custom_work_credit"):
		frappe.db.sql(
			"UPDATE `tabAttendance` SET custom_work_credit = custom_cong "
			"WHERE custom_work_credit = 0 OR custom_work_credit IS NULL"
		)
	# remove the stale Custom Field record (raw delete — no column side effect), then drop the column
	frappe.db.delete("Custom Field", {"name": "Attendance-custom_cong"})
	if _has_col("custom_cong"):
		frappe.db.sql_ddl("ALTER TABLE `tabAttendance` DROP COLUMN custom_cong")
