# Copyright (c) 2026, Miyano Việt Nam.
"""Chốt chặn: đơn nghỉ theo loại chưa có mã công thì KHÔNG lưu được.

Đây là chỗ duy nhất chặn được mà không bế tắc con-gà-quả-trứng — lúc này cả loại nghỉ lẫn mã đều đã
có cơ hội tồn tại. Không có chốt này thì ngày nghỉ ra 0 công trong im lặng (spec §1.1).

Chốt gắn vào `before_validate`, KHÔNG phải `validate`: `Document.hook` chạy method của controller
TRƯỚC rồi mới tới hook của `doc_events` (xem `frappe/model/document.py::hook`), nên gắn vào
`validate` thì `LeaveApplication.validate()` của upstream (số dư phép, trùng đơn, ngày lễ) nổ trước
— người dùng thấy sai nguyên nhân, và test thì xanh vì nhầm lý do.

Chạy qua harness rollback (KHÔNG bench run-tests trên miyano).
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from hrms.tests.isolation import PerTestRollback
from hrms.tests.vn_test_utils import default_company, test_employee

UNMAPPED = "Nghỉ thử chưa có mã"


class TestLeaveTypeCodeGate(PerTestRollback, FrappeTestCase):
	def setUp(self):
		self.employee = test_employee("gate_ma_cong@codes.com")
		self.company = default_company()

	def unmapped_leave_type(self):
		frappe.get_doc({"doctype": "Leave Type", "leave_type_name": UNMAPPED, "is_lwp": 0}).insert(
			ignore_permissions=True
		)
		return UNMAPPED

	def allocate(self, leave_type):
		alloc = frappe.get_doc(
			{
				"doctype": "Leave Allocation",
				"employee": self.employee,
				"leave_type": leave_type,
				"from_date": "2099-01-01",
				"to_date": "2099-12-31",
				"new_leaves_allocated": 10,
			}
		)
		alloc.insert(ignore_permissions=True)
		alloc.submit()

	def leave_doc(self, leave_type, day, half_day=0):
		return frappe.get_doc(
			{
				"doctype": "Leave Application",
				"employee": self.employee,
				"leave_type": leave_type,
				"from_date": day,
				"to_date": day,
				"half_day": half_day,
				"half_day_date": day if half_day else None,
				"custom_half_day_period": "Sáng" if half_day else None,
				"company": self.company,
				"status": "Approved",
				"leave_approver": frappe.session.user,
			}
		)

	def test_blocks_a_leave_type_with_no_full_day_code(self):
		"""Loại nghỉ chưa gắn mã → chặn ngay, và chặn vì ĐÚNG lý do (không phải hết phép)."""
		lt = self.unmapped_leave_type()
		self.allocate(lt)  # số dư đủ → nếu vẫn chặn thì đúng là do thiếu mã
		with self.assertRaisesRegex(frappe.ValidationError, "mã công"):
			self.leave_doc(lt, "2099-06-15").insert(ignore_permissions=True)

	def test_blocks_half_day_when_only_a_full_day_code_exists(self):
		"""Nghỉ NỬA ngày cần mã Half Day riêng — "Nghỉ ốm" chỉ có `Ô` (cả ngày)."""
		self.allocate("Nghỉ ốm")
		with self.assertRaisesRegex(frappe.ValidationError, "Half Day"):
			self.leave_doc("Nghỉ ốm", "2099-06-15", half_day=1).insert(ignore_permissions=True)

	def test_allows_a_leave_type_that_has_both_codes(self):
		"""Đối chứng: "Nghỉ không lương" có cả `K` lẫn `1/2K` → cả hai dạng đều qua.

		Cố ý KHÔNG dùng "Nghỉ phép năm": nó còn dính nhánh đặc biệt `validate_pool_code` (bắt chọn
		trường "Loại nghỉ"), nên nếu test này xanh/đỏ thì không biết là vì chốt mã công hay vì cái
		hằng cứng kia. Task 5 gỡ hằng xong sẽ có thêm đối chứng cho chính "Nghỉ phép năm".

		Hai ngày KHÁC nhau: cùng ngày sẽ vướng chốt trùng đơn của upstream, không liên quan gì tới
		thứ test này đang đo."""
		self.leave_doc("Nghỉ không lương", "2099-06-15").insert(ignore_permissions=True)
		self.leave_doc("Nghỉ không lương", "2099-06-17", half_day=1).insert(ignore_permissions=True)

	def test_message_names_the_leave_type_and_the_status_needed(self):
		"""Thông báo phải nói đủ để HR tự sửa được, không bắt đi hỏi."""
		lt = self.unmapped_leave_type()
		self.allocate(lt)
		with self.assertRaises(frappe.ValidationError):
			self.leave_doc(lt, "2099-06-15").insert(ignore_permissions=True)
		message = str(frappe.message_log[-1]) if frappe.message_log else ""
		self.assertIn(lt, message)
		self.assertIn("On Leave", message)
