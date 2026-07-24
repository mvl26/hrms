# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# For license information, please see license.txt
"""Số ngày ăn trưa tại công ty — suy từ checkin, KHÁC số công.

Quy tắc (khớp công thức HR dùng trên bảng chấm công): một ngày tính ăn trưa khi ngày đó là ngày công
(Present / Half Day) VÀ dấu vào–ra phủ cả buổi sáng lẫn chiều — vào TRƯỚC 12:00 và ra TỪ 13:30 trở đi
(tức có mặt qua giờ nghỉ trưa). Ngày chỉ làm sáng (ra trước 13:30) hoặc chỉ làm chiều (vào từ 12:00)
không tính ăn trưa.
"""

import frappe
from frappe.utils import get_datetime, getdate

MORNING_END = 12 * 60  # 12:00 = 720 phút
AFTERNOON_START = 13 * 60 + 30  # 13:30 = 810 phút
LUNCH_ELIGIBLE_STATUS = ("Present", "Half Day")


def _minutes(dt) -> int:
	return dt.hour * 60 + dt.minute


def count_lunch_days(employee: str, start_date, end_date) -> int:
	eligible = {
		getdate(a.attendance_date)
		for a in frappe.get_all(
			"Attendance",
			filters={
				"employee": employee,
				"attendance_date": ["between", [start_date, end_date]],
				"docstatus": 1,
				"status": ["in", LUNCH_ELIGIBLE_STATUS],
			},
			fields=["attendance_date"],
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

	count = 0
	for day, times in by_day.items():
		if getdate(day) not in eligible:
			continue
		first, last = min(times), max(times)
		if _minutes(first) < MORNING_END and _minutes(last) >= AFTERNOON_START:
			count += 1
	return count
