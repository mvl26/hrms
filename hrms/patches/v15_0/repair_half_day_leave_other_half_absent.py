# Copyright (c) 2026, Miyano Việt Nam.
"""Sửa những ngày nghỉ nửa ngày theo đơn mà nửa còn lại bị ép thành Absent.

Lỗi gốc (đã sửa ở code, commit 30085e4): job chấm công hằng giờ `mark_absent_for_half_day_dates` ép
nửa còn lại của ngày nghỉ nửa buổi thành `half_day_status = Absent`, đồng thời tắt
`modify_half_day_status`. Nếu lượt chấm công của nửa kia về SAU lần chạy đó, nó đụng vào bản ghi đã
có, bị bật `skip_auto_attendance`, và ngày đó kẹt ở `working_hours = 0`. Kết quả: bảng công ghi
1/2P đủ công, nhưng payroll (`get_half_absent_days`) trừ thêm 0,5 ngày.

Quy ước HR 2026-07-28: nửa nghỉ theo đơn + nửa kia (dù có hay không có lượt chấm) = nửa kia đi làm.
Vì vậy patch:

1. đặt lại `half_day_status = Present` và `modify_half_day_status = 1` cho mọi ngày như vậy, để
   lượt chấm về sau còn gộp được vào ngày nghỉ;
2. gỡ `skip_auto_attendance` khỏi những lượt chấm chưa gắn Attendance của đúng ngày đó, để job hằng
   giờ kế tiếp gộp chúng vào (giờ vào/ra, giờ làm).

Bỏ qua ngày thuộc kỳ đã chốt Bảng Công Tháng: số liệu kỳ đó đã ký, phải mở lại bảng rồi chạy lại.

**Không `git revert` được** (sửa dữ liệu). Idempotent: chạy lại khi đã sạch là no-op.
Phiếu lương nháp phải lưu lại để tính lại; phiếu đã submit không bị đụng — patch in danh sách.
"""

import frappe
from frappe.query_builder.functions import Date


def damaged_days() -> list:
	return frappe.get_all(
		"Attendance",
		filters={
			"docstatus": 1,
			"status": "Half Day",
			"half_day_status": "Absent",
			"leave_type": ("is", "set"),
		},
		fields=["name", "employee", "attendance_date"],
		order_by="attendance_date, employee",
	)


def release_skipped_checkins(employee: str, attendance_date) -> int:
	EmployeeCheckin = frappe.qb.DocType("Employee Checkin")
	condition = (
		(EmployeeCheckin.employee == employee)
		& (EmployeeCheckin.skip_auto_attendance == 1)
		& (EmployeeCheckin.attendance.isnull() | (EmployeeCheckin.attendance == ""))
		& (Date(EmployeeCheckin.shift_start) == attendance_date)
	)
	count = frappe.qb.from_(EmployeeCheckin).select(EmployeeCheckin.name).where(condition).run()
	frappe.qb.update(EmployeeCheckin).set(EmployeeCheckin.skip_auto_attendance, 0).where(condition).run()
	return len(count)


def submitted_slips_covering(employee: str, attendance_date) -> list[str]:
	return frappe.get_all(
		"Salary Slip",
		filters={
			"employee": employee,
			"docstatus": 1,
			"start_date": ("<=", attendance_date),
			"end_date": (">=", attendance_date),
		},
		pluck="name",
	)


def execute():
	from hrms.hr.period_lock import is_period_locked

	fixed, locked, released, submitted = [], [], 0, set()
	for day in damaged_days():
		if is_period_locked(day.employee, day.attendance_date):
			locked.append(day.name)
			continue
		frappe.db.set_value(
			"Attendance",
			day.name,
			{"half_day_status": "Present", "modify_half_day_status": 1},
			update_modified=False,
		)
		released += release_skipped_checkins(day.employee, day.attendance_date)
		submitted.update(submitted_slips_covering(day.employee, day.attendance_date))
		fixed.append(day.name)

	if fixed or locked:
		print(f"repair_half_day_leave_other_half_absent: sửa {len(fixed)} ngày, gỡ skip {released} lượt chấm")
		if fixed:
			print("  đã sửa:", ", ".join(fixed))
		if locked:
			print("  BỎ QUA vì kỳ đã chốt (mở lại bảng công rồi chạy lại):", ", ".join(locked))
		if submitted:
			print(
				"  phiếu lương ĐÃ SUBMIT phủ các ngày này (cần điều chỉnh tay):", ", ".join(sorted(submitted))
			)
