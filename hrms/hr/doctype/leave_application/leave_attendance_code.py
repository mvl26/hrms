# Copyright (c) 2026, Miyano Việt Nam.
"""Miyano — suy MÃ CÔNG cho đơn nghỉ. Mã công là neo, không loại nghỉ nào là trường hợp đặc biệt.

Ba việc, cùng một nguyên tắc — ``Attendance Code`` là nguồn sự thật duy nhất:

- ``validate_leave_type_has_code`` — chặn đơn nghỉ theo loại chưa có mã ứng với trạng thái cần.
- ``validate_half_day_period`` — nghỉ nửa ngày phải nói rõ nửa nào.
- ``set_leave_attendance_code`` — sau khi duyệt, ghi mã suy từ bảng lên Attendance.

**Vì sao hook ghi mã, không phó mặc cầu nối:** khi ngày đó ĐÃ có bản ghi (thường là Vắng do
auto-attendance), upstream ``create_or_update_attendance`` đi nhánh ``db_set`` — ghi thẳng DB nên
``before_validate`` và cầu nối mã công KHÔNG chạy, mã ``V`` kẹt lại dù ``status`` đã là ``On Leave``.

**Lịch sử:** tới 2026-08-24 module này tên ``leave_single_pool`` và giữ một hằng tên loại nghỉ quỹ
phép năm cùng hai bảng map cứng loại nghỉ → mã. Đã kiểm chứng nhánh cứng đó cho ĐÚNG cùng kết quả
với việc tra bảng ``Attendance Code``, nên nó bị gỡ: HR tạo bao nhiêu Loại nghỉ tuỳ ý, mỗi loại chỉ
cần một dòng mã công là chạy đúng. Xem `docs/spec/attendance-code-as-anchor.md`.

Quy ước mã nửa ngày: MỘT token đơn (``1/2P`` = nghỉ phép nửa ngày + nửa ngày đi làm đủ), KHÔNG tách
``P/X``. Dạng ``A/B`` chỉ dùng khi hai nửa khác nhau mà không có token sẵn.

Thuần hiển thị: chỉ ghi mã/công qua ``db_set`` — không đổi status/leave_type/half_day_status →
lương bất biến.
"""

import frappe
from frappe.utils import cint, flt, getdate

#: Bật chốt "loại nghỉ phải có mã công" TRONG lúc chạy test. Xem `validate_leave_type_has_code`.
ENFORCE_LEAVE_CODE_FLAG = "miyano_enforce_leave_code"


def leave_code_gate_is_active() -> bool:
	"""Chốt mã công có hiệu lực không.

	Ở SITE THẬT: luôn có. Ở CHẾ ĐỘ TEST: chỉ khi test tự bật cờ ``ENFORCE_LEAVE_CODE_FLAG``.

	Lý do: hàng trăm test của upstream tạo Loại nghỉ tạm (``_Test Leave Type``,
	``Test Earned Leave``, …) rồi nộp đơn nghỉ theo chúng. Những loại đó sẽ không bao giờ có mã
	công — chúng chỉ sống trong một test — nên chốt này chặn hết và CI đỏ ~46 lỗi không liên quan
	gì tới thứ các test đó đang đo. Bắt mỗi test upstream tự tạo thêm một Mã Công là sửa sai chỗ.

	Cờ, chứ không phải bỏ hẳn chốt trong test: ``test_leave_type_code_gate.py`` bật cờ lên để vẫn
	kiểm được chính chốt này. Hành vi trên site thật KHÔNG đổi một ly.
	"""
	return not frappe.flags.in_test or bool(frappe.flags.get(ENFORCE_LEAVE_CODE_FLAG))


def code_for_leave_type(leave_type, status="On Leave"):
	"""Mã công của một Loại nghỉ, tra từ bảng `Attendance Code` (nguồn sự thật duy nhất).

	Dùng cho mọi loại nghỉ NGOÀI quỹ phép năm. Cần thiết vì upstream
	``create_or_update_attendance`` đi nhánh ``db_set`` khi ngày đó ĐÃ có bản ghi (thường là Vắng do
	auto-attendance): ``db_set`` ghi thẳng DB nên ``before_validate`` — và cầu nối mã công — không
	chạy, mã cũ (``V``) nằm nguyên. Ở nhánh tạo mới thì ``insert()`` chạy cầu nối nên vẫn đúng.

	Trả None khi không loại nghỉ nào map tới — người gọi phải GIỮ NGUYÊN mã cũ, không được bịa."""
	if not leave_type:
		return None
	from hrms.hr.doctype.attendance.attendance import _pick_reverse_code

	matches = frappe.get_all(
		"Attendance Code",
		filters={"maps_to_status": status, "leave_type": leave_type},
		pluck="name",
	)
	return _pick_reverse_code(status, matches)


