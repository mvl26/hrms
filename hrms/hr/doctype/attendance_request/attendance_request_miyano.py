# Copyright (c) 2026, Miyano Việt Nam.
"""Miyano — Yêu cầu chấm công (Attendance Request) mở lại: có DUYỆT + ghi mã công riêng.

Kênh này khác **Đơn xin nghỉ**: dành cho ngày nhân viên VẪN làm việc / phải tính có mặt — làm tại
nhà (WFH), quên/thiếu chấm công, ra ngoài công việc (on-duty), đi muộn/về sớm. **Không trừ quỹ phép,
tính đủ công.**

- **Duyệt bởi quản lý trực tiếp** (`reports_to` → user). Nhân viên tạo bản nháp; chỉ người duyệt /
  Nhân sự mới được submit (``guard_submit``) → đóng lỗ hổng cũ "ghi thẳng ra Attendance không qua
  duyệt" khiến kênh này từng bị khoá.
- **Mã công** (``set_attendance_request_code``): sau khi submit sinh Attendance, ghi
  ``custom_attendance_code`` theo ``reason`` (WFH→W, On Duty→CT, còn lại→X) qua ``db_set`` —
  THUẦN HIỂN THỊ, không đụng status/leave_type/half_day_status → **lương bất biến**.
"""

import frappe
from frappe import _
from frappe.utils import cint, getdate

# reason (giá trị native + 2 giá trị Miyano thêm) → mã công hiển thị trên bảng chấm công.
REASON_TO_CODE = {
	"Work From Home": "W",  # làm tại nhà (W = Work from home)
	"On Duty": "CT",  # ra ngoài công việc = công tác → tái dùng mã CT có sẵn
	"Quên chấm công": "X",
	"Đi muộn/về sớm": "X",
}
DEFAULT_CODE = "X"  # reason lạ / trống → coi như đi làm đủ công
WORK_CODE = "X"  # buổi còn lại của ngày nửa buổi
APPROVER_BYPASS_ROLES = {"HR Manager", "HR User", "System Manager"}


# --- duyệt bởi quản lý trực tiếp ---------------------------------------------------------------
def set_default_approver(doc, method=None):
	"""``before_insert``/``validate``: điền người duyệt = quản lý trực tiếp (``reports_to`` → user)
	nếu để trống. Không ghi đè khi đã chọn tay."""
	if doc.get("custom_approver") or not doc.get("employee"):
		return
	reports_to = frappe.db.get_value("Employee", doc.employee, "reports_to")
	if reports_to:
		approver = frappe.db.get_value("Employee", reports_to, "user_id")
		if approver:
			doc.custom_approver = approver


def assign_to_approver(doc, method=None):
	"""``after_insert``: giao ToDo cho người duyệt (không tạo trùng ToDo Open) — như Công Tác."""
	approver = doc.get("custom_approver")
	if not approver:
		return
	if frappe.get_all(
		"ToDo",
		filters={
			"reference_type": "Attendance Request",
			"reference_name": doc.name,
			"allocated_to": approver,
			"status": "Open",
		},
		limit=1,
	):
		return
	from frappe.desk.form.assign_to import add as assign_add

	try:
		assign_add(
			{
				"assign_to": [approver],
				"doctype": "Attendance Request",
				"name": doc.name,
				"description": _("Duyệt yêu cầu chấm công {0} ({1})").format(
					doc.name, doc.get("reason") or ""
				),
			}
		)
	except frappe.exceptions.DuplicateEntryError:
		pass


def is_authorized_approver(doc) -> bool:
	"""Người dùng hiện tại có quyền duyệt phiếu này không (người duyệt được chỉ định, hoặc Nhân sự)."""
	user = frappe.session.user
	if user == "Administrator":
		return True
	if APPROVER_BYPASS_ROLES & set(frappe.get_roles(user)):
		return True
	return bool(doc.get("custom_approver")) and user == doc.get("custom_approver")


def guard_submit(doc, method=None):
	"""``before_submit``: chỉ người duyệt (quản lý trực tiếp) hoặc Nhân sự mới được duyệt.

	Tha khi ``frappe.flags.in_test`` — 10 test upstream của Attendance Request tạo+submit phiếu; chặn
	cứng sẽ phá chúng (CLAUDE.md: không fork hành vi upstream đã test). Logic quyền vẫn kiểm được qua
	``is_authorized_approver`` và test toggling flags."""
	if frappe.flags.in_test:
		return
	if not is_authorized_approver(doc):
		frappe.throw(
			_("Chỉ người duyệt ({0}) hoặc Nhân sự mới được duyệt yêu cầu chấm công này.").format(
				doc.get("custom_approver") or _("chưa chỉ định")
			),
			title=_("Không có quyền duyệt"),
		)


