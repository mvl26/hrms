"""Idempotent default setup for this VN HRMS fork.

Single entry point `ensure_defaults()`, wired to `after_install` and `after_migrate` (see hooks.py).
It is intentionally narrow and safe to run on every migrate:

  - Self-heals the Công Tác approval workflow + `COO` role by delegating to the existing idempotent
    `ensure_workflow()` (previously only ran once via the patch log, so a deleted workflow/role stayed
    gone until re-patched; now it is re-ensured on every migrate).
  - Seeds the VN leave types + attendance codes from `hrms/seed_data/` ONCE (`seed_master_data`):
    a record is inserted only when the site lacks it, and an existing one is never touched. They used
    to be fixtures, and `sync_fixtures` deletes + re-inserts every record on every migrate — HR moved
    `P` onto their own paid annual-leave type and each migrate put it back on "Nghỉ phép năm".
  - Verifies the fixture-backed schema (custom fields, property setters) is present and logs a
    warning if any is missing. It does NOT recreate fixture data — the `fixtures` mechanism owns that.
  - Warns about Leave Types that no Attendance Code points at. Mã công là neo của tuyến chấm công:
    một loại nghỉ không có mã cả ngày nào trỏ tới sẽ cho ra 0 công, im lặng. Nó chỉ CẢNH BÁO — mã
    công là master data do HR quyết, đoán một ký hiệu thay họ chỉ tạo rác.

It never mutates HR Settings (geolocation tracking stays off by default), never edits an existing
master record, and touches no payroll/attendance transactional data.
"""

import json

import frappe

from hrms.patches.v15_0.setup_cong_tac_workflow import ensure_workflow

# doctype -> fixture file basename (under hrms/fixtures/), both keyed by "name"
FIXTURE_DOCTYPES = {
	"Custom Field": "custom_field",
	"Property Setter": "property_setter",
}

# Dữ liệu gieo một lần (hrms/seed_data/) — sau đó thuộc về HR. Loại nghỉ trước, mã công sau:
# mã công trỏ link tới loại nghỉ.
SEED_LEAVE_TYPES = "leave_type"
SEED_ATTENDANCE_CODES = "attendance_code"
# Cột hệ thống trong file xuất — để Frappe tự đặt khi chèn.
SEED_SKIP_KEYS = ("modified", "creation", "owner", "modified_by", "docstatus")


def ensure_defaults():
	"""Idempotent post-install / post-migrate setup. Returns a small summary dict for testability."""
	ensure_workflow()
	seeded = seed_master_data()

	missing = check_fixture_master_data()
	if missing:
		frappe.logger("hrms").warning(
			f"hrms.setup_vn_defaults.ensure_defaults: fixture master data missing "
			f"(fixtures may not have synced): {missing}"
		)

	shifts_without_schedule = warn_shifts_without_working_days()

	unmapped = leave_types_without_code()
	if unmapped:
		frappe.logger("hrms").warning(
			f"hrms.setup_vn_defaults.ensure_defaults: loại nghỉ chưa có mã công cả ngày "
			f"(ngày nghỉ theo chúng sẽ ra 0 công): {unmapped}"
		)

	return {
		"workflow": bool(frappe.db.exists("Workflow", "Cong Tac Approval")),
		"coo_role": bool(frappe.db.exists("Role", "COO")),
		"seeded": seeded,
		"missing": missing,
		"leave_types_without_code": unmapped,
		"shifts_without_working_days": shifts_without_schedule,
	}


def seed_master_data() -> dict:
	"""Chèn loại nghỉ + mã công mặc định CÒN THIẾU; không bao giờ sửa bản ghi đã có.

	Công xoay quanh mã công, nên mã công quyết loại nghỉ chứ không ngược lại:
	  - Mã đã có trên site → để nguyên, kể cả khi HR đã chuyển nó sang loại nghỉ khác.
	  - Loại nghỉ mặc định chỉ được dựng khi CHƯA mã nào của nó có mặt trên site (site mới). Mã đã
	    có mà loại nghỉ thì không, nghĩa là HR đã chọn chỗ khác cho mã đó — dựng lại chỉ đẻ ra một
	    loại nghỉ mồ côi, chính là cái HR vừa xoá.
	  - Mã mới chèn chỉ gắn loại nghỉ mặc định nếu loại đó có mặt và chưa có mã khác giữ cùng cặp
	    (trạng thái, loại nghỉ) — nếu không `AttendanceCode.validate` sẽ chặn cả lượt migrate.

	Trả về {"Leave Type": [...], "Attendance Code": [...]} những gì vừa chèn."""
	leave_types = seed_records(SEED_LEAVE_TYPES)
	codes = seed_records(SEED_ATTENDANCE_CODES)
	seeded = {"Leave Type": [], "Attendance Code": []}

	for record in leave_types:
		name = record["name"]
		if frappe.db.exists("Leave Type", name):
			continue
		own_codes = [c["name"] for c in codes if c.get("leave_type") == name]
		if any(frappe.db.exists("Attendance Code", code) for code in own_codes):
			continue
		insert_seed(record)
		seeded["Leave Type"].append(name)

	for record in codes:
		if frappe.db.exists("Attendance Code", record["name"]):
			continue
		record = dict(record)
		leave_type = record.get("leave_type")
		if leave_type and (
			not frappe.db.exists("Leave Type", leave_type)
			or frappe.db.exists(
				"Attendance Code",
				{"leave_type": leave_type, "maps_to_status": record.get("maps_to_status")},
			)
		):
			record["leave_type"] = None
		insert_seed(record)
		seeded["Attendance Code"].append(record["name"])

	return seeded


