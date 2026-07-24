# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt
"""Miyano — gộp một quỹ phép năm.

Nghỉ có lương thuộc nhóm "trừ quỹ" (Phép/Ốm/Chăm con ốm) nộp qua Đơn xin nghỉ với
``leave_type = "Nghỉ phép năm"`` để cùng rút một số dư (Frappe tự chặn khi hết). Đơn mang thêm
``custom_attendance_code`` (mã lý do) — sau khi duyệt sinh Attendance, hook ghi mã đó lên Attendance
để bảng công hiện Ô/Cô/P riêng. Thuần hiển thị: không đổi status/leave_type/half_day_status → lương
bất biến. TS/N/T miễn trừ (loại nghỉ riêng); K không lương.
"""

import frappe

POOL_LEAVE_TYPE = "Nghỉ phép năm"
# Các mã hợp lệ cho đơn rút quỹ phép năm (P + nửa ngày P, Ốm, Chăm con ốm)
DEDUCTING_CODES = {"P", "1/2P", "Ô", "Cô"}


def validate_pool_code(doc, method=None):
	"""Đơn rút quỹ phép năm phải chọn Mã chấm công hợp lệ (P/Ô/Cô…). Bỏ qua loại nghỉ khác."""
	if doc.get("leave_type") != POOL_LEAVE_TYPE:
		return
	code = doc.get("custom_attendance_code")
	if code not in DEDUCTING_CODES:
		frappe.throw(
			frappe._("Nghỉ rút quỹ phép năm phải chọn Mã chấm công hợp lệ ({0}).").format(
				", ".join(sorted(DEDUCTING_CODES))
			)
		)


def set_leave_attendance_code(doc, method=None):
	"""Sau khi Đơn xin nghỉ duyệt sinh Attendance (upstream ``update_attendance``), ghi mã lý do lên
	Attendance để bảng công hiện đúng. THUẦN HIỂN THỊ: chỉ đặt ``custom_attendance_code`` bằng
	``db_set`` — không đụng status/leave_type/half_day_status nên lương không đổi."""
	code = doc.get("custom_attendance_code")
	if not code:
		return
	for name in frappe.get_all(
		"Attendance",
		filters={"leave_application": doc.name, "docstatus": ["<", 2]},
		pluck="name",
	):
		frappe.db.set_value("Attendance", name, "custom_attendance_code", code, update_modified=False)
