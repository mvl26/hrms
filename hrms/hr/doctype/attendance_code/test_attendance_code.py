# Copyright (c) 2026, Miyano Việt Nam.
import frappe
from frappe.tests.utils import FrappeTestCase

from hrms.tests.isolation import PerTestRollback


def create_attendance_code(code, **kwargs):
	"""Insert (or replace) an Attendance Code for tests."""
	if frappe.db.exists("Attendance Code", code):
		frappe.delete_doc("Attendance Code", code, force=True)
	doc = frappe.get_doc(
		{
			"doctype": "Attendance Code",
			"code": code,
			"code_name": kwargs.pop("code_name", code),
			"category": kwargs.pop("category", "Công"),
			"maps_to_status": kwargs.pop("maps_to_status", "Present"),
		}
	)
	doc.update(kwargs)
	return doc.insert()


class TestAttendanceCode(PerTestRollback, FrappeTestCase):
	def fresh_leave_type(self, name):
		"""Loại nghỉ CHƯA có mã nào trỏ tới — dùng loại nghỉ thật (Nghỉ ốm, Nghỉ phép năm) thì chính
		bước dựng dữ liệu đã vi phạm luật duy nhất, và test xanh/đỏ vì sai lý do."""
		frappe.get_doc({"doctype": "Leave Type", "leave_type_name": name, "is_lwp": 0}).insert(
			ignore_permissions=True
		)
		return name

	def test_record_is_named_after_its_code(self):
		doc = create_attendance_code("X", code_name="Công đủ ngày")
		self.assertEqual(doc.name, "X")
		self.assertEqual(doc.code_name, "Công đủ ngày")

	def test_defaults_full_paid_work_day(self):
		doc = create_attendance_code("XD")
		self.assertEqual(doc.work_fraction, 1)
		self.assertEqual(doc.is_paid, 1)

	def test_code_must_be_unique(self):
		create_attendance_code("P", maps_to_status="On Leave")
		with self.assertRaises(frappe.exceptions.DuplicateEntryError):
			frappe.get_doc(
				{
					"doctype": "Attendance Code",
					"code": "P",
					"code_name": "duplicate",
					"category": "Phép",
					"maps_to_status": "On Leave",
				}
			).insert()

	def test_maps_to_status_is_mandatory(self):
		doc = frappe.get_doc({"doctype": "Attendance Code", "code": "NN", "code_name": "no status"})
		with self.assertRaises(frappe.exceptions.MandatoryError):
			doc.insert()

	def test_leave_type_is_optional(self):
		doc = create_attendance_code("K", maps_to_status="Absent", work_fraction=0, is_paid=0)
		self.assertIn(doc.leave_type, (None, ""))
		self.assertEqual(doc.work_fraction, 0)
		self.assertEqual(doc.is_paid, 0)

	def test_rejects_second_code_for_the_same_leave_type_and_status(self):
		"""Bất biến HR yêu cầu: 1 mã ↔ 1 (trạng thái, loại nghỉ).

		Hai mã cùng cặp thì reverse-derive phải ĐOÁN xem ngày nghỉ đó hiện mã nào — và `P` với một
		mã lạ nào đó không thay thế được cho nhau."""
		lt = self.fresh_leave_type("Nghỉ thử trùng mã")
		create_attendance_code(
			"ZP", maps_to_status="On Leave", category="Phép", leave_type=lt, work_fraction=0
		)
		with self.assertRaises(frappe.ValidationError):
			create_attendance_code(
				"ZQ", maps_to_status="On Leave", category="Phép", leave_type=lt, work_fraction=0
			)

	def test_allows_same_leave_type_on_a_different_status(self):
		"""Cặp cả-ngày/nửa-ngày (P và 1/2P) là hợp lệ — chúng khác `maps_to_status`."""
		lt = self.fresh_leave_type("Nghỉ thử cặp mã")
		create_attendance_code(
			"ZH", maps_to_status="Half Day", category="Ốm", leave_type=lt, work_fraction=0.5
		)
		doc = create_attendance_code(
			"ZF", maps_to_status="On Leave", category="Ốm", leave_type=lt, work_fraction=0
		)
		self.assertEqual(doc.name, "ZF")

	def test_allows_many_codes_without_a_leave_type(self):
		"""Mã đi làm (X, CT, W) không có loại nghỉ — luật duy nhất KHÔNG được áp cho chúng."""
		create_attendance_code("ZW", maps_to_status="Work From Home", category="Công")
		doc = create_attendance_code("ZV", maps_to_status="Work From Home", category="Công")
		self.assertEqual(doc.name, "ZV")

	def test_allows_an_on_leave_code_not_linked_yet(self):
		"""Mã nghỉ phải tạo được lúc CHƯA gắn loại nghỉ — form Loại nghỉ chọn mã đã tồn tại.

		Bắt buộc `leave_type` ở đây là bế tắc con-gà-quả-trứng (xem spec §3.2)."""
		doc = create_attendance_code("ZU", maps_to_status="On Leave", category="Phép", work_fraction=0)
		self.assertIsNone(doc.leave_type)

	def test_all_fixture_codes_pass_validation(self):
		"""17 mã đang có trên site phải qua được — nếu không, `bench migrate` re-sync fixtures sẽ vỡ."""
		for name in frappe.get_all("Attendance Code", pluck="name"):
			frappe.get_doc("Attendance Code", name).validate()
