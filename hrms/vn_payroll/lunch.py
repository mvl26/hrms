# Copyright (c) 2026, Miyano Việt Nam.
"""Số ngày ăn trưa tại công ty — suy từ checkin, KHÁC số công.

Quy tắc (khớp công thức HR): một ngày tính ăn trưa khi ngày đó là ngày công (Present / Half Day) VÀ
dấu vào-ra phủ cả giờ nghỉ trưa — vào TRƯỚC giờ bắt đầu nghỉ trưa và ra TỪ giờ hết nghỉ trưa trở đi.
Giờ nghỉ trưa lấy từ Shift Type của ngày đó (`custom_lunch_start`/`custom_lunch_end`); nếu ca không
đặt thì dùng mặc định 12:00-13:30.
"""

import frappe
from frappe.utils import cint, get_datetime, get_last_day, getdate

from hrms.db_utils import commit_unless_test

DEFAULT_LUNCH_START = 12 * 60  # 12:00 = 720 phút (hết ca sáng)
DEFAULT_LUNCH_END = 13 * 60 + 30  # 13:30 = 810 phút (vào ca chiều)
# Nghỉ trưa luôn rơi vào giữa ngày. Chỉ tin cấu hình khi start < end và nằm trong khoảng này; ngoài
# ra (để trống, hoặc Time field bị đặt = giờ hiện tại → khung ~23:xx) coi như chưa cấu hình → mặc định.
LUNCH_EARLIEST = 10 * 60  # 10:00
LUNCH_LATEST = 16 * 60  # 16:00
LUNCH_ELIGIBLE_STATUS = ("Present", "Half Day")

# Mã công KHÔNG bao giờ tính ăn tại công ty: đi công tác ăn ngoài (và đã có Expense Claim riêng),
# làm tại nhà thì ăn ở nhà. Loại theo MÃ chứ không theo status vì cả hai mã này đều có thể mang
# status Present (công tác nội thành chấm Present, WFH chấm Work From Home tuỳ cấu hình).
NO_LUNCH_CODES = ("CT", "W")

# Ô "Ăn trưa" trên phiếu chấm công: người chọn thì máy không đè lại nữa (spec §5.3).
LUNCH_OVERRIDE_AUTO = "Tự động"
LUNCH_OVERRIDE_YES = "Có"
LUNCH_OVERRIDE_NO = "Không"

# Dưới ngưỡng này thì dấu chấm KHÔNG đủ để kết luận có ở lại qua trưa hay không (0 dấu = chấm tay
# hoặc sửa qua soát công; 1 dấu = quên chấm ra) → rơi về mặc định theo status thay vì phạt về 0.
MIN_PUNCHES_TO_DECIDE = 2


def _minutes(dt) -> int:
	return dt.hour * 60 + dt.minute


