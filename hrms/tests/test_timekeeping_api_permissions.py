# Copyright (c) 2026, Miyano Việt Nam.
"""Các API chấm công chỉ dành cho Nhân sự — tài khoản nhân viên gọi thẳng phải bị từ chối.

`@frappe.whitelist()` mở hàm cho MỌI tài khoản đăng nhập, kể cả nhân viên chỉ dùng app chấm công.
Trang Soát công và báo cáo Bảng chấm công có khai vai trò, nhưng vai trò đó chỉ gác giao diện: gọi
thẳng `/api/method/...` là đi vòng qua. Ba hàm dưới đây đọc bằng `frappe.get_all` (bỏ qua phân
quyền) hoặc ghi bằng `set_value`, nên không tự gác thì không còn gì gác.

Không dùng `frappe.only_for`: nó trả về ngay khi `frappe.flags.in_test`, tức không test nào kiểm
được chốt đó có thật hay không.

Chạy qua harness rollback (KHÔNG bench run-tests trên miyano).
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from hrms.tests.isolation import PerTestRollback
from hrms.tests.vn_test_utils import default_company

PLAIN_USER = "plain_staff@timekeeping.test"
HR_USER = "hr_staff@timekeeping.test"


def ensure_user(email: str, role: str) -> str:
	if not frappe.db.exists("User", email):
		frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": email.split("@")[0],
				"send_welcome_email": 0,
				"roles": [{"role": role}],
			}
		).insert(ignore_permissions=True)
	return email


class TestTimekeepingApisAreHrOnly(PerTestRollback, FrappeTestCase):
	def setUp(self):
		self.company = default_company()
		ensure_user(PLAIN_USER, "Employee")
		ensure_user(HR_USER, "HR User")
		self.addCleanup(frappe.set_user, "Administrator")

	def test_review_grid_refuses_a_plain_employee(self):
		"""Lưới soát công trả mã công, trạng thái, loại nghỉ của CẢ công ty."""
		from hrms.hr.attendance_review import get_review_grid

		frappe.set_user(PLAIN_USER)
		with self.assertRaises(frappe.PermissionError):
			get_review_grid({"month": 9, "year": 2099, "company": self.company})

	def test_review_grid_still_opens_for_hr(self):
		from hrms.hr.attendance_review import get_review_grid

		frappe.set_user(HR_USER)
		grid = get_review_grid({"month": 9, "year": 2099, "company": self.company})
		self.assertIn("rows", grid)

	def test_code_sync_preview_refuses_a_plain_employee(self):
		from hrms.hr.attendance_code_sync import preview_sync

		frappe.set_user(PLAIN_USER)
		with self.assertRaises(frappe.PermissionError):
			preview_sync({"month": 9, "year": 2099, "company": self.company})

	def test_code_sync_preview_still_opens_for_hr(self):
		from hrms.hr.attendance_code_sync import preview_sync

		frappe.set_user(HR_USER)
		self.assertIn("changes", preview_sync({"month": 9, "year": 2099, "company": self.company}))

	def test_lunch_recompute_refuses_a_plain_employee(self):
		"""Hàm này GHI cờ ăn trưa cho cả kỳ — cờ đó đi thẳng vào khoản ăn trưa trên phiếu lương."""
		from hrms.vn_payroll.lunch import recompute_lunch_flags

		frappe.set_user(PLAIN_USER)
		with self.assertRaises(frappe.PermissionError):
			recompute_lunch_flags(9, 2099, self.company)

	def test_lunch_recompute_still_runs_for_hr(self):
		from hrms.vn_payroll.lunch import recompute_lunch_flags

		frappe.set_user(HR_USER)
		self.assertEqual(recompute_lunch_flags(9, 2099, self.company), 0)

	def test_closing_a_sheet_does_not_need_the_review_role(self):
		"""`before_submit` của Bảng Công Tháng tự đọc lưới để cảnh báo ô bất thường. Chốt gác chỉ
		nằm ở cửa API; đường gọi nội bộ không được vỡ theo."""
		from hrms.hr.attendance_review import build_review_grid

		frappe.set_user(PLAIN_USER)
		grid = build_review_grid({"month": 9, "year": 2099, "company": self.company})
		self.assertIn("flags", grid)
