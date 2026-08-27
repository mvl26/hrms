# Copyright (c) 2026, Miyano Việt Nam.
"""Miyano — nhân viên MIỄN CHẤM CÔNG: ngày làm việc tự sinh đủ công.

Một số người (giám đốc, người có giờ làm không cố định) không quẹt thẻ, nhưng công của họ là công
khoán theo tháng. Không có module này thì `mark_absent_for_dates_with_no_attendance` chấm họ VẮNG cả
tháng và `payment_days` bị trừ sạch.

Module giữ TOÀN BỘ luật; các điểm móc trong shift_type / attendance / business_trip chỉ gọi vào đây.
Ngày tự sinh ghi bằng MÃ CÔNG (`X`) — `status` / `leave_type` / `custom_work_credit` do cầu nối
`Attendance.apply_attendance_code_bridge` suy ra, không đặt tay (một nguồn sự thật).

Xem `docs/spec/attendance-exempt-employees.md`.
"""

from datetime import datetime

import frappe
from frappe import _
from frappe.utils import add_days, cint, get_last_day, getdate

from erpnext.setup.doctype.employee.employee import is_holiday

EXEMPT_CODE = "X"
# Cửa sổ lùi tối đa của lượt quét tự động — CHỐT CHẶN CHI PHÍ, không phải luật nghiệp vụ: bật cờ cho
# người vào làm từ 2020 mà không giới hạn thì mỗi giờ job lại cày sáu năm lịch sử. Bù xa hơn thì
# dùng `generate_for_month`.
BACKFILL_DAYS = 31

EMPLOYEE_FIELDS = [
	"name",
	"status",
	"company",
	"default_shift",
	"date_of_joining",
	"relieving_date",
	"custom_exempt_from_checkin",
	"custom_exempt_from_checkin_from",
]


def exempt_fields_installed() -> bool:
	"""Fixtures đã lên site chưa. Chưa thì mọi thứ im lặng và hành vi cũ y nguyên — cùng khuôn
	phòng thủ với `Attendance.get_split_shift_config`."""
	return frappe.get_meta("Employee").has_field("custom_exempt_from_checkin")


def is_exempt(employee: str, date) -> bool:
	"""Nhân viên này có được miễn chấm công vào NGÀY này không."""
	if not employee or not exempt_fields_installed():
		return False
	row = frappe.db.get_value("Employee", employee, EMPLOYEE_FIELDS, as_dict=True)
	if not row or not cint(row.custom_exempt_from_checkin) or row.status != "Active":
		return False
	date = getdate(date)
	start = row.custom_exempt_from_checkin_from or row.date_of_joining
	if start and date < getdate(start):
		return False
	if row.relieving_date and date > getdate(row.relieving_date):
		return False
	return True


def is_exempt_working_day(employee: str, date) -> bool:
	"""Ngày mà luật miễn chấm công được áp: có cờ VÀ là ngày làm việc.

	Ngày nghỉ (T7/CN/lễ) KHÔNG thuộc "full công hàng tháng" — cả công ty đều nghỉ. Ca có bật
	`mark_auto_attendance_on_holidays` mà ép X ở đây thì chấm 10 phút ngày lễ cũng thành đủ công,
	và trên cấu hình trả lương ngày lễ là cộng dư. Ngày nghỉ đi đúng luật chung như mọi người."""
	return is_exempt(employee, date) and not is_holiday(employee, date, raise_exception=False)


def exempt_employees() -> list:
	"""Mọi nhân viên đang làm việc có bật cờ miễn chấm công."""
	if not exempt_fields_installed():
		return []
	return frappe.get_all(
		"Employee",
		filters={"status": "Active", "custom_exempt_from_checkin": 1},
		fields=EMPLOYEE_FIELDS,
	)


# Ngày do một kênh CÓ CHỦ Ý ghi thì không được đụng: mọi mã nghỉ đều có `leave_type`, còn công tác
# (CT) và làm việc ở nhà / từ xa (W) mang status "Work From Home". Ba mã còn lại — X, 1/2X, V — đều
# do LƯỢT CHẤM suy ra, và với người không quẹt thẻ thì chúng chính là thứ sai cần sửa.
PROTECTED_STATUSES = ("On Leave", "Work From Home")

