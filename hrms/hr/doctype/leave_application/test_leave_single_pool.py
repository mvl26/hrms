# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# See license.txt
"""Bậc 2 — gộp một quỹ phép năm: đơn rút "Nghỉ phép năm" **bắt buộc chọn Loại nghỉ** (tiếng Việt);
hệ thống tự suy mã công (P/Ô/Cô) → bảng công hiện riêng. Nghỉ nửa ngày phải chọn buổi (Sáng/Chiều).

Chạy qua harness rollback (KHÔNG bench run-tests trên miyano)."""

import frappe
from frappe.tests.utils import FrappeTestCase


class TestLeaveSinglePool(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.emp = frappe.db.get_value("Employee", {"status": "Active"}, "name")
		cls.company = frappe.db.get_value("Employee", cls.emp, "company")
		cls.year = 2099

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

	def test_sick_reason_from_annual_pool_shows_O_but_deducts_pool(self):
		# "Nghỉ ốm" nộp qua quỹ phép năm: Attendance hiện "Ô" (bảng công), nhưng leave_type là quỹ chung
		# và status không đổi (payroll-neutral).
		self._alloc("Nghỉ phép năm", 12)
		la = self._leave_app("Nghỉ phép năm", f"{self.year}-03-06", f"{self.year}-03-06", reason="Nghỉ ốm")
		att = self._att(la)
		self.assertEqual(att.custom_attendance_code, "Ô")  # hiện riêng trên bảng công
		self.assertEqual(att.leave_type, "Nghỉ phép năm")  # rút một quỹ
		self.assertEqual(att.status, "On Leave")  # lương không đổi

		from hrms.hr.report.monthly_attendance_report.monthly_attendance_report import get_sheet_rows

		row = next(r for r in get_sheet_rows({"month": 3, "year": self.year}) if r["employee"] == self.emp)
		self.assertEqual(row["days"][6], "Ô")
		self.assertGreaterEqual(row["totals"].get("Ốm", 0), 1.0)

	def test_child_sick_reason_maps_to_Co(self):
		self._alloc("Nghỉ phép năm", 12)
		la = self._leave_app(
			"Nghỉ phép năm", f"{self.year}-03-09", f"{self.year}-03-09", reason="Nghỉ chăm con ốm"
		)
		self.assertEqual(self._att(la).custom_attendance_code, "Cô")

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

	def test_pool_display_code_is_payroll_neutral(self):
		# "Nghỉ ốm" rút quỹ phép năm phải giống hệt một ngày phép năm về các field payroll đọc (status/
		# leave_type/half_day_status) — chỉ khác custom_attendance_code (hiển thị). is_lwp của quỹ = 0.
		self._alloc("Nghỉ phép năm", 12)
		p = self._att(
			self._leave_app(
				"Nghỉ phép năm", f"{self.year}-04-05", f"{self.year}-04-05", reason="Nghỉ phép năm"
			)
		)
		o = self._att(
			self._leave_app("Nghỉ phép năm", f"{self.year}-04-06", f"{self.year}-04-06", reason="Nghỉ ốm")
		)
		self.assertEqual((p.status, p.leave_type), (o.status, o.leave_type))  # payroll đọc giống nhau
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

	def test_half_day_morning_leave_splits_codes(self):
		# nghỉ nửa ngày buổi Sáng: bảng công morning=P (nghỉ), afternoon=X (đi làm); payroll = Half Day.
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
		self.assertEqual(att.custom_morning_code, "P")  # nghỉ sáng
		self.assertEqual(att.custom_afternoon_code, "X")  # làm chiều

	def test_half_day_afternoon_leave_splits_codes(self):
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
		self.assertEqual(att.custom_morning_code, "X")  # làm sáng
		self.assertEqual(att.custom_afternoon_code, "P")  # nghỉ chiều

	def test_half_day_sick_morning_uses_reason_code(self):
		# nửa ngày ốm buổi sáng: morning=Ô, afternoon=X.
		self._alloc("Nghỉ phép năm", 12)
		la = self._leave_app(
			"Nghỉ phép năm",
			f"{self.year}-07-03",
			f"{self.year}-07-03",
			reason="Nghỉ ốm",
			half_day=1,
			period="Sáng",
		)
		att = self._att(la)
		self.assertEqual(att.custom_morning_code, "Ô")
		self.assertEqual(att.custom_afternoon_code, "X")

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
