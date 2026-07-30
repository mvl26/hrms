# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt
"""Miyano — quỹ phép năm.

CHỈ "Nghỉ phép năm" trừ vào quỹ phép năm (Frappe tự chặn khi hết). Đơn nghỉ ``leave_type =
"Nghỉ phép năm"`` **bắt buộc chọn "Loại nghỉ"** — hiện chỉ còn một lựa chọn hợp lệ suy ra mã công:

    Nghỉ phép năm → P

**Nghỉ ốm / chăm con ốm KHÔNG trừ quỹ phép năm** (nghỉ CÓ LƯƠNG, ĐỦ CÔNG): nộp bằng loại nghỉ riêng
(``Nghỉ ốm`` / ``Nghỉ chăm con ốm`` — BHXH trả, công ty không tính lương) hoặc ghi thẳng mã công Ô/Cô — bridge reverse-derive tự
đặt mã, payroll trả đủ. Thai sản/việc riêng cưới-tang/TNLĐ/nghỉ bù cũng là loại riêng hưởng lương
KHÔNG trừ quỹ; K không lương.

Sau khi duyệt sinh Attendance, hook ghi mã P lên Attendance để bảng công hiện đúng. Nghỉ **nửa ngày**
phải chọn buổi (``custom_half_day_period`` = Sáng/Chiều) — buổi để đặt half_day_date của đơn — nhưng
mã hiển thị là MỘT token đơn ``1/2P`` (nghỉ phép nửa ngày + nửa ngày đi làm đủ), KHÔNG tách P/X. Quy
ước mã: dạng ``A/B`` chỉ khi hai nửa khác nhau mà không có token; nửa phép + nửa làm đã có token 1/2P.

Thuần hiển thị: chỉ ghi mã/công qua ``db_set`` — không đổi status/leave_type/half_day_status →
lương bất biến.
"""

import frappe
from frappe.utils import cint, getdate

POOL_LEAVE_TYPE = "Nghỉ phép năm"
# Loại nghỉ (nhãn tiếng Việt hiện trên đơn) → mã công. Khớp code_name trong
# hrms/fixtures/attendance_code.json. Miyano: CHỈ "Nghỉ phép năm" trừ vào quỹ phép năm. Nghỉ ốm /
# chăm con ốm là nghỉ CÓ LƯƠNG, ĐỦ CÔNG, KHÔNG trừ phép năm → nộp bằng loại nghỉ riêng (Nghỉ ốm /
# Nghỉ chăm con ốm) hoặc ghi thẳng mã công Ô/Cô; bridge reverse-derive tự đặt mã, payroll trả đủ.
POOL_REASONS = {
	"Nghỉ phép năm": "P",
}
# Mã NỬA ngày (token đơn) cho từng loại nghỉ rút quỹ — nghỉ nửa ngày = đi làm đủ nửa còn lại.
HALF_DAY_CODE = {
	"P": "1/2P",
}


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
			# nghỉ nửa ngày (làm nửa còn lại) → MỘT token đơn 1/2P, không tách P/X (theo quy ước mã).
			# db_set thuần hiển thị nên không đụng status/leave_type/half_day_status → lương bất biến.
			vals = {
				"custom_attendance_code": HALF_DAY_CODE.get(code, code),
				"custom_morning_code": None,
				"custom_afternoon_code": None,
			}
		else:
			vals = {
				"custom_attendance_code": code,
				"custom_morning_code": None,
				"custom_afternoon_code": None,
			}
		for field, value in vals.items():
			frappe.db.set_value("Attendance", att.name, field, value, update_modified=False)
