# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt
"""Nhật ký điều chỉnh công — vết BẤT BIẾN của mọi lần HR sửa một ngày công ở bước soát.

Bước soát công cho phép HR đè lên kết quả máy chấm, mà những field bị đè (`status`,
`leave_type`, `half_day_status`) chính là thứ payroll đọc. Không có vết thì tháng sau không ai
trả lời được "vì sao ngày này thành nửa công". Nên mỗi lần sửa bắt buộc kèm lý do và đẻ ra đúng
một bản ghi ở đây, ghi cả giá trị trước lẫn sau.

Bản ghi KHÔNG sửa được sau khi tạo: sửa được thì nó không còn là vết nữa.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime


class AttendanceCorrectionLog(Document):
	def validate(self):
		if not self.is_new():
			frappe.throw(_("Nhật ký điều chỉnh công là vết kiểm toán — không sửa được sau khi tạo."))
		self.corrected_by = self.corrected_by or frappe.session.user
		self.corrected_on = self.corrected_on or now_datetime()

	def on_trash(self):
		if "System Manager" not in frappe.get_roles():
			frappe.throw(_("Chỉ System Manager mới xoá được nhật ký điều chỉnh công."))


def log_correction(attendance, before: dict, after: dict, reason: str) -> str:
	"""Ghi một vết điều chỉnh. `before`/`after` là dict các field payroll + mã công."""
	doc = frappe.get_doc(
		{
			"doctype": "Attendance Correction Log",
			"attendance": attendance.name,
			"employee": attendance.employee,
			"attendance_date": attendance.attendance_date,
			"old_code": before.get("custom_attendance_code"),
			"new_code": after.get("custom_attendance_code"),
			"old_status": before.get("status"),
			"new_status": after.get("status"),
			"old_leave_type": before.get("leave_type"),
			"new_leave_type": after.get("leave_type"),
			"old_half_day_status": before.get("half_day_status"),
			"new_half_day_status": after.get("half_day_status"),
			"reason": reason,
		}
	)
	doc.insert(ignore_permissions=True)
	return doc.name
