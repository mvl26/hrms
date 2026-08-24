# Copyright (c) 2026, Miyano Việt Nam.
"""Miyano — quỹ phép năm.

CHỈ "Nghỉ phép năm" trừ vào quỹ phép năm (Frappe tự chặn khi hết). Đơn nghỉ ``leave_type =
"Nghỉ phép năm"`` **bắt buộc chọn "Loại nghỉ"** — hiện chỉ còn một lựa chọn hợp lệ suy ra mã công:

    Nghỉ phép năm → P

**Nghỉ ốm / chăm con ốm KHÔNG trừ quỹ phép năm**: nộp bằng loại nghỉ riêng (``Nghỉ ốm`` /
``Nghỉ chăm con ốm``) hoặc ghi thẳng mã công Ô/Cô — bridge reverse-derive tự đặt mã.

Nhưng KHÔNG tính công: **quỹ BHXH chi trả** ngày ốm và chăm con ốm (Đ.25/28 Luật BHXH), không phải
doanh nghiệp, nên Ô/Cô mang ``is_paid = 0`` và rơi khỏi "Tổng công" (quyết định 2026-07-30, HR xác
nhận lại 2026-08-04). Chỗ này từng ghi ngược là "CÓ LƯƠNG, ĐỦ CÔNG" — sai so với dữ liệu và so với
`is_paid_leave` của báo cáo chấm công; sửa lại 2026-08-04 để không ai đọc chú thích rồi tin nhầm.

Thai sản do BHXH trả nên cũng không tính công. Ngược lại việc riêng cưới-tang / TNLĐ / nghỉ bù là
CÔNG TY trả nên vẫn hưởng lương, đủ công, và KHÔNG trừ quỹ phép năm; K không lương.

Sau khi duyệt sinh Attendance, hook ghi mã P lên Attendance để bảng công hiện đúng. Nghỉ **nửa ngày**
phải chọn buổi (``custom_half_day_period`` = Sáng/Chiều) — buổi để đặt half_day_date của đơn — nhưng
mã hiển thị là MỘT token đơn ``1/2P`` (nghỉ phép nửa ngày + nửa ngày đi làm đủ), KHÔNG tách P/X. Quy
ước mã: dạng ``A/B`` chỉ khi hai nửa khác nhau mà không có token; nửa phép + nửa làm đã có token 1/2P.

Thuần hiển thị: chỉ ghi mã/công qua ``db_set`` — không đổi status/leave_type/half_day_status →
lương bất biến.
"""

import frappe
from frappe.utils import cint, flt, getdate

POOL_LEAVE_TYPE = "Nghỉ phép năm"
# Loại nghỉ (nhãn tiếng Việt hiện trên đơn) → mã công. Khớp code_name trong
# hrms/fixtures/attendance_code.json. Miyano: CHỈ "Nghỉ phép năm" trừ vào quỹ phép năm. Nghỉ ốm /
# chăm con ốm KHÔNG trừ phép năm → nộp bằng loại nghỉ riêng (Nghỉ ốm / Nghỉ chăm con ốm) hoặc ghi
# thẳng mã công Ô/Cô; bridge reverse-derive tự đặt mã. Hai loại đó do BHXH trả nên không tính công.
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
	"""
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
	nghỉ lên Attendance để bảng công hiện đúng — cho MỌI loại nghỉ.

	Đơn rút quỹ phép năm lấy mã từ "Loại nghỉ" người dùng chọn; loại nghỉ khác tra bảng
	``Attendance Code``. Không thể phó mặc cho bridge reverse-derive: khi ngày đó ĐÃ có bản ghi (Vắng
	do auto-attendance), upstream đi nhánh ``db_set`` nên ``before_validate`` không chạy và mã ``V``
	kẹt lại dù status đã là On Leave.

	THUẦN HIỂN THỊ: chỉ đặt mã qua ``db_set`` — không đụng status/leave_type/half_day_status nên lương
	không đổi. Ngày nghỉ nửa ngày: dùng token đơn (1/2P)."""
	if doc.get("leave_type") == POOL_LEAVE_TYPE:
		code = resolve_reason_code(doc)
	else:
		code = code_for_leave_type(doc.get("leave_type"))
	if not code:
		return  # không map được thì GIỮ NGUYÊN mã cũ, không bịa
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
			day_code = HALF_DAY_CODE.get(code, code)
		else:
			day_code = code

		# db_set thuần hiển thị nên không đụng status/leave_type/half_day_status → lương bất biến.
		vals = {
			"custom_attendance_code": day_code,
			"custom_morning_code": None,
			"custom_afternoon_code": None,
			"custom_work_credit": work_credit(day_code),
		}
		for field, value in vals.items():
			frappe.db.set_value("Attendance", att.name, field, value, update_modified=False)
