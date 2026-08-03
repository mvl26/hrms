# Copyright (c) 2026, Miyano Việt Nam.
"""Nút Đồng bộ mã công: dọn các ngày mà mã công lệch với status/leave_type.

Xem trước rồi mới áp — không tự ý sửa hàng loạt trên dữ liệu lương thật.

Chạy qua harness rollback (KHÔNG bench run-tests trên miyano).
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from hrms.hr.attendance_code_sync import apply_sync, preview_sync
from hrms.tests.isolation import PerTestRollback
from hrms.tests.vn_test_utils import test_employee


class TestAttendanceCodeSync(PerTestRollback, FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.year = 2099
		cls.emp = test_employee()
		cls.company = frappe.db.get_value("Employee", cls.emp, "company")

	def _mismatched(self, date, leave_type="Nghỉ ốm"):
		"""Ngày On Leave nhưng mã công kẹt ở V — đúng triệu chứng của sự cố."""
		att = frappe.get_doc(
			{
				"doctype": "Attendance",
				"employee": self.emp,
				"attendance_date": date,
				"company": self.company,
				"status": "Absent",
			}
		)
		att.insert(ignore_permissions=True)
		att.submit()
		# giả lập đúng cách upstream làm hỏng: db_set thẳng, không qua cầu nối
		att.db_set({"status": "On Leave", "leave_type": leave_type}, update_modified=False)
		return att

	def _filters(self, month=4):
		return {"month": month, "year": self.year, "company": self.company}

	def _row(self, name):
		return frappe.db.get_value(
			"Attendance",
			name,
			["status", "leave_type", "half_day_status", "custom_attendance_code", "custom_work_credit"],
			as_dict=True,
		)

	def test_preview_finds_the_mismatch(self):
		att = self._mismatched(f"{self.year}-04-05")
		rows = preview_sync(self._filters())
		hit = [r for r in rows["changes"] if r["attendance"] == att.name]
		self.assertEqual(len(hit), 1)
		self.assertEqual(hit[0]["old_code"], "V")
		self.assertEqual(hit[0]["new_code"], "Ô")

	def test_preview_writes_nothing(self):
		att = self._mismatched(f"{self.year}-04-06")
		preview_sync(self._filters())
		self.assertEqual(self._row(att.name).custom_attendance_code, "V", "xem trước không được ghi gì")

	def test_apply_fixes_only_display_fields(self):
		att = self._mismatched(f"{self.year}-04-07")
		before = self._row(att.name)

		rows = preview_sync(self._filters())
		apply_sync(rows["changes"], reason="Đồng bộ mã công theo loại nghỉ")

		after = self._row(att.name)
		self.assertEqual(after.custom_attendance_code, "Ô")
		# ba field payroll KHÔNG được đổi
		self.assertEqual(after.status, before.status)
		self.assertEqual(after.leave_type, before.leave_type)
		self.assertEqual(after.half_day_status, before.half_day_status)

	def test_apply_writes_correction_log(self):
		att = self._mismatched(f"{self.year}-04-08")
		rows = preview_sync(self._filters())
		apply_sync(rows["changes"], reason="Đồng bộ mã công theo loại nghỉ")

		log = frappe.get_all(
			"Attendance Correction Log",
			filters={"attendance": att.name},
			fields=["old_code", "new_code", "reason"],
		)
		self.assertEqual(len(log), 1)
		self.assertEqual((log[0].old_code, log[0].new_code), ("V", "Ô"))

	def test_correct_records_are_not_listed(self):
		"""Ngày đã đúng mã thì không xuất hiện trong danh sách đề xuất."""
		att = frappe.get_doc(
			{
				"doctype": "Attendance",
				"employee": self.emp,
				"attendance_date": f"{self.year}-04-09",
				"company": self.company,
				"status": "Present",
			}
		)
		att.insert(ignore_permissions=True)
		att.submit()

		rows = preview_sync(self._filters())
		self.assertNotIn(att.name, [r["attendance"] for r in rows["changes"]])

	def test_unmapped_leave_type_is_not_touched(self):
		"""Loại nghỉ chưa có mã: không đề xuất gì, tuyệt đối không bịa mã."""
		lt = frappe.get_doc(
			{"doctype": "Leave Type", "leave_type_name": "Nghỉ chưa map sync", "is_lwp": 0}
		)
		lt.insert(ignore_permissions=True)
		att = self._mismatched(f"{self.year}-04-10", leave_type=lt.name)

		rows = preview_sync(self._filters())
		self.assertNotIn(att.name, [r["attendance"] for r in rows["changes"]])

	def test_locked_period_is_skipped_not_crashed(self):
		"""Kỳ đã chốt: xếp vào `skipped` kèm lý do, KHÔNG được ném lỗi làm vỡ cả lượt."""
		att = self._mismatched(f"{self.year}-04-11")
		rows = preview_sync(self._filters())
		change = next(r for r in rows["changes"] if r["attendance"] == att.name)

		# chốt kỳ tháng 4
		sheet = frappe.get_doc(
			{
				"doctype": "Monthly Attendance Sheet",
				"company": self.company,
				"month": "4",
				"year": self.year,
			}
		)
		sheet.insert(ignore_permissions=True)
		sheet.submit()

		result = apply_sync([change], reason="Thử kỳ đã chốt")
		self.assertEqual(result["applied"], 0)
		self.assertEqual(len(result["skipped"]), 1)
		self.assertIn(att.name, result["skipped"][0]["attendance"])
		self.assertEqual(self._row(att.name).custom_attendance_code, "V", "kỳ khoá thì không được sửa")

	def test_manual_half_day_codes_are_left_alone(self):
		"""Người dùng đã nhập mã theo buổi → không đè ý định của họ."""
		att = self._mismatched(f"{self.year}-04-12")
		frappe.db.set_value("Attendance", att.name, "custom_morning_code", "X", update_modified=False)

		rows = preview_sync(self._filters())
		self.assertNotIn(att.name, [r["attendance"] for r in rows["changes"]])
