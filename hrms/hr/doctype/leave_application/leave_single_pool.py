# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt
"""Miyano — gộp một quỹ phép năm.

Nghỉ có lương thuộc nhóm "trừ quỹ" nộp qua Đơn xin nghỉ với ``leave_type = "Nghỉ phép năm"`` để cùng
rút một số dư (Frappe tự chặn khi hết). Người dùng **bắt buộc chọn "Loại nghỉ"** (tiếng Việt) khi
leave_type = quỹ phép năm — hệ thống tự suy ra **mã công** tương ứng (không nhập mã tay):

    Nghỉ phép năm → P · Nghỉ ốm → Ô · Nghỉ chăm con ốm → Cô

Đúng các loại trừ-quỹ ở VN, không thừa không thiếu (thai sản/việc riêng cưới-tang/TNLĐ là loại riêng
hưởng lương KHÔNG trừ quỹ; nghỉ bù riêng; không lương riêng).

Sau khi duyệt sinh Attendance, hook ghi mã đó lên Attendance để bảng công hiện Ô/Cô/P riêng. Nghỉ
**nửa ngày** phải chọn buổi (``custom_half_day_period`` = Sáng/Chiều): hook tách mã theo buổi
(nghỉ sáng → morning=mã, afternoon=X; nghỉ chiều → morning=X, afternoon=mã).

Thuần hiển thị: chỉ ghi mã/công qua ``db_set`` — không đổi status/leave_type/half_day_status →
lương bất biến. TS/N/T miễn trừ (loại nghỉ riêng, bridge reverse-derive tự đặt mã); K không lương.
"""

import frappe
from frappe.utils import cint, getdate

POOL_LEAVE_TYPE = "Nghỉ phép năm"
# Loại nghỉ (nhãn tiếng Việt hiện trên đơn) → mã công. Khớp code_name trong
# hrms/fixtures/attendance_code.json; đúng các loại TRỪ vào quỹ phép năm ở VN (không thừa không thiếu).
POOL_REASONS = {
	"Nghỉ phép năm": "P",
	"Nghỉ ốm": "Ô",
	"Nghỉ chăm con ốm": "Cô",
}
WORK_CODE = "X"  # buổi đi làm của ngày nghỉ nửa ngày


def resolve_reason_code(doc):
	"""Suy mã công từ "Loại nghỉ" (tiếng Việt) người dùng chọn trên đơn rút quỹ phép năm."""
	return POOL_REASONS.get(doc.get("custom_leave_reason"))


def validate_pool_code(doc, method=None):
	"""Đơn rút quỹ phép năm: **bắt buộc** chọn Loại nghỉ hợp lệ; nghỉ nửa ngày bắt buộc chọn buổi
	(Sáng/Chiều). Bỏ qua loại nghỉ khác (miễn trừ/không lương)."""
	if doc.get("leave_type") != POOL_LEAVE_TYPE:
		return
	if doc.get("custom_leave_reason") not in POOL_REASONS:
		frappe.throw(frappe._("Nghỉ phép năm phải chọn Loại nghỉ: {0}.").format(", ".join(POOL_REASONS)))
	if cint(doc.get("half_day")) and not doc.get("custom_half_day_period"):
		frappe.throw(frappe._("Nghỉ nửa ngày phải chọn buổi nghỉ: Sáng hay Chiều."))


def set_leave_attendance_code(doc, method=None):
	"""Sau khi Đơn xin nghỉ duyệt sinh Attendance (upstream ``update_attendance``), ghi mã suy từ Loại
	nghỉ lên Attendance để bảng công hiện đúng. Chỉ áp cho đơn rút quỹ phép năm; loại miễn trừ/khác để
	bridge reverse-derive tự đặt mã (TS/N/T…).

	THUẦN HIỂN THỊ: chỉ đặt mã qua ``db_set`` — không đụng status/leave_type/half_day_status nên lương
	không đổi. Ngày nghỉ nửa ngày: tách mã theo buổi (custom_morning_code / custom_afternoon_code)."""
	if doc.get("leave_type") != POOL_LEAVE_TYPE:
		return
	code = resolve_reason_code(doc)
	if not code:
		return
	period = doc.get("custom_half_day_period")
	half_day_date = doc.get("half_day_date")
	is_half = cint(doc.get("half_day")) and half_day_date and period

	for att in frappe.get_all(
		"Attendance",
		filters={"leave_application": doc.name, "docstatus": ["<", 2]},
		fields=["name", "attendance_date"],
	):
		if is_half and getdate(att.attendance_date) == getdate(half_day_date):
			# Sáng: nghỉ buổi sáng, đi làm buổi chiều; Chiều thì ngược lại.
			if period == "Sáng":
				vals = {"custom_morning_code": code, "custom_afternoon_code": WORK_CODE}
			else:
				vals = {"custom_morning_code": WORK_CODE, "custom_afternoon_code": code}
			vals["custom_attendance_code"] = None
		else:
			vals = {
				"custom_attendance_code": code,
				"custom_morning_code": None,
				"custom_afternoon_code": None,
			}
		for field, value in vals.items():
			frappe.db.set_value("Attendance", att.name, field, value, update_modified=False)