REPAIR_FIELDS = [
	"name",
	"status",
	"leave_type",
	"leave_application",
	"attendance_request",
	"custom_attendance_code",
	"in_time",
	"out_time",
]


def existing_day(employee: str, date):
	return frappe.db.get_value(
		"Attendance",
		{"employee": employee, "attendance_date": getdate(date), "docstatus": ["<", 2]},
		REPAIR_FIELDS,
		as_dict=True,
	)


def is_protected_day(row) -> bool:
	"""Ngày này đã được ghi có chủ ý (nghỉ phép, công tác, WFH/từ xa, yêu cầu chấm công) chưa."""
	if not row:
		return False
	if row.get("leave_type") or row.get("leave_application") or row.get("attendance_request"):
		return True
	return row.get("status") in PROTECTED_STATUSES


def pending_checkins(employee: str, date, row) -> list:
	"""Lượt chấm của ngày này chưa gắn vào ngày công nào — CHỈ ĐỌC.

	Một chỗ duy nhất truy vấn lượt chấm chưa gắn: `plan_day` (xem trước) và `attach_late_checkins`
	(lúc ghi) đều hỏi qua đây, nếu không hai bên sẽ đếm theo hai luật khác nhau."""
	if row.get("in_time") or row.get("out_time"):
		return []
	day = getdate(date)
	return frappe.get_all(
		"Employee Checkin",
		filters={
			"employee": employee,
			"attendance": ("is", "not set"),
			"time": ("between", [f"{day} 00:00:00", f"{day} 23:59:59"]),
		},
		fields=["name", "time"],
		order_by="time",
	)


def plan_day(employee: str, date) -> frappe._dict:
	"""QUYẾT ĐỊNH sẽ làm gì với một ngày — thuần đọc, không ghi.

	Nguồn luật DUY NHẤT cho cả xem trước lẫn lúc ghi, nên hai bên không thể hứa một đằng làm một nẻo.
	`action` ∈ create / repair / attach / skip; `reason` giải thích vì sao bỏ qua (xem spec §3.6).
	"""
	from hrms.hr.doctype.attendance_request.attendance_request_miyano import approved_request_for
	from hrms.hr.period_lock import is_period_locked

	date = getdate(date)
	out = frappe._dict(
		action="skip", reason=None, code_cu=None, attendance=None, date=date, employee=employee
	)
	if not is_exempt(employee, date):
		out.reason = "not_exempt"
		return out
	if is_holiday(employee, date, raise_exception=False):
		out.reason = "rest_day"  # T7/CN/lễ: không ai có công, kể cả người miễn chấm công
		return out
	if is_period_locked(employee, date):
		out.reason = "locked"  # kỳ đã chốt là đóng băng
		return out

	row = existing_day(employee, date)
	if row:
		out.attendance = row.name
		out.code_cu = row.custom_attendance_code
		if is_protected_day(row):
			if row.get("attendance_request"):
				out.reason = "request"
			elif row.get("status") == "Work From Home":
				out.reason = "trip_wfh"
			else:
				out.reason = "leave"
			return out
		if row.custom_attendance_code == EXEMPT_CODE and row.status == "Present":
			if pending_checkins(employee, date, row):
				out.action = "attach"  # ngày đúng rồi, chỉ thiếu giờ vào/ra
			else:
				out.reason = "ok"
			return out
		out.action = "repair"
		return out

	if approved_request_for(employee, date):
		out.reason = "request"  # đơn đã duyệt dựng lại ngày công theo đơn — đơn thắng
		return out
	out.action = "create"
	return out


def ensure_full_day(employee: str, date) -> str | None:
	"""Bảo đảm ngày làm việc của người miễn chấm công là ĐỦ CÔNG (mã X) = `plan_day` + thực thi.

	Trả tên Attendance nếu có tạo/sửa/ghi giờ, None nếu không cần đụng.
	"""
	from hrms.hr.doctype.attendance_request.attendance_request_miyano import reapply_attendance_request

	date = getdate(date)
	plan = plan_day(employee, date)
	if plan.action == "skip":
		return None
	if plan.action in ("attach", "repair"):
		row = existing_day(employee, date)
		attached = attach_late_checkins(row, employee, date)
		if plan.action == "attach":
			return row.name if attached else None
		return repair_day(row)

	if reapply_attendance_request(employee, date):
		return None  # đơn vừa dựng lại ngày công (plan_day chỉ đọc nên không làm được việc này)
	return create_full_day(employee, date)


