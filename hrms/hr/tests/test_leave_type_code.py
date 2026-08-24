# Copyright (c) 2026, Miyano Việt Nam.
"""Ô "Mã công cả ngày" trên Loại nghỉ: mặt bàn để nhập, ghi ngược về `Attendance Code`.

`Attendance Code.leave_type` vẫn là NGUỒN SỰ THẬT DUY NHẤT — vì một loại nghỉ ứng với NHIỀU mã
(`P` và `1/2P` cùng trỏ "Nghỉ phép năm"), một ô đơn không chứa nổi cặp cả-ngày/nửa-ngày.

Test gọi thẳng hàm đồng bộ với doc-like object nên KHÔNG cần custom field tồn tại trên site —
tránh DDL trong harness rollback (DDL không rollback được, sẽ rò rỉ vào dữ liệu thật).

Chạy qua harness rollback (KHÔNG bench run-tests trên miyano).
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from hrms.hr.leave_type_code import full_day_code_for, sync_code_to_leave_type
from hrms.tests.isolation import PerTestRollback


class TestLeaveTypeCode(PerTestRollback, FrappeTestCase):
	def _leave_type(self, name):
		lt = frappe.get_doc({"doctype": "Leave Type", "leave_type_name": name, "is_lwp": 0})
		lt.insert(ignore_permissions=True)
		return lt

	def _code_link(self, code):
		return frappe.db.get_value("Attendance Code", code, "leave_type")

	def test_full_day_code_for_reads_attendance_code_table(self):
		"""Tra mã cả ngày của một loại nghỉ từ bảng Attendance Code."""
		self.assertEqual(full_day_code_for("Nghỉ phép năm"), "P")
		self.assertEqual(full_day_code_for("Nghỉ ốm"), "Ô")
		self.assertIsNone(full_day_code_for("Loại nghỉ không tồn tại"))

	def test_sync_writes_back_to_attendance_code(self):
		"""Chọn mã trên Loại nghỉ → Attendance Code.leave_type trỏ về loại nghỉ đó."""
		lt = self._leave_type("Nghỉ thử ghi ngược")
		# tạo một mã chưa gắn loại nghỉ nào
		frappe.get_doc(
			{
				"doctype": "Attendance Code",
				"code": "ZZ",
				"code_name": "Mã thử",
				"category": "Phép",
				"maps_to_status": "On Leave",
				"work_fraction": 0,
			}
		).insert(ignore_permissions=True)

		sync_code_to_leave_type(frappe._dict(name=lt.name, custom_attendance_code="ZZ"))

		self.assertEqual(self._code_link("ZZ"), lt.name)

	def test_sync_releases_previous_code(self):
		"""Đổi sang mã khác → mã cũ được gỡ liên kết, không còn hai mã cùng trỏ một loại nghỉ."""
		lt = self._leave_type("Nghỉ thử đổi mã")
		for code in ("ZZ", "YY"):
			frappe.get_doc(
				{
					"doctype": "Attendance Code",
					"code": code,
					"code_name": f"Mã thử {code}",
					"category": "Phép",
					"maps_to_status": "On Leave",
					"work_fraction": 0,
				}
			).insert(ignore_permissions=True)

		sync_code_to_leave_type(frappe._dict(name=lt.name, custom_attendance_code="ZZ"))
		self.assertEqual(self._code_link("ZZ"), lt.name)

		sync_code_to_leave_type(frappe._dict(name=lt.name, custom_attendance_code="YY"))
		self.assertEqual(self._code_link("YY"), lt.name)
		self.assertIsNone(self._code_link("ZZ"), "mã cũ phải được gỡ liên kết")

	def test_rejects_code_that_is_not_a_leave_status(self):
		"""Mã có maps_to_status ngoài {On Leave, Half Day} không phải mã nghỉ → chặn."""
		lt = self._leave_type("Nghỉ thử mã sai")
		# X = Present, không phải mã nghỉ
		with self.assertRaises(frappe.ValidationError):
			sync_code_to_leave_type(frappe._dict(name=lt.name, custom_attendance_code="X"))

	def test_empty_field_never_releases_the_code(self):
		"""Ô trống = "không nhập gì", KHÔNG phải "gỡ mã" — liên kết phải còn nguyên.

		Ô này chỉ là mặt bàn để nhập nên nó rỗng ở mọi lần lưu không đi qua form (script,
		`bench execute`, hoặc bấm Save trước khi kịp chọn mã). Coi rỗng là "gỡ" thì mã nghỉ mất
		đường tra ngược và bảng chấm công hiện sai. Gỡ thật thì sửa ở Attendance Code."""
		lt = self._leave_type("Nghỉ thử xoá trống")
		frappe.get_doc(
			{
				"doctype": "Attendance Code",
				"code": "ZZ",
				"code_name": "Mã thử",
				"category": "Phép",
				"maps_to_status": "On Leave",
				"work_fraction": 0,
			}
		).insert(ignore_permissions=True)
		sync_code_to_leave_type(frappe._dict(name=lt.name, custom_attendance_code="ZZ"))

		sync_code_to_leave_type(frappe._dict(name=lt.name, custom_attendance_code=None))
		self.assertEqual(self._code_link("ZZ"), lt.name)

	def test_real_leave_type_save_with_empty_field_keeps_the_map(self):
		"""SỰ CỐ THẬT 2026-08-03: lưu lại loạt Loại nghỉ đã gỡ liên kết của T/KH/R1/R2.

		Khác `test_real_leave_type_save_is_safe_before_migrate` (custom field CHƯA có): ở đây field
		đã migrate nhưng người/script lưu mà không đụng tới ô đó."""
		before = self._code_link("KH")
		self.assertEqual(before, "Nghỉ kết hôn", "tiền đề: KH đang trỏ Nghỉ kết hôn")

		sync_code_to_leave_type(frappe._dict(name="Nghỉ kết hôn", custom_attendance_code=None))

		self.assertEqual(self._code_link("KH"), "Nghỉ kết hôn")

	def test_half_day_code_is_accepted(self):
		"""1/2P là mã nghỉ hợp lệ (maps_to_status = Half Day)."""
		lt = self._leave_type("Nghỉ thử nửa ngày")
		sync_code_to_leave_type(frappe._dict(name=lt.name, custom_attendance_code="1/2P"))
		self.assertEqual(self._code_link("1/2P"), lt.name)

	def test_real_leave_type_save_is_safe_before_migrate(self):
		"""TRẠNG THÁI HIỆN TẠI CỦA PROD: custom field chưa migrate.

		Lưu một Loại nghỉ thật khi đó KHÔNG được đụng tới map sẵn có — nếu hook cứ chạy, `doc.get`
		trả None và vòng dọn sẽ xoá sạch liên kết P ↔ Nghỉ phép năm."""
		before = self._code_link("P")
		self.assertEqual(before, "Nghỉ phép năm", "tiền đề: P đang trỏ Nghỉ phép năm")

		lt = frappe.get_doc("Leave Type", "Nghỉ phép năm")
		lt.max_continuous_days_allowed = 5  # sửa gì đó để kích hoạt on_update
		lt.save(ignore_permissions=True)

		self.assertEqual(self._code_link("P"), "Nghỉ phép năm", "map không được mất khi lưu Loại nghỉ")

	def test_sync_does_not_touch_attendance_records(self):
		"""Đổi map là sửa MASTER DATA — không được đụng vào ngày công đã ghi."""
		before = frappe.db.sql(
			"""SELECT name, status, leave_type, half_day_status, custom_attendance_code
			   FROM `tabAttendance` ORDER BY name"""
		)
		lt = self._leave_type("Nghỉ thử bất biến")
		sync_code_to_leave_type(frappe._dict(name=lt.name, custom_attendance_code="1/2P"))
		after = frappe.db.sql(
			"""SELECT name, status, leave_type, half_day_status, custom_attendance_code
			   FROM `tabAttendance` ORDER BY name"""
		)
		self.assertEqual(before, after)
