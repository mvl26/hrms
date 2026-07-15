import frappe
from frappe.model.utils.rename_field import rename_field

# Bang Cong Thang Detail total fields: VN-romanized -> English (labels stay Vietnamese).
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

TABLE = "tabBang Cong Thang Detail"


def _has_col(col: str) -> bool:
	# uncached check — frappe.db.get_table_columns caches per process and misleads mid-patch
	return bool(
		frappe.db.sql(
			"""SELECT 1 FROM information_schema.columns
			WHERE table_schema = DATABASE() AND table_name = %s AND column_name = %s""",
			(TABLE, col),
		)
	)


def execute():
	if not frappe.db.exists("DocType", "Bang Cong Thang Detail"):
		return
	for old, new in RENAMES.items():
		if not _has_col(old):
			continue
		if not _has_col(new):
			rename_field("Bang Cong Thang Detail", old, new)
		# rename_field can leave the old column orphaned — carry data over, then drop it.
		if _has_col(old) and _has_col(new):
			frappe.db.sql(f"UPDATE `{TABLE}` SET `{new}` = `{old}` WHERE `{new}` = 0 OR `{new}` IS NULL")
			frappe.db.sql_ddl(f"ALTER TABLE `{TABLE}` DROP COLUMN `{old}`")