def create_full_day(employee: str, date) -> str:
	"""Tạo MỚI một ngày công đủ (mã X) — cầu nối mã công suy ra status/work_credit."""
	emp = frappe.db.get_value("Employee", employee, ["company", "default_shift"], as_dict=True)
	doc = frappe.get_doc(
		{
			"doctype": "Attendance",
			"employee": employee,
			"attendance_date": getdate(date),
			"company": emp.company,
			"shift": emp.default_shift,
			"custom_attendance_code": EXEMPT_CODE,
			"custom_auto_filled": 1,
		}
	)
	doc.flags.ignore_permissions = True
	doc.insert(ignore_permissions=True)
	doc.submit()
	doc.add_comment("Comment", _("Tự sinh: nhân viên miễn chấm công (full công)"))
	return doc.name


def repair_day(row) -> str:
	"""Lật một ngày sai (V / 1/2X / …) về đủ công, GIỮ NGUYÊN giờ vào/ra thật.

	Dùng `db_set` vì bản ghi đã submit mà không field mã công nào có `allow_on_submit` — đúng khuôn
	`leave_application.create_or_update_attendance` và `business_trip.convert_auto_filled_to_trip`.
	"""
	doc = frappe.get_doc("Attendance", row.name)
	cu = 1 if not (row.get("in_time") or row.get("out_time")) else 0
	doc.db_set(
		{
			"status": "Present",
			"custom_attendance_code": EXEMPT_CODE,
			"custom_work_credit": 1.0,
			"half_day_status": None,
			"custom_auto_filled": cu,
		}
	)
	doc.add_comment(
		"Comment",
		_("Sửa về đủ công: nhân viên miễn chấm công (mã cũ {0}).").format(
			row.get("custom_attendance_code") or _("trống")
		),
	)
	return doc.name


def attach_late_checkins(row, employee: str, date) -> bool:
	"""Gắn lượt chấm VỀ SAU vào ngày công đã tự sinh: ghi giờ vào/ra + link log. Trả True nếu có ghi.

	`mark_attendance_and_link_log` bỏ qua ngày đã có bản ghi, nên lượt chấm về sau ngày tự sinh sẽ
	không bao giờ được ghi: báo cáo giờ làm hiện 0 cho ngày người ta thật sự có mặt, và lượt chấm
	nằm mãi ở trạng thái chưa gắn nên lần nào chạy auto-attendance cũng đụng lại. Mã công KHÔNG đổi
	(vẫn đủ công) — đây thuần là dữ liệu giờ.
	"""
	logs = pending_checkins(employee, date, row)
	if not logs:
		return False

	doc = frappe.get_doc("Attendance", row.name)
	in_time, out_time = logs[0].time, logs[-1].time
	doc.db_set(
		{"in_time": in_time, "out_time": out_time, "working_hours": worked_hours(doc, in_time, out_time)}
	)
	for log in logs:
		frappe.db.set_value("Employee Checkin", log.name, "attendance", row.name)
	return True


def worked_hours(doc, in_time, out_time) -> float:
	"""Giờ làm thật của một ngày, trừ nghỉ trưa — dùng chính bộ phân loại VN để không đẻ công thức thứ hai."""
	from frappe.utils import get_datetime

	from hrms.hr.doctype.attendance.vn_day_classifier import classify_day, resolve_lunch_window

	cfg = doc.get_split_shift_config()
	if not cfg:
		return round((get_datetime(out_time) - get_datetime(in_time)).total_seconds() / 3600, 2)
	lunch_start, lunch_end = resolve_lunch_window(cfg.custom_lunch_start, cfg.custom_lunch_end)
	return classify_day(
		get_datetime(in_time),
		get_datetime(out_time),
		day=datetime.combine(getdate(doc.attendance_date), datetime.min.time()),
		start_time=cfg.start_time,
		end_time=cfg.end_time,
		lunch_start=lunch_start,
		lunch_end=lunch_end,
		flexible=bool(cint(cfg.get("custom_flexible_shift"))),
		band_minutes=cint(cfg.get("custom_flex_band_minutes") or 180),
		min_work_hours=float(cfg.get("custom_min_work_hours") or 8.0),
	).hours


