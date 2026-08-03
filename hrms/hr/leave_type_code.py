# Copyright (c) 2026, Miyano Việt Nam.
"""Miyano — gắn mã công cho Loại nghỉ ngay tại form Loại nghỉ.

**Vì sao cần:** cầu nối mã công tra ngược qua ``Attendance Code.leave_type``. Tạo một Loại nghỉ mới
mà quên tạo mã tương ứng thì ngày nghỉ đó không suy ra được mã, bảng chấm công hiển thị sai (đây
chính là gốc của sự cố "nghỉ phép có lương mà hiện V"). Ô này đưa việc gắn mã lên đúng lúc người
dùng tạo Loại nghỉ, thay vì bắt họ nhớ sang một doctype khác.

**Nguồn sự thật vẫn là ``Attendance Code.leave_type``**, không phải ô này. Lý do: một Loại nghỉ ứng
với NHIỀU mã — ``P`` và ``1/2P`` cùng trỏ "Nghỉ phép năm", ``K`` và ``1/2K`` cùng trỏ "Nghỉ không
lương" — phân biệt bằng ``maps_to_status``. Một ô đơn không chứa nổi cặp cả-ngày/nửa-ngày, nên ô này
chỉ là **mặt bàn để nhập**: lưu Loại nghỉ thì ghi ngược vào mã. Mã nửa ngày vẫn quản ở Attendance Code.

Sửa MASTER DATA, tuyệt đối không đụng ngày công đã ghi — muốn nắn dữ liệu cũ thì dùng nút Đồng bộ
mã công trên báo cáo chấm công tháng (`hrms/hr/attendance_code_sync.py`).
"""

import frappe
from frappe import _

FIELD = "custom_attendance_code"
LEAVE_STATUSES = ("On Leave", "Half Day")


def full_day_code_for(leave_type):
	"""Mã công CẢ NGÀY đang trỏ tới Loại nghỉ này, hoặc None."""
	if not leave_type:
		return None
	codes = frappe.get_all(
		"Attendance Code",
		filters={"leave_type": leave_type, "maps_to_status": "On Leave"},
		pluck="name",
	)
	return sorted(codes)[0] if codes else None


def sync_code_to_leave_type(doc, method=None):
	"""Ghi ngược ô "Mã công" của Loại nghỉ vào ``Attendance Code.leave_type``.

	Gọi được với Document thật hoặc doc-like ``frappe._dict(name=..., custom_attendance_code=...)``.
	Chỉ chạm bảng Attendance Code — không đụng Attendance nào."""
	leave_type = doc.get("name")
	if not leave_type:
		return

	# Site CHƯA migrate custom field: `doc.get(FIELD)` trả None cho mọi Loại nghỉ, và nếu cứ chạy
	# tiếp thì vòng dọn bên dưới sẽ XOÁ SẠCH map hiện có. Chỉ bỏ qua với Document thật — doc-like
	# dict trong test luôn mang field một cách tường minh.
	if not isinstance(doc, dict) and not frappe.get_meta("Leave Type").has_field(FIELD):
		return

	code = doc.get(FIELD)

	# Ô TRỐNG = "không nhập gì", KHÔNG phải "gỡ mã". Ô này chỉ là mặt bàn để nhập nên nó rỗng ở
	# mọi lần lưu không đi qua form: sửa Loại nghỉ bằng script, `bench execute`, hay chính người
	# dùng bấm Save trước khi kịp chọn mã. Trước đây vòng dọn bên dưới vẫn chạy trong tình huống
	# đó và XOÁ `Attendance Code.leave_type` — mã nghỉ mất đường tra ngược, bảng chấm công hiện
	# sai (P thành V). Sự cố có thật: lưu lại 10 Loại nghỉ ngày 2026-08-03 đã gỡ liên kết của
	# T/KH/R1/R2. Muốn gỡ thật thì sửa ở Attendance Code — nơi giữ nguồn sự thật.
	if not code:
		return

	status = frappe.db.get_value("Attendance Code", code, "maps_to_status")
	if status not in LEAVE_STATUSES:
		frappe.throw(
			_(
				"Mã công {0} không phải mã nghỉ (nó ứng với trạng thái {1}). Chọn mã có trạng thái {2}."
			).format(frappe.bold(code), frappe.bold(status or "?"), " hoặc ".join(LEAVE_STATUSES)),
			title=_("Mã công không hợp lệ"),
		)

	# Gỡ các mã cùng maps_to_status đang trỏ tới loại nghỉ này nhưng không phải mã vừa chọn:
	# giữ đúng một mã cả-ngày cho mỗi loại nghỉ, tránh reverse-derive phải đoán.
	for stale in frappe.get_all(
		"Attendance Code",
		filters={"leave_type": leave_type, "maps_to_status": status, "name": ("!=", code)},
		pluck="name",
	):
		frappe.db.set_value("Attendance Code", stale, "leave_type", None)

	frappe.db.set_value("Attendance Code", code, "leave_type", leave_type)


def warn_if_unmapped(doc, method=None):
	"""Cảnh báo (KHÔNG chặn) khi một Loại nghỉ chưa có mã công cả ngày nào trỏ tới.

	Không chặn vì HR vẫn phải tạo được Loại nghỉ; nhưng để im thì lỗi chỉ lộ ra sau khi bảng chấm
	công đã in sai."""
	if doc.get("name") and not full_day_code_for(doc.get("name")):
		frappe.msgprint(
			_(
				"Loại nghỉ {0} chưa có mã công nào. Ngày nghỉ theo loại này sẽ không hiện mã trên "
				"bảng chấm công. Chọn "
			).format(frappe.bold(doc.get("name")))
			+ _("Mã công cả ngày")
			+ _(" ở trên, hoặc tạo một Mã công trỏ tới loại nghỉ này."),
			title=_("Chưa gắn mã công"),
			indicator="orange",
		)