def _td_minutes(td) -> int | None:
	"""Time (timedelta) của Shift Type → phút trong ngày; None nếu không đặt."""
	if td is None:
		return None
	if hasattr(td, "total_seconds"):
		return int(td.total_seconds() // 60)
	parts = str(td).split(":")
	return int(parts[0]) * 60 + int(parts[1])


def shift_lunch_window(shift: str | None) -> tuple[int, int]:
	"""(phút bắt đầu, phút kết thúc) giờ nghỉ trưa của ca; thiếu/không hợp lệ → mặc định 12:00-13:30.

	Chỉ dùng cấu hình khi là một khung nghỉ trưa GIỮA NGÀY hợp lý (start < end, trong 10:00-16:00). Time
	field để trống có thể bị đặt = giờ hiện tại (không phải NULL) → khung rác (vd 23:26); khi đó về mặc định
	để số buổi ăn trưa không bị 0 oan (an toàn cho ca mới quên cấu hình)."""
	default = (DEFAULT_LUNCH_START, DEFAULT_LUNCH_END)
	if not shift:
		return default
	ls, le = frappe.db.get_value("Shift Type", shift, ["custom_lunch_start", "custom_lunch_end"]) or (
		None,
		None,
	)
	start = _td_minutes(ls)
	end = _td_minutes(le)
	if start is None or end is None or not (LUNCH_EARLIEST <= start < end <= LUNCH_LATEST):
		return default
	return start, end


def checkins_cover_lunch(day_datetimes, window: tuple[int, int]) -> bool:
	"""Dấu vào-ra của một ngày có phủ giờ nghỉ trưa không (vào < bắt đầu VÀ ra ≥ kết thúc)."""
	if not day_datetimes:
		return False
	lunch_start, lunch_end = window
	first, last = min(day_datetimes), max(day_datetimes)
	return _minutes(first) < lunch_start and _minutes(last) >= lunch_end


def is_lunch_day(status: str | None, shift: str | None, day_datetimes) -> bool:
	"""Luật per-ngày: ngày công (Present/Half Day) VÀ checkin phủ giờ nghỉ trưa của ca → có ăn trưa."""
	if status not in LUNCH_ELIGIBLE_STATUS:
		return False
	return checkins_cover_lunch(day_datetimes, shift_lunch_window(shift))


def effective_lunch_flag(
	status: str | None,
	code: str | None,
	shift: str | None,
	day_datetimes,
	override: str | None = None,
) -> int:
	"""Cờ ăn trưa cuối cùng của MỘT ngày — nguồn luật duy nhất cho cả ba đường ghi (spec §5.4).

	Người chọn tay thì thắng tuyệt đối; còn lại suy từ trạng thái + mã công + dấu chấm."""
	if override == LUNCH_OVERRIDE_YES:
		return 1
	if override == LUNCH_OVERRIDE_NO:
		return 0

	if status not in LUNCH_ELIGIBLE_STATUS:
		return 0
	if (code or "") in NO_LUNCH_CODES:
		return 0

	punches = list(day_datetimes or [])
	lunch_start, lunch_end = shift_lunch_window(shift)
	if len(punches) >= MIN_PUNCHES_TO_DECIDE:
		return 1 if checkins_cover_lunch(punches, (lunch_start, lunch_end)) else 0

	# Dưới 2 dấu thì luật "phủ giờ nghỉ trưa" không kết luận được. KHÔNG mặc định có ăn cho mọi
	# trường hợp: một dấu duy nhất lúc 14:00 nghĩa là chiều mới tới, chắc chắn không ăn tại công ty.
	if status != "Present":
		return 0  # nửa ngày: không đủ bằng chứng đã ở lại qua trưa
	if not punches:
		return 1  # chấm tay / sửa qua soát công: đã công nhận ngày công đủ thì mặc định có ăn
	# Đúng một dấu: chỉ biết người đó CÓ MẶT lúc đó. Có mặt trước giờ nghỉ trưa → coi như ở lại ăn
	# (quên chấm ra); dấu duy nhất từ giờ trưa trở đi → đến muộn, không ăn.
	return 1 if _minutes(min(punches)) < lunch_start else 0


def day_punches(employee: str, attendance_date) -> list:
	"""Mọi dấu chấm công của NV trong đúng ngày đó, dạng datetime."""
	day = getdate(attendance_date)
	return [
		get_datetime(c.time)
		for c in frappe.get_all(
			"Employee Checkin",
			filters={"employee": employee, "time": ["between", [f"{day} 00:00:00", f"{day} 23:59:59"]]},
			fields=["time"],
		)
	]


def lunch_flag_for_attendance(
	employee: str,
	attendance_date,
	status: str | None,
	shift: str | None,
	code: str | None = None,
	override: str | None = None,
) -> bool:
	"""Cờ ăn trưa của MỘT Attendance — đọc dấu chấm của đúng ngày rồi áp ``effective_lunch_flag``.

	`code`/`override` mặc định None để mọi lời gọi cũ vẫn chạy: không mã thì không rơi vào loại trừ
	CT/W, không override thì đi nhánh tự động."""
	if override in (LUNCH_OVERRIDE_YES, LUNCH_OVERRIDE_NO):
		return override == LUNCH_OVERRIDE_YES  # khỏi truy vấn checkin: người đã quyết
	if status not in LUNCH_ELIGIBLE_STATUS:
		return False
	return bool(effective_lunch_flag(status, code, shift, day_punches(employee, attendance_date), override))


def compute_lunch_flags_for_period(month, year, company: str | None = None) -> dict:
	"""{attendance_name: 0/1} theo checkin cho cả kỳ — KHÔNG ghi DB (tính lại để làm mới cờ khi
	checkin về muộn). Tách riêng để test được cả trước khi field custom_lunch lên site."""
	start = getdate(f"{cint(year)}-{cint(month):02d}-01")
	end = get_last_day(start)
	filters = {"attendance_date": ["between", [start, end]], "docstatus": 1}
	if company:
		filters["company"] = company
	meta = frappe.get_meta("Attendance")
	fields = ["name", "employee", "attendance_date", "status", "shift"]
	# Mã công quyết định loại trừ CT/W; ô "Ăn trưa" là lựa chọn tay mà lượt tính lại KHÔNG được xoá.
	for optional in ("custom_attendance_code", "custom_lunch_override"):
		if meta.has_field(optional):
			fields.append(optional)

	flags = {}
	for a in frappe.get_all("Attendance", filters=filters, fields=fields):
		flags[a.name] = (
			1
			if lunch_flag_for_attendance(
				a.employee,
				a.attendance_date,
				a.status,
				a.shift,
				a.get("custom_attendance_code"),
				a.get("custom_lunch_override"),
			)
			else 0
		)
	return flags


@frappe.whitelist()
def recompute_lunch_flags(month: int | str, year: int | str, company: str | None = None) -> int:
	"""Tính lại cờ ``custom_lunch`` cho Attendance trong kỳ từ checkin (chạy trước khi chốt lương để
	bắt checkin về muộn). Trả số bản ghi thay đổi. Chỉ ghi field hiển thị (db_set, update_modified=False)
	→ không đụng payroll status. No-op nếu field chưa migrate."""
	if not frappe.get_meta("Attendance").has_field("custom_lunch"):
		return 0
	changed = 0
	for name, flag in compute_lunch_flags_for_period(month, year, company).items():
		if cint(frappe.db.get_value("Attendance", name, "custom_lunch")) != flag:
			frappe.db.set_value("Attendance", name, "custom_lunch", flag, update_modified=False)
			changed += 1
	return changed


def backfill_lunch_flags(dry_run: int = 1) -> dict:
	"""Đặt cờ ``custom_lunch`` cho MỌI Attendance đã submit từ checkin — chạy MỘT LẦN sau khi migrate
	field, CÓ SIGN-OFF (data-migration, không git-revert được). ``bench --site miyano execute
	hrms.vn_payroll.lunch.backfill_lunch_flags`` (mặc định dry_run — chỉ đếm, không ghi). Gọi lại với
	``--kwargs '{"dry_run": 0}'`` để ghi. Idempotent; chỉ ghi field hiển thị → payroll bất biến."""
	if not frappe.get_meta("Attendance").has_field("custom_lunch"):
		return {"error": "field custom_lunch chưa migrate", "changed": 0}
	dry = cint(dry_run)
	meta = frappe.get_meta("Attendance")
	fields = ["name", "employee", "attendance_date", "status", "shift", "custom_lunch"]
	for optional in ("custom_attendance_code", "custom_lunch_override"):
		if meta.has_field(optional):
			fields.append(optional)
	atts = frappe.get_all("Attendance", filters={"docstatus": 1}, fields=fields)
	to_change = 0
	for a in atts:
		flag = (
			1
			if lunch_flag_for_attendance(
				a.employee,
				a.attendance_date,
				a.status,
				a.shift,
				a.get("custom_attendance_code"),
				a.get("custom_lunch_override"),
			)
			else 0
		)
		if cint(a.custom_lunch) != flag:
			to_change += 1
			if not dry:
				frappe.db.set_value("Attendance", a.name, "custom_lunch", flag, update_modified=False)
	if not dry:
		commit_unless_test()
	return {"total": len(atts), "to_change": to_change, "written": 0 if dry else to_change, "dry_run": dry}


def lunch_days_for_period(employee: str, start_date, end_date) -> int:
	"""Số buổi ăn trưa trong kỳ = **Σ cờ ``custom_lunch``** (nguồn duy nhất — cùng số report/Bảng Công
	Tháng hiển thị). Trước khi field được migrate lên site, fallback sang ``count_lunch_days`` (quét
	checkin) để payroll không vỡ. Cùng luật per-ngày nên hai đường cho kết quả giống nhau."""
	if frappe.get_meta("Attendance").has_field("custom_lunch"):
		rows = frappe.get_all(
			"Attendance",
			filters={
				"employee": employee,
				"attendance_date": ["between", [start_date, end_date]],
				"docstatus": 1,
			},
			fields=["custom_lunch"],
		)
		return sum(cint(r.custom_lunch) for r in rows)
	return count_lunch_days(employee, start_date, end_date)


def lunch_days_map(employees, start_date, end_date) -> dict:
	"""{employee: số buổi ăn trưa} cho nhiều NV bằng **một** truy vấn gộp (thay vì gọi
	``lunch_days_for_period`` từng người trong report). Trước migrate: fallback quét checkin từng NV."""
	if not employees:
		return {}
	if frappe.get_meta("Attendance").has_field("custom_lunch"):
		rows = frappe.get_all(
			"Attendance",
			filters={
				"employee": ["in", list(employees)],
				"attendance_date": ["between", [start_date, end_date]],
				"docstatus": 1,
			},
			fields=["employee", "sum(custom_lunch) as lunch"],
			group_by="employee",
		)
		return {r.employee: cint(r.lunch) for r in rows}
	return {e: count_lunch_days(e, start_date, end_date) for e in employees}


def count_lunch_days(employee: str, start_date, end_date) -> int:
	# ngày công + ca của ngày đó (để lấy giờ nghỉ trưa theo ca)
	eligible = {
		getdate(a.attendance_date): a.shift
		for a in frappe.get_all(
			"Attendance",
			filters={
				"employee": employee,
				"attendance_date": ["between", [start_date, end_date]],
				"docstatus": 1,
				"status": ["in", LUNCH_ELIGIBLE_STATUS],
			},
			fields=["attendance_date", "shift"],
		)
	}
	if not eligible:
		return 0

	checkins = frappe.get_all(
		"Employee Checkin",
		filters={
			"employee": employee,
			"time": ["between", [f"{start_date} 00:00:00", f"{end_date} 23:59:59"]],
		},
		fields=["time"],
		order_by="time",
	)
	by_day = {}
	for c in checkins:
		dt = get_datetime(c.time)
		by_day.setdefault(dt.date(), []).append(dt)

	window_cache = {}
	count = 0
	for day, times in by_day.items():
		if getdate(day) not in eligible:
			continue
		shift = eligible[getdate(day)]
		if shift not in window_cache:
			window_cache[shift] = shift_lunch_window(shift)
		if checkins_cover_lunch(times, window_cache[shift]):
			count += 1
	return count