def ensure_exempt_days(employee: str, start_date, end_date) -> int:
	"""Rà một khoảng ngày cho MỘT người miễn chấm công. Trả số ngày đã tạo/sửa."""
	if not start_date or not end_date or not is_exempt(employee, end_date):
		return 0
	day, stop, n = getdate(start_date), getdate(end_date), 0
	while day <= stop:
		if ensure_full_day(employee, day):
			n += 1
		day = add_days(day, 1)
	return n


def process_exempt_employees():
	"""Scheduler `hourly_long`: lấp đầy ngày công cho MỌI người có cờ, kể cả người không được phân
	ca tháng đó (phân ca ở Miyano cấp theo từng tháng, quên là mất công cả tháng)."""
	if not exempt_fields_installed():
		return
	end = add_days(getdate(), -1)  # hôm nay chưa hết thì chưa kết luận
	floor = add_days(end, -BACKFILL_DAYS)
	for emp in exempt_employees():
		start = getdate(emp.custom_exempt_from_checkin_from or emp.date_of_joining or floor)
		if start < floor:
			start = floor
		stop = end
		if emp.relieving_date and getdate(emp.relieving_date) < stop:
			stop = getdate(emp.relieving_date)
		day = start
		while day <= stop:
			ensure_full_day(emp.name, day)
			day = add_days(day, 1)
		# giữ tiến độ giữa các nhân viên, y như `process_auto_attendance`
		frappe.db.commit()  # nosemgrep


# Ngày bị chừa ra vì lý do NÀY thì phải báo cho người dùng thấy — im lặng bỏ qua chính là thứ làm
# nút cũ trông như hỏng. Còn `ok` / `rest_day` / `not_exempt` là nhiễu, không nhồi vào bảng.
REPORTED_SKIPS = ("leave", "trip_wfh", "request", "locked")


def plan_month(month, year, employee: str | None = None) -> list:
	"""Kế hoạch cho cả tháng — thuần đọc. Không đụng ngày hôm nay và tương lai."""
	start = getdate(f"{cint(year)}-{cint(month):02d}-01")
	end = min(get_last_day(start), add_days(getdate(), -1))
	rows = [frappe._dict(name=employee)] if employee else exempt_employees()
	plans = []
	for emp in rows:
		day = start
		while day <= end:
			plans.append(plan_day(emp.name, day))
			day = add_days(day, 1)
	return plans


def as_result(plans: list) -> dict:
	"""Gom kế hoạch thành {rows, summary} — cùng một cấu trúc cho xem trước và cho lúc ghi."""
	summary = {"create": 0, "repair": 0, "attach": 0, "skip": 0}
	rows = []
	for p in plans:
		summary[p.action] += 1
		if p.action != "skip" or p.reason in REPORTED_SKIPS:
			rows.append(
				{
					"employee": p.employee,
					"employee_name": frappe.db.get_value("Employee", p.employee, "employee_name"),
					"date": str(p.date),
					"action": p.action,
					"reason": p.reason,
					"code_cu": p.code_cu,
				}
			)
	return {"rows": rows, "summary": summary}


@frappe.whitelist()
def preview_month(month, year, employee: str | None = None) -> dict:
	"""Xem trước việc sẽ làm — KHÔNG ghi một dòng nào."""
	frappe.only_for(("HR Manager", "System Manager"))
	return as_result(plan_month(month, year, employee))


@frappe.whitelist()
def generate_for_month(month, year, employee: str | None = None) -> dict:
	"""Chạy bù cả tháng. Trả CÙNG cấu trúc với `preview_month` để đối chiếu được với bản xem trước.

	Dùng khi bật cờ giữa chừng, sau khi huỷ chốt kỳ, hoặc muốn chạy ngay lúc soát công thay vì đợi
	lượt quét đầu giờ sau. Việc thường ngày đã có `process_exempt_employees` lo."""
	frappe.only_for(("HR Manager", "System Manager"))
	plans = plan_month(month, year, employee)
	for p in plans:
		if p.action != "skip":
			ensure_full_day(p.employee, p.date)
	return as_result(plans)