def work_credit(code: str) -> float:
	"""Field hiển thị "Công" của một mã: số công DOANH NGHIỆP TRẢ cho ngày đó.

	Dùng chung `paid_credit` với cầu nối mã công, báo cáo và bộ đồng bộ — nguồn luật duy nhất. Chỗ
	này từng ghi thẳng `work_fraction` (công ĐI LÀM thực), nghĩa CŨ mà patch
	`recompute_work_credit_as_paid_cong` đã bỏ: ngày nghỉ phép năm hiện "Công = 0" dù công ty trả đủ
	lương, và cùng một ngày đi hai đường (đơn nghỉ vs dựng lại ngày công) ra hai số khác nhau."""
	from hrms.hr.report.monthly_attendance_report.monthly_attendance_report import paid_credit

	row = frappe.db.get_value("Attendance Code", code, ["category", "work_fraction", "is_paid"], as_dict=True)
	return flt(paid_credit(row)) if row else 0.0


def validate_leave_type_has_code(doc, method=None):
	"""Loại nghỉ của đơn phải có mã công ứng với TRẠNG THÁI mà đơn sẽ sinh ra.

	Không có mã thì ngày nghỉ ra 0 công và bảng chấm công để trống — hoặc tệ hơn, giữ nguyên mã
	``V`` của bản ghi vắng có sẵn, làm lương (đọc ``status``) và bảng công (đọc mã) nói ngược nhau.

	Gắn vào ``before_validate``, KHÔNG phải ``validate``: ``Document.hook`` chạy method của
	controller TRƯỚC rồi mới tới hook ``doc_events``, nên ở ``validate`` thì mọi chốt của upstream
	(số dư phép, trùng đơn, ngày lễ) nổ trước và người dùng thấy sai nguyên nhân. Thiếu mã công là
	vấn đề gốc hơn số dư phép, phải báo trước.

	Đơn nghỉ nửa ngày cần THÊM một mã ``Half Day`` (token đơn kiểu ``1/2P``) — mã cả ngày không mô
	tả được nửa ngày đi làm. Cách chữa cho cả hai là tạo một Mã Công, một dòng master data.

	Trong lúc chạy test thì chốt chỉ bật khi test tự yêu cầu — xem ``leave_code_gate_is_active``.
	"""
	if not leave_code_gate_is_active():
		return

	leave_type = doc.get("leave_type")
	if not leave_type:
		return

	needed = ["On Leave"]
	if cint(doc.get("half_day")):
		needed.append("Half Day")

	for status in needed:
		if code_for_leave_type(leave_type, status):
			continue
		frappe.throw(
			frappe._(
				"Loại nghỉ {0} chưa có mã công cho trạng thái {1}. Tạo một Mã Công với "
				"Trạng thái = {1} và Loại nghỉ = {0}, rồi lưu lại đơn này."
			).format(frappe.bold(leave_type), frappe.bold(status)),
			title=frappe._("Thiếu mã công"),
		)


def validate_half_day_period(doc, method=None):
	"""Nghỉ nửa ngày phải chọn buổi (Sáng/Chiều) — cho MỌI loại nghỉ.

	Không phải luật mới: fixture của trường đã khai ``mandatory_depends_on = eval:doc.half_day`` và
	`setHalfDayPeriodVisibility` trong PWA cũng bắt buộc. Chỉ có chốt phía server là đang hẹp hơn
	khai báo (trước 2026-08-24 chỉ bắt với quỹ phép năm), nay khớp lại — nếu không, đường ghi qua
	API vẫn lọt bản ghi nửa ngày không rõ nửa nào."""
	if cint(doc.get("half_day")) and not doc.get("custom_half_day_period"):
		frappe.throw(frappe._("Nghỉ nửa ngày phải chọn buổi nghỉ: Sáng hay Chiều."))


def set_leave_attendance_code(doc, method=None):
	"""Sau khi Đơn xin nghỉ duyệt sinh Attendance (upstream ``update_attendance``), ghi mã suy từ
	bảng ``Attendance Code`` lên Attendance để bảng công hiện đúng — MỘT đường cho mọi loại nghỉ.

	THUẦN HIỂN THỊ: chỉ đặt mã qua ``db_set`` — không đụng status/leave_type/half_day_status nên
	lương không đổi. Ngày nghỉ nửa ngày dùng token đơn (1/2P).
	"""
	leave_type = doc.get("leave_type")
	full_code = code_for_leave_type(leave_type, "On Leave")
	half_code = code_for_leave_type(leave_type, "Half Day")
	half_day_date = doc.get("half_day_date")
	is_half = cint(doc.get("half_day")) and half_day_date

	for att in frappe.get_all(
		"Attendance",
		filters={"leave_application": doc.name, "docstatus": ["<", 2]},
		fields=["name", "attendance_date"],
	):
		day_code = (
			half_code if is_half and getdate(att.attendance_date) == getdate(half_day_date) else full_code
		)
		if not day_code:
			continue  # không map được thì GIỮ NGUYÊN mã cũ, không bịa

		# db_set thuần hiển thị nên không đụng status/leave_type/half_day_status → lương bất biến.
		frappe.db.set_value(
			"Attendance",
			att.name,
			{
				"custom_attendance_code": day_code,
				"custom_morning_code": None,
				"custom_afternoon_code": None,
				"custom_work_credit": work_credit(day_code),
			},
			update_modified=False,
		)
