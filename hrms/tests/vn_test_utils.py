# Copyright (c) 2026, Miyano Việt Nam.
"""Tiện ích dùng chung cho test của lớp bản địa hoá VN (Miyano)."""

import frappe


def default_company() -> str:
	"""Công ty để dựng dữ liệu test — KHÔNG hardcode tên.

	Hardcode ``company="Miyano"`` làm test chỉ chạy được trên site miyano; trên ``test_site``
	của CI (chỉ có ``_Test Company``) mọi lời gọi vỡ với
	``LinkValidationError: Could not find Company: Miyano``, kéo theo hàng loạt lỗi dây chuyền
	(``Salary Slip None not found``, ``'NoneType' object has no attribute ...``).

	Xác định công ty y hệt cách ``hrms.vn_payroll.setup_mvl`` làm, để cấu trúc lương MVL và dữ
	liệu test luôn thuộc cùng một công ty.
	"""
	company = frappe.defaults.get_defaults().get("company") or frappe.db.get_value("Company", {}, "name")
	if not company:
		raise AssertionError("site chưa có Company nào để dựng dữ liệu test")
	return company


def ensure_short_hours_code() -> str:
	"""Đảm bảo mã `1/2X` (làm nửa ngày do thiếu giờ) có mặt cho test cần nó.

	`1/2X` đi kèm `hrms/fixtures/attendance_code.json` nên site đã `bench migrate` thì hàm này là
	no-op. Site chưa sync fixtures (hoặc `test_site` của CI dựng từ đầu) thì tạo tạm trong chính
	transaction của test — harness rollback dọn sạch sau đó. Đây là DML thuần, không phải DDL, nên
	không có nguy cơ rò rỉ như khi tạo Custom Field.
	"""
	code = "1/2X"
	if not frappe.db.exists("Attendance Code", code):
		frappe.get_doc(
			{
				"doctype": "Attendance Code",
				"__newname": code,
				"code": code,
				"code_name": "Làm nửa ngày (thiếu giờ)",
				"category": "Công",
				"work_fraction": 0.5,
				"is_paid": 1,
				"maps_to_status": "Half Day",
			}
		).insert()
	return code


def test_employee(email: str = "vn_fixture@codes.com") -> str:
	"""Nhân viên để dựng dữ liệu test — TỰ TẠO, không đi tìm người có sẵn trên site.

	``frappe.db.get_value("Employee", {"status": "Active"}, "name")`` chỉ chạy được trên site đã
	có dữ liệu. Trên ``test_site`` của CI, mỗi test class rollback phần của nó, nên tới lượt class
	sau có thể không còn nhân viên nào: get_value trả ``None`` và mọi thứ phía sau vỡ —
	``MandatoryError: [Attendance]: employee``, ``KeyError: 'employee'``.

	``make_employee`` trả lại đúng nhân viên cũ nếu user đã tồn tại, nên gọi nhiều lần là an toàn.
	"""
	from erpnext.setup.doctype.employee.test_employee import make_employee

	return make_employee(email, company=default_company())
