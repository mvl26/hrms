import frappe

# Monthly Attendance Sheet Detail total fields: VN-romanized -> English (labels stay Vietnamese).
RENAMES = {
	"cong": "work_days",
	"phep": "annual_leave",
	"om": "sick_leave",
	"thai_san": "maternity_leave",
	"tnld": "work_accident_leave",
	"nghi_bu": "comp_off",
	"khong_luong": "unpaid_leave",
	"vang": "absent",
}

TABLE = "tabMonthly Attendance Sheet Detail"


def _has_col(col: str) -> bool:
	return bool(
		frappe.db.sql(
			"""SELECT 1 FROM information_schema.columns
			WHERE table_schema = DATABASE() AND table_name = %s AND column_name = %s""",
			(TABLE, col),
		)
	)


def execute():
	"""post_model_sync: model sync already created the new columns from the JSON; the old columns
	+ data still linger -> carry data over, then drop the old columns."""
	if not frappe.db.exists("DocType", "Monthly Attendance Sheet Detail"):
		return
	for old, new in RENAMES.items():
		if _has_col(old) and _has_col(new):
			frappe.db.sql(f"UPDATE `{TABLE}` SET `{new}` = `{old}` WHERE `{new}` = 0 OR `{new}` IS NULL")
		if _has_col(old):
			frappe.db.sql_ddl(f"ALTER TABLE `{TABLE}` DROP COLUMN `{old}`")
