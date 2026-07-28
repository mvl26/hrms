# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# See license.txt
"""VN auto morning/afternoon classifier + its Shift Type config fields."""

import frappe
from frappe.tests.utils import FrappeTestCase

SHIFT_FIELDS = (
	"custom_split_half_day",
	"custom_lunch_start",
	"custom_lunch_end",
	"custom_half_day_min_fraction",
	"custom_half_day_grace_minutes",
)


class TestVNHalfDayClassifier(FrappeTestCase):
	def test_shift_type_config_fields_exist(self):
		for fn in SHIFT_FIELDS:
			self.assertTrue(
				frappe.db.exists("Custom Field", f"Shift Type-{fn}"), f"missing Custom Field Shift Type-{fn}"
			)


class TestVNHalfDayLogic(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.emp = frappe.db.get_value("Employee", {"status": "Active"}, "name")
		cls.shift = "VN Split 08-1730 (test)"
		if not frappe.db.exists("Shift Type", cls.shift):
			frappe.get_doc(
				{
					"doctype": "Shift Type",
					"__newname": cls.shift,
					"start_time": "08:00:00",
					"end_time": "17:30:00",
					"custom_split_half_day": 1,
					"custom_lunch_start": "12:00:00",
					"custom_lunch_end": "13:30:00",
					"custom_half_day_min_fraction": 0.5,
					"custom_half_day_grace_minutes": 15,
				}
			).insert()
		cls.day = frappe.utils.getdate("2099-03-04")

	def _cls(self, in_hm, out_hm, shift="__default__", **extra):
		doc = frappe.get_doc(
			{
				"doctype": "Attendance",
				"employee": self.emp,
				"attendance_date": self.day,
				"shift": self.shift if shift == "__default__" else shift,
				"in_time": f"{self.day} {in_hm}:00",
				"out_time": f"{self.day} {out_hm}:00",
				**extra,
			}
		)
		doc.before_validate()
		return doc

	def test_full_day(self):
		d = self._cls("08:00", "17:30")
		self.assertEqual(d.status, "Present")
		self.assertEqual(d.custom_work_credit, 1.0)
		self.assertEqual(d.custom_attendance_code, "X")  # cả ngày đi làm → MỘT mã đơn (không X/X)
		self.assertEqual(d.working_hours, 8.0)  # 4h morning + 4h afternoon, lunch excluded

	def test_morning_only(self):
		# làm buổi sáng, nửa còn lại là nghỉ KHÔNG LƯƠNG → mã CHUẨN token đơn 1/2K (không tách X/K).
		d = self._cls("08:00", "12:00")
		self.assertEqual(d.status, "Half Day")
		self.assertEqual(d.half_day_status, "Present")  # nửa đi làm là Present; nửa K trừ qua LWP
		self.assertEqual(d.leave_type, "Nghỉ không lương")
		self.assertEqual(d.custom_work_credit, 0.5)
		self.assertEqual(d.custom_attendance_code, "1/2K")
		self.assertIsNone(d.custom_morning_code)
		self.assertIsNone(d.custom_afternoon_code)
		self.assertEqual(d.working_hours, 4.0)

	def test_afternoon_only(self):
		# làm buổi chiều → cùng token đơn 1/2K (không phân biệt sáng/chiều ở phần hiển thị)
		d = self._cls("13:30", "17:30")
		self.assertEqual(d.status, "Half Day")
		self.assertEqual(d.custom_attendance_code, "1/2K")
		self.assertIsNone(d.custom_morning_code)
		self.assertEqual(d.leave_type, "Nghỉ không lương")
		self.assertEqual(d.custom_work_credit, 0.5)

	def test_early_leave_below_threshold_is_half_day(self):
		# leaves 15:00: afternoon coverage 13:30-15:15(grace) = 1.75h/4h = 44% < 50% -> morning only
		d = self._cls("08:00", "15:00")
		self.assertEqual(d.status, "Half Day")
		self.assertEqual(d.custom_attendance_code, "1/2K")
		self.assertEqual(d.working_hours, 5.5)  # 4h morning + 1.5h afternoon (actual overlap, no grace)

	def test_no_session_is_absent(self):
		d = self._cls("12:10", "13:20")  # entirely inside lunch
		self.assertEqual(d.status, "Absent")
		self.assertEqual(d.custom_attendance_code, "V")

	def test_gated_off_without_split_shift(self):
		# no split shift -> classifier is a no-op; a morning-only in/out is NOT reclassified
		d = self._cls("08:00", "12:00", shift=None, status="Present")
		self.assertIsNone(d.get("custom_morning_code"))
		self.assertEqual(d.status, "Present")

	def test_manual_code_wins(self):
		d = self._cls("08:00", "12:00", custom_attendance_code="P")
		self.assertEqual(d.status, "On Leave")
		self.assertEqual(d.leave_type, "Nghỉ phép năm")

	def test_half_day_leave_keeps_its_leave_type_when_the_other_half_is_worked(self):
		"""Nửa ngày phép + nửa ngày đi làm: bộ phân loại KHÔNG được xoá `leave_type`.

		A half-day Leave Application marks Attendance as Half Day + leave_type. If check-in times are
		then present on that record, the classifier would re-derive both halves from the clock alone
		and the bridge would rewrite leave_type from the (leave-less) 'V' code — silently dropping the
		employee's annual leave, which payroll reads."""
		d = self._cls(
			"13:30",
			"17:30",
			status="Half Day",
			leave_type="Nghỉ phép năm",
			half_day_status="Present",
		)

		self.assertEqual(d.status, "Half Day")
		self.assertEqual(d.leave_type, "Nghỉ phép năm")

	def test_a_full_day_of_leave_is_never_reclassified_from_the_clock(self):
		d = self._cls("13:30", "17:30", status="On Leave", leave_type="Nghỉ ốm")

		self.assertEqual(d.status, "On Leave")
		self.assertEqual(d.leave_type, "Nghỉ ốm")
