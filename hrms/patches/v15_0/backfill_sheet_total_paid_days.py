"""Điền cột "Tổng công" (`total_paid_days`) cho các Bảng Công Tháng đã lập trước khi có cột này.

Bảng cũ chỉ có "Công đi làm" — không cộng ngày nghỉ CÓ LƯƠNG nên nhìn vào tưởng công ty không trả
ngày phép. Cột mới lấy đúng con số của báo cáo chấm công tháng (`get_sheet_rows` → "Tổng công"),
tức cùng nguồn suy diễn mà chính bảng dùng để chụp ảnh.

Chỉ ghi MỘT field hiển thị của dòng chi tiết; không đụng Attendance và không đụng
`status`/`leave_type`/`half_day_status` → lương bất biến. Cổng đối soát lương (`sheet_gate`) vốn
tính lại số công trực tiếp từ `get_sheet_rows` chứ không đọc field này, nên nó cũng không đổi.

Bảng ĐÃ CHỐT vẫn được điền: kỳ đã khoá thì `populate_from_attendance` từ chối chạy, mà để trống thì
bảng đã ký lại thiếu đúng con số quan trọng nhất. Idempotent: chỉ đụng dòng còn lệch.
"""

import frappe
from frappe.utils import flt

from hrms.hr.report.monthly_attendance_report.monthly_attendance_report import (
	TOTAL_PAID,
	get_sheet_rows,
)


def execute():
	backfill()


def backfill(dry_run: bool = False) -> dict:
	"""Điền total_paid_days cho mọi bảng chưa huỷ. Trả {tên bảng: số dòng đã sửa}."""
	if not frappe.db.has_column("Monthly Attendance Sheet Detail", "total_paid_days"):
		return {}

	result = {}
	for sheet in frappe.get_all(
		"Monthly Attendance Sheet",
		filters={"docstatus": ["<", 2]},
		fields=["name", "month", "year", "company", "department", "include_company_descendants"],
	):
		filters = frappe._dict(
			month=sheet.month,
			year=sheet.year,
			company=sheet.company,
			include_company_descendants=sheet.include_company_descendants,
		)
		if sheet.department:
			filters.department = sheet.department
		paid_by_emp = {r["employee"]: flt(r["totals"].get(TOTAL_PAID)) for r in get_sheet_rows(filters)}

		n = 0
		for row in frappe.get_all(
			"Monthly Attendance Sheet Detail",
			filters={"parent": sheet.name, "parenttype": "Monthly Attendance Sheet"},
			fields=["name", "employee", "total_paid_days"],
		):
			want = paid_by_emp.get(row.employee)
			if want is None or flt(row.total_paid_days) == want:
				continue
			n += 1
			if not dry_run:
				frappe.db.set_value(
					"Monthly Attendance Sheet Detail",
					row.name,
					"total_paid_days",
					want,
					update_modified=False,
				)
		if n:
			result[sheet.name] = n
	return result
