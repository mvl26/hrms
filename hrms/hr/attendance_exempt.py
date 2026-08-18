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

import frappe
from frappe.utils import cint, getdate

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


def exempt_employees() -> list:
	"""Mọi nhân viên đang làm việc có bật cờ miễn chấm công."""
	if not exempt_fields_installed():
		return []
	return frappe.get_all(
		"Employee",
		filters={"status": "Active", "custom_exempt_from_checkin": 1},
		fields=EMPLOYEE_FIELDS,
	)
