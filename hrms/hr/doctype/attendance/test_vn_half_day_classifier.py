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
		cls.emp = frappe.db.get_value("Employee", {}, "name")
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
		self.assertEqual(d.working_hours, 8.0)  # 4h morning + 4h afternoon, lunch excluded

	def test_morning_only(self):
		d = self._cls("08:00", "12:00")
		self.assertEqual(d.status, "Half Day")
		self.assertEqual(d.half_day_status, "Absent")
		self.assertEqual(d.custom_work_credit, 0.5)
		self.assertEqual(d.custom_morning_code, "X")
		self.assertEqual(d.custom_afternoon_code, "V")
		self.assertEqual(d.working_hours, 4.0)

	def test_afternoon_only(self):
		d = self._cls("13:30", "17:30")
		self.assertEqual(d.status, "Half Day")
		self.assertEqual(d.custom_morning_code, "V")
		self.assertEqual(d.custom_afternoon_code, "X")
		self.assertEqual(d.custom_work_credit, 0.5)

	def test_early_leave_below_threshold_is_half_day(self):
		# leaves 15:00: afternoon coverage 13:30–15:15(grace) = 1.75h/4h = 44% < 50% -> morning only
		d = self._cls("08:00", "15:00")
		self.assertEqual(d.status, "Half Day")
		self.assertEqual(d.custom_afternoon_code, "V")
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
