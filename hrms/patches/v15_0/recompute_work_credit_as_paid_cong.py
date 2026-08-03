"""Tính lại field hiển thị "Công" (`custom_work_credit`) theo nghĩa MỚI: công DOANH NGHIỆP TRẢ.

Trước đây field mang `work_fraction` — công ĐI LÀM thực tế — nên một ngày nghỉ phép năm hiện
**Công = 0** dù công ty trả đủ lương ngày đó, và cùng số 0 ấy gộp ba nhóm khác hẳn nhau: nghỉ công
ty trả (P/KH/R1/R2/NB/T), nghỉ BHXH chi trả (Ô/Cô/TS) và không ai trả (K/V).

Nghĩa mới khớp đúng cột "Tổng công" của bảng chấm công tháng — dùng chung `paid_credit`, không chép
luật sang đây.

Chỉ ghi MỘT field hiển thị; không đụng `status` / `leave_type` / `half_day_status` (những field duy
nhất payroll đọc) nên lương bất biến. Idempotent: chạy lại chỉ đụng những dòng còn lệch.
"""

import frappe
from frappe.utils import flt

from hrms.hr.report.monthly_attendance_report.monthly_attendance_report import paid_credit


def execute():
	recompute()


def recompute(dry_run: bool = False) -> dict:
	"""Đặt lại custom_work_credit = công doanh nghiệp trả. Trả {(sáng, chiều): số dòng đã sửa}."""
	if not frappe.db.has_column("Attendance", "custom_work_credit"):
		return {}

	codes = {
		c.name: c
		for c in frappe.get_all("Attendance Code", fields=["name", "category", "work_fraction", "is_paid"])
	}

	rows = frappe.db.sql(
		"""select name, custom_attendance_code, custom_morning_code, custom_afternoon_code,
				  custom_work_credit
		   from `tabAttendance`
		   where docstatus < 2
			 and coalesce(custom_attendance_code, custom_morning_code, custom_afternoon_code) is not null""",
		as_dict=True,
	)

	changed = {}
	for r in rows:
		morning = codes.get(r.custom_morning_code or r.custom_attendance_code)
		afternoon = codes.get(r.custom_afternoon_code or r.custom_attendance_code)
		if not (morning and afternoon):
			continue  # mã lạ (đã xoá khỏi master) — để nguyên, không đoán
		credit = sum(paid_credit(c) * 0.5 for c in (morning, afternoon))
		if flt(r.custom_work_credit) == flt(credit):
			continue
		key = (morning.name, afternoon.name)
		changed[key] = changed.get(key, 0) + 1
		if not dry_run:
			frappe.db.set_value("Attendance", r.name, "custom_work_credit", credit, update_modified=False)

	return changed