def insert_seed(record: dict):
	doc = frappe.get_doc({k: v for k, v in record.items() if k not in SEED_SKIP_KEYS})
	# Loại nghỉ được chèn TRƯỚC mã của nó, nên hook `warn_if_unmapped` sẽ báo "chưa gắn mã" cho
	# một tình trạng chỉ kéo dài vài dòng — tắt tiếng để log migrate không đầy cảnh báo giả.
	muted = frappe.flags.mute_messages
	frappe.flags.mute_messages = True
	try:
		doc.insert(ignore_permissions=True)
	finally:
		frappe.flags.mute_messages = muted


def seed_records(seed: str) -> list[dict]:
	path = frappe.get_app_path("hrms", "seed_data", f"{seed}.json")
	# đường dẫn nội bộ của app (frappe.get_app_path), không đến từ request
	with open(path, encoding="utf-8") as f:  # nosemgrep
		return [record for record in json.load(f) if record.get("name")]


def warn_shifts_without_working_days() -> list[str]:
	"""Ca đang bật chấm công tự động mà chưa khai ngày làm việc trong tuần.

	CẢNH BÁO, không tự vá: lịch tuần là MẪU SỐ của phiếu lương, đoán hộ một giá trị "hợp lý" là
	đúng kiểu thay đổi im lặng mà repo này cấm. Có lịch mặc định của công ty thì chưa nguy hiểm —
	ca sẽ rơi về đó — nên chỉ cảnh báo khi cả hai đều trống.
	"""
	from hrms.hr.work_schedule import company_default_weekdays, shift_weekdays

	if company_default_weekdays():
		return []
	shifts = frappe.get_all("Shift Type", filters={"enable_auto_attendance": 1}, pluck="name")
	missing = [s for s in shifts if shift_weekdays(s) is None]
	if missing:
		frappe.logger("hrms").warning(
			f"hrms.setup_vn_defaults.ensure_defaults: ca chưa khai ngày làm việc trong tuần và "
			f"công ty cũng chưa có lịch mặc định (chấm công sẽ nổ lỗi cấu hình): {missing}"
		)
	return missing


def leave_types_without_code() -> list[str]:
	"""Loại nghỉ chưa có mã công CẢ NGÀY nào trỏ tới — ngày nghỉ theo chúng sẽ ra 0 công.

	Không tự sửa: mã công là master data do HR quyết, đoán một ký hiệu thay họ chỉ tạo rác. Chốt
	chặn thật nằm ở Đơn xin nghỉ (`leave_attendance_code.validate_leave_type_has_code`); hàm này chỉ
	để lỗi lộ ra lúc deploy chứ không phải lúc in bảng công."""
	linked = set(
		frappe.get_all(
			"Attendance Code",
			filters={"maps_to_status": "On Leave", "leave_type": ("is", "set")},
			pluck="leave_type",
		)
	)
	return sorted(name for name in frappe.get_all("Leave Type", pluck="name") if name not in linked)


def check_fixture_master_data() -> dict:
	"""Return {doctype: [absent names]} for fixture-backed master data not present on the site."""
	missing = {}
	for doctype, fixture in FIXTURE_DOCTYPES.items():
		absent = [name for name in _fixture_names(fixture) if not frappe.db.exists(doctype, name)]
		if absent:
			missing[doctype] = absent
	return missing


def _fixture_names(fixture: str) -> list[str]:
	path = frappe.get_app_path("hrms", "fixtures", f"{fixture}.json")
	# đường dẫn nội bộ của app (frappe.get_app_path), không đến từ request
	with open(path) as f:  # nosemgrep
		return [record["name"] for record in json.load(f) if record.get("name")]
