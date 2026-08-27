# Copyright (c) 2026, Miyano Việt Nam.
import frappe
from frappe import _
from frappe.model.document import Document


class AttendanceCode(Document):
	"""Mã công — NEO của toàn bộ tuyến chấm công VN.

	Mã quyết định ngày đó hiện ký hiệu gì, tính mấy công, và rơi vào cột nào của bảng công tháng.
	Loại nghỉ thì HR tạo bao nhiêu tuỳ ý, nhưng mỗi loại nghỉ phải có mã trỏ tới thì ngày nghỉ mới
	ra đúng công — xem `docs/spec/attendance-code-as-anchor.md`.
	"""

	def validate(self):
		self.validate_unique_leave_mapping()

	def validate_unique_leave_mapping(self):
		"""Một cặp (trạng thái, loại nghỉ) chỉ được đúng MỘT mã.

		Đây là bất biến HR yêu cầu ("1 code ứng 1 loại nghỉ"), và cũng là thứ khiến reverse-derive
		không bao giờ phải đoán: `_pick_reverse_code` nhận nhiều mã cùng khớp thì buộc phải chọn
		bừa, mà `W` (làm tại nhà) với `CT` (đi công tác) là ví dụ sống của hai mã KHÔNG thay thế
		được cho nhau.

		Mã KHÔNG có loại nghỉ (X, CT, W, V, 1/2X) nằm ngoài luật này — chúng phân biệt nhau bằng
		`CANONICAL_REVERSE_CODE` chứ không bằng loại nghỉ. Mã nghỉ CHƯA gắn loại nghỉ cũng hợp lệ:
		ô "Mã công cả ngày" trên form Loại nghỉ chọn một mã đã tồn tại, nên mã phải tạo được trước
		khi có ai trỏ tới nó.
		"""
		if not self.leave_type:
			return
		clash = frappe.db.exists(
			"Attendance Code",
			{
				"name": ("!=", self.name),
				"leave_type": self.leave_type,
				"maps_to_status": self.maps_to_status,
			},
		)
		if clash:
			frappe.throw(
				_(
					"Mã công {0} đã ứng với loại nghỉ {1} ở trạng thái {2}. Một cặp (trạng thái, "
					"loại nghỉ) chỉ được có đúng một mã — sửa hoặc gỡ mã kia trước."
				).format(frappe.bold(clash), frappe.bold(self.leave_type), frappe.bold(self.maps_to_status)),
				title=_("Trùng mã cho một loại nghỉ"),
			)