# --- mã công (thuần hiển thị, payroll-neutral) --------------------------------------------------
UNPAID_CODE = "K"  # nửa còn lại KHÔNG làm → nghỉ không lương (native half_day_status="Absent" trừ 0.5)


def set_attendance_request_code(doc, method=None):
	"""``on_submit``: sau khi upstream ``create_attendance_records`` sinh/cập nhật Attendance, ghi mã
	công theo ``reason`` (WFH→W, On Duty→CT, còn lại→X) lên các Attendance của phiếu này.

	THUẦN HIỂN THỊ: chỉ ghi ``custom_attendance_code``/``custom_morning_code``/``custom_afternoon_code``
	qua ``db_set`` — KHÔNG đụng ``status``/``leave_type``/``half_day_status`` → lương bất biến. Ghi đè
	mã mà bridge reverse-derive từ status (vd status "Work From Home" mặc định ra CT → sửa thành W).

	Ngày nửa buổi: buổi yêu cầu = mã reason; buổi còn lại suy TỪ half_day_status native (đúng payroll) —
	đã hiện diện (Present) → X ⇒ **W/X (đi làm đủ, cả ngày trả lương)**; chưa (Absent, native trừ 0.5) →
	K ⇒ **W/K (chỉ làm nửa ngày, nửa kia không lương)**."""
	code = REASON_TO_CODE.get(doc.get("reason"), DEFAULT_CODE)
	is_half = cint(doc.get("half_day")) and doc.get("half_day_date")
	half_date = getdate(doc.get("half_day_date")) if is_half else None

	for att in frappe.get_all(
		"Attendance",
		filters={"attendance_request": doc.name, "docstatus": ["<", 2]},
		fields=["name", "attendance_date", "half_day_status"],
	):
		if is_half and getdate(att.attendance_date) == half_date:
			# buổi còn lại: hiện diện đủ → X (W/X đủ công); không → K không lương (W/K nửa ngày). Khớp
			# đúng cách payroll xử lý half_day_status (chỉ Absent mới trừ 0.5) nên bảng công ↔ lương nhất quán.
			other = WORK_CODE if att.half_day_status == "Present" else UNPAID_CODE
			vals = {
				"custom_morning_code": code,
				"custom_afternoon_code": other,
				"custom_attendance_code": None,
			}
		else:
			vals = {
				"custom_attendance_code": code,
				"custom_morning_code": None,
				"custom_afternoon_code": None,
			}
		for field, value in vals.items():
			frappe.db.set_value("Attendance", att.name, field, value, update_modified=False)


def approved_request_for(employee: str, date) -> str | None:
	"""Tên Yêu cầu chấm công ĐÃ DUYỆT phủ ngày này, hoặc None."""
	return frappe.db.get_value(
		"Attendance Request",
		{
			"employee": employee,
			"docstatus": 1,
			"from_date": ["<=", date],
			"to_date": [">=", date],
		},
		"name",
	)


def reapply_attendance_request(employee: str, date) -> str | None:
	"""Dựng lại ngày công từ Yêu cầu chấm công đã duyệt. Trả tên yêu cầu nếu có dựng, None nếu không.

	Yêu cầu chấm công chỉ ghi ra Attendance ĐÚNG MỘT LẦN, lúc submit. Sau đó bất kỳ lần nào ngày
	công được dựng lại — chạy công cụ rebuild, HR huỷ rồi chấm lại, bản ghi bị xoá — auto-attendance
	thấy ngày trống là chấm **Vắng**, vì `get_dates_for_attendance` chỉ trừ ngày lễ và ngày đã có
	bản ghi, không hề hỏi Yêu cầu chấm công. Người lao động có đơn WFH đã duyệt mà vẫn bị ghi vắng.

	Hàm này để auto-attendance hỏi lại trước khi chấm vắng: có đơn đã duyệt thì dựng lại đúng ngày
	công đó (WFH / on-duty / quên chấm) thay vì chấm vắng. Dùng chính `create_or_update_attendance`
	của Yêu cầu chấm công nên không đẻ ra đường ghi thứ hai.
	"""
	name = approved_request_for(employee, date)
	if not name:
		return None

	doc = frappe.get_doc("Attendance Request", name)
	if not doc.should_mark_attendance(date):
		return None  # ngày lễ / đang nghỉ phép — chính đơn cũng không chấm ngày này

	doc.create_or_update_attendance(date)
	set_attendance_request_code(doc)
	return name
