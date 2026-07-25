# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# For license information, please see license.txt
"""Số ngày ăn trưa tại công ty — suy từ checkin, KHÁC số công.

Quy tắc (khớp công thức HR): một ngày tính ăn trưa khi ngày đó là ngày công (Present / Half Day) VÀ
dấu vào–ra phủ cả giờ nghỉ trưa — vào TRƯỚC giờ bắt đầu nghỉ trưa và ra TỪ giờ hết nghỉ trưa trở đi.
Giờ nghỉ trưa lấy từ Shift Type của ngày đó (`custom_lunch_start`/`custom_lunch_end`); nếu ca không
đặt thì dùng mặc định 12:00–13:30.
"""

import frappe
from frappe.utils import get_datetime, getdate

DEFAULT_LUNCH_START = 12 * 60  # 12:00 = 720 phút (hết ca sáng)
DEFAULT_LUNCH_END = 13 * 60 + 30  # 13:30 = 810 phút (vào ca chiều)
LUNCH_ELIGIBLE_STATUS = ("Present", "Half Day")


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
	"""(phút bắt đầu, phút kết thúc) giờ nghỉ trưa của ca; thiếu → mặc định 12:00–13:30."""
	if not shift:
		return DEFAULT_LUNCH_START, DEFAULT_LUNCH_END
	ls, le = frappe.db.get_value("Shift Type", shift, ["custom_lunch_start", "custom_lunch_end"]) or (
		None,
		None,
	)
	start = _td_minutes(ls)
	end = _td_minutes(le)
	return (
		start if start is not None else DEFAULT_LUNCH_START,
		end if end is not None else DEFAULT_LUNCH_END,
	)


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
		lunch_start, lunch_end = window_cache[shift]
		first, last = min(times), max(times)
		if _minutes(first) < lunch_start and _minutes(last) >= lunch_end:
			count += 1
	return count
