# Copyright (c) 2026, Miyano Việt Nam.
"""KHOÁ KỲ — làm cho "chốt công" thật sự có hiệu lực.

Trước đây Bảng Công Tháng chỉ là ảnh chụp: chốt và ký xong vẫn sửa được Attendance, lương đổi
theo, còn bảng đã ký thì đứng im — hai con số lệch nhau mà không ai được cảnh báo. Module này
đóng băng kỳ: khi một Bảng Công Tháng đã submit phủ ngày đó, mọi thao tác thêm/sửa/huỷ ngày công
trong kỳ đều bị chặn. Muốn sửa thì phải huỷ bảng chốt — và việc huỷ để lại vết qua `docstatus`.

Nhờ đó, payroll vẫn đọc thẳng Attendance như cũ (không đụng một dòng công thức lương nào) mà số
liệu vẫn **đúng bằng bảng đã chốt**: bảng là bản quyền lực, Attendance là kho đông lạnh của nó.

Lưu ý vận hành: chốt kỳ rồi thì auto-attendance cũng không tạo được bản ghi mới cho kỳ đó nữa.
Đó là chủ ý — một ngày công mọc thêm sau khi chốt chính là thứ làm bảng ký và phiếu lương lệch nhau.
"""

import frappe
from frappe import _
from frappe.utils import get_link_to_form, getdate


def locking_sheet(employee: str, date) -> str | None:
	"""Tên Bảng Công Tháng ĐÃ CHỐT phủ ngày này của nhân viên, hoặc None nếu kỳ còn mở.

	Bảng có phòng ban chỉ khoá nhân viên thuộc phòng ban đó; bảng không ghi phòng ban khoá cả
	công ty."""
	if not (employee and date):
		return None

	emp = frappe.db.get_value("Employee", employee, ["company", "department"], as_dict=True)
	if not emp:
		return None

	date = getdate(date)
	sheets = frappe.get_all(
		"Monthly Attendance Sheet",
		filters={
			"docstatus": 1,
			"company": emp.company,
			"from_date": ["<=", date],
			"to_date": [">=", date],
		},
		fields=["name", "department"],
	)
	for s in sheets:
		if not s.department or s.department == emp.department:
			return s.name
	return None


def is_period_locked(employee: str, date) -> bool:
	return bool(locking_sheet(employee, date))


def throw_period_locked(date, sheet: str):
	frappe.throw(
		_("Kỳ chấm công của ngày {0} đã chốt tại {1}. Muốn sửa thì phải huỷ bảng chốt đó trước.").format(
			frappe.bold(frappe.utils.formatdate(date)),
			get_link_to_form("Monthly Attendance Sheet", sheet),
		),
		title=_("Kỳ đã chốt"),
	)


def guard_period_not_locked(doc, method=None):
	"""Chặn mọi thay đổi ngày công thuộc kỳ đã chốt. Gắn vào `doc_events` của Attendance."""
	sheet = locking_sheet(doc.get("employee"), doc.get("attendance_date"))
	if sheet:
		throw_period_locked(doc.get("attendance_date"), sheet)


def first_locked_day(employee: str, start, end) -> tuple | None:
	"""`(ngày, tên bảng)` của ngày đã chốt ĐẦU TIÊN trong khoảng, hoặc None nếu cả khoảng còn mở."""
	if not (employee and start and end):
		return None
	day, end = getdate(start), getdate(end)
	while day <= end:
		sheet = locking_sheet(employee, day)
		if sheet:
			return day, sheet
		day = frappe.utils.add_days(day, 1)
	return None


def guard_range_not_locked(employee: str, start, end):
	"""Chặn một chứng từ NHIỀU NGÀY (đơn nghỉ, Yêu cầu chấm công) chạm vào kỳ đã chốt.

	Hook `guard_period_not_locked` chỉ chạy khi Attendance đi qua `Document` (insert / sửa sau
	submit / huỷ). Các chứng từ này lại ghi lên bản ghi CÓ SẴN bằng `db_set` / `set_value` — thẳng
	xuống DB, không hook nào chạy — nên phải chặn ngay tại chứng từ, trước khi nó kịp ghi."""
	hit = first_locked_day(employee, start, end)
	if hit:
		throw_period_locked(*hit)


def guard_leave_application(doc, method=None):
	"""`before_submit` + `before_cancel` của Đơn xin nghỉ.

	Duyệt đơn thì upstream `create_or_update_attendance` đổi status/leave_type của ngày công có sẵn
	bằng `db_set`; huỷ đơn thì `cancel_attendance` đặt thẳng `docstatus = 2`. Cả hai đều đổi lương
	của một kỳ đã ký mà không để lại vết nào trên bảng công.

	Đơn bị TỪ CHỐI không sinh ngày công nên không cần chặn. Lúc huỷ, `before_cancel` của controller
	đã kịp đổi `doc.status` thành "Cancelled", nên phải hỏi DB xem trước đó đơn có được duyệt không."""
	status = doc.get("status")
	if doc.docstatus == 2:
		status = frappe.db.get_value("Leave Application", doc.name, "status")
	if status != "Approved":
		return
	guard_range_not_locked(doc.get("employee"), doc.get("from_date"), doc.get("to_date"))


def guard_attendance_request(doc, method=None):
	"""`before_submit` của Yêu cầu chấm công — cùng lý do với đơn nghỉ: ngày đã có bản ghi thì
	upstream sửa status bằng `db_set`. (Huỷ phiếu đi qua `Attendance.cancel()` nên đã có hook gác.)"""
	guard_range_not_locked(doc.get("employee"), doc.get("from_date"), doc.get("to_date"))
