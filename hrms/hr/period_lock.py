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


def guard_period_not_locked(doc, method=None):
	"""Chặn mọi thay đổi ngày công thuộc kỳ đã chốt. Gắn vào `doc_events` của Attendance."""
	sheet = locking_sheet(doc.get("employee"), doc.get("attendance_date"))
	if not sheet:
		return

	frappe.throw(
		_("Kỳ chấm công của ngày {0} đã chốt tại {1}. Muốn sửa thì phải huỷ bảng chốt đó trước.").format(
			frappe.bold(frappe.utils.formatdate(doc.get("attendance_date"))),
			get_link_to_form("Monthly Attendance Sheet", sheet),
		),
		title=_("Kỳ đã chốt"),
	)
