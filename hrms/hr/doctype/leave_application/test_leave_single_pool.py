# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# See license.txt
"""Quỹ phép năm: đơn rút "Nghỉ phép năm" **bắt buộc chọn Loại nghỉ** — CHỈ còn "Nghỉ phép năm" → P.
Nghỉ ốm / chăm con ốm KHÔNG rút quỹ phép năm (loại nghỉ riêng, có lương, đủ công). Nghỉ nửa ngày phải
chọn buổi (Sáng/Chiều).

Chạy qua harness rollback (KHÔNG bench run-tests trên miyano)."""

import frappe
from frappe.tests.utils import FrappeTestCase

from hrms.tests.isolation import PerTestRollback


class TestLeaveSinglePool(PerTestRollback, FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.year = 2099
		# Phải là nhân viên mà bảng công tháng THỰC SỰ render, không phải "Active" bất kỳ:
		# get_employees() chỉ lấy người vào làm trước cuối kỳ và chưa nghỉ việc trước đầu kỳ.
		# Site có sẵn dữ liệu (test_site của CI) dễ trả về người đã có relieving_date, khi đó
		# get_sheet_rows không có dòng nào cho họ và test vỡ bằng StopIteration.
		cls.emp = frappe.db.get_value(
			"Employee",
			{
				"status": "Active",
				"date_of_joining": ["<=", f"{cls.year}-01-01"],
				"relieving_date": ["is", "not set"],
			},
			"name",
		)
		if not cls.emp:
			raise AssertionError("site không có nhân viên đang làm việc nào để dựng bảng công")
		cls.company = frappe.db.get_value("Employee", cls.emp, "company")

	def _alloc(self, leave_type, days):
		a = frappe.get_doc(
			{
				"doctype": "Leave Allocation",
				"employee": self.emp,
				"leave_type": leave_type,
				"from_date": f"{self.year}-01-01",
				"to_date": f"{self.year}-12-31",
				"new_leaves_allocated": days,
				"company": self.company,
			}
		)
		a.insert(ignore_permissions=True)
		a.submit()
		return a

	def _leave_app(self, leave_type, from_d, to_d, reason=None, half_day=0, period=None):
		la = frappe.get_doc(
			{
				"doctype": "Leave Application",
				"employee": self.emp,
				"leave_type": leave_type,
				"from_date": from_d,
				"to_date": to_d,
				"company": self.company,
				"status": "Approved",
				"half_day": half_day,
			}
		)
		if reason:
			la.custom_leave_reason = reason
		if period:
			la.custom_half_day_period = period
		la.insert(ignore_permissions=True)
		la.submit()
		return la

	def _att(self, la):
		return frappe.db.get_value(
			"Attendance",
			{"leave_application": la.name},
			[
				"status",
				"leave_type",
				"half_day_status",
				"custom_attendance_code",
				"custom_morning_code",
				"custom_afternoon_code",
			],
			as_dict=True,
		)

	def test_annual_leave_reason_creates_P_attendance(self):
		self._alloc("Nghỉ phép năm", 12)
		la = self._leave_app(
			"Nghỉ phép năm", f"{self.year}-03-05", f"{self.year}-03-05", reason="Nghỉ phép năm"
		)
		att = self._att(la)
		self.assertIsNotNone(att, "đơn duyệt phải sinh Attendance")
		self.assertEqual(att.status, "On Leave")
		self.assertEqual(att.leave_type, "Nghỉ phép năm")
		self.assertEqual(att.custom_attendance_code, "P")

	def test_sick_and_child_sick_rejected_from_pool(self):
		# Miyano: nghỉ ốm / chăm con ốm KHÔNG rút quỹ phép năm nữa → không còn là Loại nghỉ hợp lệ của quỹ.
		self._alloc("Nghỉ phép năm", 12)
		for reason in ("Nghỉ ốm", "Nghỉ chăm con ốm"):
			with self.assertRaises(frappe.ValidationError):
				self._leave_app("Nghỉ phép năm", f"{self.year}-03-06", f"{self.year}-03-06", reason=reason)

	def test_sick_via_own_leave_type_does_not_touch_annual_pool(self):
		# nghỉ ốm nộp bằng loại nghỉ riêng "Nghỉ ốm": KHÔNG giảm quỹ phép năm, có lương (is_lwp=0),
		# bảng công vẫn hiện Ô (bridge reverse suy mã), và đếm vào Tổng công (đủ công).
		from hrms.hr.doctype.leave_application.leave_application import get_leave_balance_on
		from hrms.hr.report.monthly_attendance_report.monthly_attendance_report import get_sheet_rows

		self._alloc("Nghỉ phép năm", 12)
		self._alloc("Nghỉ ốm", 30)
		before = get_leave_balance_on(self.emp, "Nghỉ phép năm", f"{self.year}-03-06")
		la = self._leave_app("Nghỉ ốm", f"{self.year}-03-06", f"{self.year}-03-06")
		after = get_leave_balance_on(self.emp, "Nghỉ phép năm", f"{self.year}-03-06")
		self.assertEqual(before, after)  # quỹ phép năm KHÔNG đổi
		att = self._att(la)
		self.assertEqual(att.leave_type, "Nghỉ ốm")
		self.assertEqual(att.custom_attendance_code, "Ô")
		self.assertEqual(frappe.db.get_value("Leave Type", "Nghỉ ốm", "is_lwp"), 0)  # có lương
		# đủ công: ngày ốm tính vào Tổng công (số ngày được trả lương)
		row = next(r for r in get_sheet_rows({"month": 3, "year": self.year}) if r["employee"] == self.emp)
		self.assertEqual(row["days"][6], "Ô")
		self.assertGreaterEqual(row["totals"].get("Tổng công", 0), 1.0)

	def test_pool_requires_reason(self):
		# đơn rút quỹ phép năm KHÔNG chọn Loại nghỉ → chặn (field bắt buộc).
		self._alloc("Nghỉ phép năm", 12)
		with self.assertRaises(frappe.ValidationError):
			self._leave_app("Nghỉ phép năm", f"{self.year}-03-07", f"{self.year}-03-07")  # thiếu loại nghỉ

	def test_pool_rejects_invalid_reason(self):
		# Loại nghỉ ngoài 3 loại trừ-quỹ (vd nhập thai sản) → chặn.
		self._alloc("Nghỉ phép năm", 12)
		with self.assertRaises(frappe.ValidationError):
			self._leave_app(
				"Nghỉ phép năm", f"{self.year}-03-08", f"{self.year}-03-08", reason="Nghỉ thai sản"
			)

	def test_blocks_when_pool_exhausted(self):
		# hết quỹ → Frappe chặn nộp đơn (số dư âm, allow_negative=0). "không cho xin phép nghỉ".
		self._alloc("Nghỉ phép năm", 1)
		with self.assertRaises(frappe.ValidationError):
			self._leave_app(
				"Nghỉ phép năm", f"{self.year}-03-10", f"{self.year}-03-11", reason="Nghỉ phép năm"
			)  # 2 > 1

	def test_annual_pool_leave_is_paid(self):
		# ngày rút quỹ phép năm là On Leave, có lương (is_lwp=0) → không trừ lương.
		self._alloc("Nghỉ phép năm", 12)
		p = self._att(
			self._leave_app(
				"Nghỉ phép năm", f"{self.year}-04-05", f"{self.year}-04-05", reason="Nghỉ phép năm"
			)
		)
		self.assertEqual((p.status, p.leave_type), ("On Leave", "Nghỉ phép năm"))
		self.assertEqual(frappe.db.get_value("Leave Type", "Nghỉ phép năm", "is_lwp"), 0)  # có lương

	def test_exempt_leave_does_not_touch_annual_pool(self):
		# thai sản (miễn trừ) dùng loại nghỉ riêng, KHÔNG giảm quỹ phép năm, KHÔNG cần chọn Loại nghỉ.
		from hrms.hr.doctype.leave_application.leave_application import get_leave_balance_on

		self._alloc("Nghỉ phép năm", 12)
		self._alloc("Nghỉ thai sản", 180)
		before = get_leave_balance_on(self.emp, "Nghỉ phép năm", f"{self.year}-05-02")
		la = self._leave_app("Nghỉ thai sản", f"{self.year}-05-02", f"{self.year}-05-02")
		after = get_leave_balance_on(self.emp, "Nghỉ phép năm", f"{self.year}-05-02")
		self.assertEqual(before, after)  # quỹ phép năm không đổi
		self.assertEqual(self._att(la).custom_attendance_code, "TS")  # hiện mã thai sản

	def test_half_day_morning_leave_uses_single_token(self):
		# nghỉ nửa ngày buổi Sáng: mã CHUẨN là token đơn 1/2P (không tách P/X); payroll = Half Day.
		self._alloc("Nghỉ phép năm", 12)
		la = self._leave_app(
			"Nghỉ phép năm",
			f"{self.year}-07-01",
			f"{self.year}-07-01",
			reason="Nghỉ phép năm",
			half_day=1,
			period="Sáng",
		)
		att = self._att(la)
		self.assertEqual(att.status, "Half Day")  # payroll: nửa ngày
		self.assertEqual(att.custom_attendance_code, "1/2P")  # nghỉ phép nửa ngày + nửa ngày đi làm
		self.assertIsNone(att.custom_morning_code)
		self.assertIsNone(att.custom_afternoon_code)

	def test_half_day_afternoon_leave_uses_single_token(self):
		# nghỉ nửa ngày buổi Chiều → cùng token đơn 1/2P (không phân biệt sáng/chiều ở hiển thị).
		self._alloc("Nghỉ phép năm", 12)
		la = self._leave_app(
			"Nghỉ phép năm",
			f"{self.year}-07-02",
			f"{self.year}-07-02",
			reason="Nghỉ phép năm",
			half_day=1,
			period="Chiều",
		)
		att = self._att(la)
		self.assertEqual(att.status, "Half Day")
		self.assertEqual(att.custom_attendance_code, "1/2P")
		self.assertIsNone(att.custom_morning_code)
		self.assertIsNone(att.custom_afternoon_code)

	def test_half_day_requires_period(self):
		# nửa ngày mà không chọn buổi (Sáng/Chiều) → chặn.
		self._alloc("Nghỉ phép năm", 12)
		with self.assertRaises(frappe.ValidationError):
			self._leave_app(
				"Nghỉ phép năm",
				f"{self.year}-07-05",
				f"{self.year}-07-05",
				reason="Nghỉ phép năm",
				half_day=1,
			)
