# Copyright (c) 2026, Miyano Việt Nam.
"""Miyano — đồng bộ mã công với `status`/`leave_type` cho một kỳ.

**Vì sao cần:** upstream ``create_or_update_attendance`` đi nhánh ``db_set`` khi ngày đó ĐÃ có bản
ghi (thường là Vắng do auto-attendance sinh vì không có checkin). ``db_set`` ghi thẳng DB nên cầu
nối mã công không chạy và mã ``V`` kẹt lại dù ``status`` đã là ``On Leave``. Bảng công tháng gom
theo *category* của mã nên ngày đó đếm vào cột Vắng thay vì cột Phép/Ốm/…

``leave_single_pool.set_leave_attendance_code`` đã chặn nguồn phát sinh mới; module này để **dọn
dữ liệu đã lệch từ trước**.

**Xem trước rồi mới áp** — đây là dữ liệu lương thật, không tự ý sửa hàng loạt.

THUẦN HIỂN THỊ: chỉ ghi ``custom_attendance_code`` / ``custom_morning_code`` /
``custom_afternoon_code`` / ``custom_work_credit``. Ba field payroll đọc (``status``,
``leave_type``, ``half_day_status``) **không bao giờ** bị chạm → lương bất biến theo cấu trúc.
"""

import json

import frappe
from frappe import _
from frappe.utils import flt, get_last_day, getdate

from hrms.hr.doctype.attendance.attendance import _pick_reverse_code


def expected_code(row) -> str | None:
	"""Mã công đúng ra phải có, suy từ `status` + `leave_type`. None nếu không suy được."""
	filters = {"maps_to_status": row.status, "leave_type": row.leave_type or ["is", "not set"]}
	return _pick_reverse_code(row.status, frappe.get_all("Attendance Code", filters=filters, pluck="name"))


def period_bounds(month, year):
	start = getdate(f"{int(year)}-{int(month):02d}-01")
	return start, get_last_day(start)


@frappe.whitelist()
def preview_sync(filters: str | dict | None = None) -> dict:
	"""Liệt kê ngày công có mã lệch với status/leave_type. **Không ghi gì.**"""
	if isinstance(filters, str):
		filters = json.loads(filters)
	filters = frappe._dict(filters or {})
	if not (filters.get("month") and filters.get("year")):
		frappe.throw(_("Phải chọn tháng và năm."))

	start, end = period_bounds(filters.month, filters.year)
	att_filters = {"attendance_date": ["between", [start, end]], "docstatus": ["<", 2]}
	if filters.get("company"):
		att_filters["company"] = filters.company

	changes = []
	for row in frappe.get_all(
		"Attendance",
		filters=att_filters,
		fields=[
			"name",
			"employee",
			"employee_name",
			"attendance_date",
			"status",
			"leave_type",
			"custom_attendance_code",
			"custom_morning_code",
			"custom_afternoon_code",
		],
		order_by="attendance_date, employee",
		limit_page_length=0,
	):
		# mã nhập tay theo buổi = ý định của người dùng, không đè
		if row.custom_morning_code or row.custom_afternoon_code:
			continue
		want = expected_code(row)
		if not want or want == row.custom_attendance_code:
			continue  # không suy được thì GIỮ NGUYÊN, không bịa
		changes.append(
			{
				"attendance": row.name,
				"employee": row.employee,
				"employee_name": row.employee_name,
				"attendance_date": str(row.attendance_date),
				"status": row.status,
				"leave_type": row.leave_type,
				"old_code": row.custom_attendance_code,
				"new_code": want,
			}
		)
	return {"changes": changes, "count": len(changes)}


@frappe.whitelist()
def apply_sync(rows: str | list, reason: str | None = None) -> dict:
	"""Áp đúng danh sách người dùng đã duyệt ở bước xem trước.

	Kỳ đã chốt thì xếp vào ``skipped`` kèm lý do — KHÔNG ném lỗi làm vỡ cả lượt, vì một bảng đã chốt
	giữa kỳ không được phép chặn việc dọn các ngày còn lại."""
	if isinstance(rows, str):
		rows = json.loads(rows)
	if not reason or not reason.strip():
		frappe.throw(_("Phải nhập lý do đồng bộ."))
	reason = reason.strip()

	from hrms.hr.attendance_review import payroll_snapshot
	from hrms.hr.doctype.attendance_correction_log.attendance_correction_log import log_correction
	from hrms.hr.period_lock import locking_sheet

	applied, skipped = [], []
	for r in rows or []:
		name = r.get("attendance") if isinstance(r, dict) else r
		doc = frappe.get_doc("Attendance", name)
		doc.check_permission("write")

		sheet = locking_sheet(doc.employee, doc.attendance_date)
		if sheet:
			skipped.append({"attendance": name, "reason": _("Kỳ đã chốt tại {0}").format(sheet)})
			continue

		want = expected_code(doc)
		if not want or want == doc.custom_attendance_code:
			skipped.append({"attendance": name, "reason": _("Mã đã đúng hoặc không suy được")})
			continue

		before = payroll_snapshot(doc)
		credit = flt(frappe.db.get_value("Attendance Code", want, "work_fraction"))
		# CHỈ field hiển thị — status/leave_type/half_day_status không nằm trong danh sách này.
		frappe.db.set_value(
			"Attendance",
			name,
			{
				"custom_attendance_code": want,
				"custom_morning_code": None,
				"custom_afternoon_code": None,
				"custom_work_credit": credit,
			},
			update_modified=False,
		)
		doc.custom_attendance_code = want
		after = payroll_snapshot(doc)
		after["custom_work_credit"] = credit
		log_correction(doc, before, after, reason)
		applied.append(name)

	return {"applied": len(applied), "names": applied, "skipped": skipped}
