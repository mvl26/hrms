# Copyright (c) 2026, Miyano Việt Nam.
"""Sửa những ngày nghỉ nửa ngày theo đơn mà nửa còn lại bị ép thành Absent.

Lỗi gốc (đã sửa ở code, commit 30085e4): job chấm công hằng giờ `mark_absent_for_half_day_dates` ép
nửa còn lại của ngày nghỉ nửa buổi thành `half_day_status = Absent`, đồng thời tắt
`modify_half_day_status`. Nếu lượt chấm công của nửa kia về SAU lần chạy đó, nó đụng vào bản ghi đã
có, bị bật `skip_auto_attendance`, và ngày đó kẹt ở `working_hours = 0`. Kết quả: bảng công ghi
1/2P đủ công, nhưng payroll (`get_half_absent_days`) trừ thêm 0,5 ngày.

Lỗi gốc thứ hai (sửa 2026-11-03 ở `mark_attendance_and_link_log`): lượt chấm của nửa kia CÓ gộp vào,
nhưng giờ làm dưới ngưỡng vắng của ca (ngưỡng cho cả ngày) nên nửa kia bị ghi Absent — vd 09:10 →
13:23 = 2,8h. Cùng hệ quả: Công 1, phiếu lương 0,5.

Quy ước HR 2026-07-28: nửa nghỉ theo đơn + nửa kia (dù có hay không có lượt chấm) = nửa kia đi làm.
Vì vậy patch:

1. với ngày mang mã nửa-ngày-nghỉ (1/2P, 1/2K…), đặt lại `half_day_status = Present`; chỉ khi ngày đó
   còn lượt chấm bị skip mới mở `modify_half_day_status = 1` để lượt chấm gộp được vào ngày nghỉ;
2. gỡ `skip_auto_attendance` khỏi những lượt chấm chưa gắn Attendance của đúng ngày đó, để job hằng
   giờ kế tiếp gộp chúng vào (giờ vào/ra, giờ làm).

Bỏ qua ngày thuộc kỳ đã chốt Bảng Công Tháng: số liệu kỳ đó đã ký, phải mở lại bảng rồi chạy lại.

**Không `git revert` được** (sửa dữ liệu). Idempotent: chạy lại khi đã sạch là no-op.
Phiếu lương nháp phải lưu lại để tính lại; phiếu đã submit không bị đụng — patch in danh sách.
"""

import frappe
from frappe.query_builder.functions import Date


def half_leave_codes() -> list[str]:
	"""Mã MỘT nửa ngày nghỉ (1/2P, 1/2K…): theo định nghĩa nửa kia đi làm."""
	return frappe.get_all(
		"Attendance Code", {"maps_to_status": "Half Day", "leave_type": ("is", "set")}, pluck="name"
	)


def damaged_days() -> list:
	"""Chỉ ngày MANG mã nửa-ngày-nghỉ (Công tính đủ nửa kia) mà payroll vẫn trừ nửa kia. Ngày ghi tách
	nửa nghỉ / V là nửa vắng THẬT — đúng là Absent, không đụng."""
	codes = half_leave_codes()
	if not codes:
		return []
	return frappe.get_all(
		"Attendance",
		filters={
			"docstatus": 1,
			"status": "Half Day",
			"half_day_status": "Absent",
			"leave_type": ("is", "set"),
			"custom_attendance_code": ("in", codes),
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
		freed = release_skipped_checkins(day.employee, day.attendance_date)
		updates = {"half_day_status": "Present"}
		if freed:
			# còn lượt chấm bị skip chưa gộp → mở cờ để job gộp vào. Ngày đã gộp xong thì KHÔNG mở:
			# cờ này là đúng thứ job đánh vắng bản cũ (trước 30085e4) nhắm vào — server còn chạy code cũ
			# hoặc chưa restart sẽ ép Absent lại ở lần auto-attendance kế tiếp.
			updates["modify_half_day_status"] = 1
		frappe.db.set_value("Attendance", day.name, updates, update_modified=False)
		released += freed
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
