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
		lt = frappe.get_doc({"doctype": "Leave Type", "leave_type_name": "Nghỉ chưa map sync", "is_lwp": 0})
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


class TestSyncKeepsValidCodes(PerTestRollback, FrappeTestCase):
	"""Đồng bộ KHÔNG được đè mã đang hợp lệ — nhiều mã chung một status, không thay nhau được.

	Lỗi 2026-08-05: `W` (làm tại nhà, do Yêu cầu chấm công sinh ra) và `CT` (đi công tác) đều mang
	status `Work From Home`; bộ đồng bộ luôn trả mã "chuẩn" `CT` nên bấm Đồng bộ là mọi ngày làm
	tại nhà bị đè thành đi công tác."""

	def row(self, code, status="Work From Home", leave_type=None):
		return frappe._dict(status=status, leave_type=leave_type, custom_attendance_code=code)

	def test_work_from_home_code_is_kept(self):
		from hrms.hr.attendance_code_sync import expected_code

		self.assertEqual(expected_code(self.row("W")), "W", "W đang hợp lệ → phải giữ, không hoá CT")

	def test_business_trip_code_is_kept_too(self):
		from hrms.hr.attendance_code_sync import expected_code

		self.assertEqual(expected_code(self.row("CT")), "CT")

	def test_a_code_that_contradicts_the_status_is_still_corrected(self):
		"""Đây mới là việc của bộ đồng bộ: V kẹt lại trên ngày đã thành đi làm."""
		from hrms.hr.attendance_code_sync import expected_code

		self.assertEqual(expected_code(self.row("V", status="Present")), "X")

	def test_empty_code_still_gets_filled(self):
		from hrms.hr.attendance_code_sync import expected_code

		self.assertEqual(expected_code(self.row(None, status="Present")), "X")


class TestSyncRespectsAttendanceRequestSource(PerTestRollback, FrappeTestCase):
	"""Ngày do Yêu cầu chấm công sinh ra: **phiếu là nguồn có thẩm quyền của mã**, không phải status.

	Lỗi thật (Lê Văn Cường 2026-07-14): phiếu lý do `On Duty` → upstream đặt `status = Present`
	(chỉ riêng lý do WFH mới ra status `Work From Home`), hook Miyano ghi mã `CT`. Nhưng
	`Attendance Code CT` khai `maps_to_status = Work From Home`, nên bộ đồng bộ tính
	`matching_codes(Present) = ['X']`, thấy CT không thuộc đó và đề xuất **CT → X** — xoá mất thông
	tin đi công tác có thật. Cùng họ với lỗi W-hoá-CT (2026-08-05), nhưng nguồn sai là PHIẾU chứ
	không phải status."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.year = 2095
		cls.emp = test_employee()
		cls.company = frappe.db.get_value("Employee", cls.emp, "company")

	def on_duty_day(self, date):
		"""Dựng đúng đường thật: phiếu Yêu cầu chấm công lý do On Duty, duyệt → sinh ngày công."""
		req = frappe.get_doc(
			{
				"doctype": "Attendance Request",
				"employee": self.emp,
				"from_date": date,
				"to_date": date,
				"reason": "On Duty",
				"company": self.company,
			}
		)
		req.insert(ignore_permissions=True)
		req.submit()
		return frappe.db.get_value(
			"Attendance",
			{"employee": self.emp, "attendance_date": date, "docstatus": ("<", 2)},
			["name", "status", "leave_type", "custom_attendance_code", "attendance_request"],
			as_dict=True,
		)

	def test_on_duty_day_is_present_with_ct_code(self):
		"""Tiền đề của lỗi: status là Present chứ không phải Work From Home."""
		row = self.on_duty_day(f"{self.year}-04-14")
		self.assertEqual(row.status, "Present")
		self.assertEqual(row.custom_attendance_code, "CT")

	def test_ct_from_an_on_duty_request_is_kept(self):
		from hrms.hr.attendance_code_sync import expected_code

		row = self.on_duty_day(f"{self.year}-04-15")
		self.assertEqual(expected_code(row), "CT", "phiếu On Duty quy định CT — không được hoá X")

	def test_preview_does_not_list_the_on_duty_day(self):
		date = f"{self.year}-04-16"
		self.on_duty_day(date)

		result = preview_sync({"month": 4, "year": self.year, "company": self.company})

		self.assertEqual(
			[c for c in result["changes"] if c["attendance_date"] == date],
			[],
			"ngày đi công tác đang đúng thì không được nằm trong danh sách đề xuất sửa",
		)

	def test_a_wiped_code_is_refilled_from_the_request(self):
		"""Mã bị xoá trên ngày có phiếu → điền lại theo PHIẾU (CT), không suy từ status (X)."""
		from hrms.hr.attendance_code_sync import expected_code

		row = self.on_duty_day(f"{self.year}-04-17")
		frappe.db.set_value("Attendance", row.name, "custom_attendance_code", None, update_modified=False)
		row.custom_attendance_code = None

		self.assertEqual(expected_code(row), "CT")

	def test_day_without_a_request_is_still_corrected(self):
		"""Không đụng việc chính của bộ đồng bộ: ngày KHÔNG có phiếu, mã lệch → vẫn sửa."""
		from hrms.hr.attendance_code_sync import expected_code

		row = frappe._dict(
			status="Present", leave_type=None, custom_attendance_code="V", attendance_request=None
		)
		self.assertEqual(expected_code(row), "X")
