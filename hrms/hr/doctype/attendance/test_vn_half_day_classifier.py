# Copyright (c) 2026, Miyano Việt Nam.
"""Tầng Document của bộ phân loại VN: chốt chặn, đọc cấu hình ca, và chuỗi mã → field payroll.

Bản thân LUẬT (ca trượt, giờ net, X / 1/2X / V) được test đầy đủ ở `test_vn_day_classifier.py`
dưới dạng hàm thuần — không cần DB. Ở đây chỉ kiểm phần ráp nối.
"""

from datetime import timedelta

import frappe
from frappe.tests.utils import FrappeTestCase

from hrms.tests.isolation import PerTestRollback
from hrms.tests.vn_test_utils import ensure_short_hours_code, test_employee

SHIFT_FIELDS = (
	"custom_split_half_day",
	"custom_lunch_start",
	"custom_lunch_end",
	"custom_flexible_shift",
	"custom_flex_band_minutes",
	"custom_min_work_hours",
)


class TestVNHalfDayClassifier(PerTestRollback, FrappeTestCase):
	def test_shift_type_config_fields_exist(self):
		for fn in SHIFT_FIELDS:
			self.assertTrue(
				frappe.db.exists("Custom Field", f"Shift Type-{fn}"), f"missing Custom Field Shift Type-{fn}"
			)


class TestVNHalfDayLogic(PerTestRollback, FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.emp = test_employee()
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
				}
			).insert()
		ensure_short_hours_code()
		# 2099-03-04 là thứ Tư — ngày thường, để chốt chặn ngày nghỉ không nuốt mất test
		cls.day = frappe.utils.getdate("2099-03-04")

	def cls_doc(self, in_hm, out_hm, shift="__default__", day=None, **extra):
		d = day or self.day
		doc = frappe.get_doc(
			{
				"doctype": "Attendance",
				"employee": self.emp,
				"attendance_date": d,
				"shift": self.shift if shift == "__default__" else shift,
				"in_time": f"{d} {in_hm}:00",
				"out_time": f"{d} {out_hm}:00",
				**extra,
			}
		)
		doc.before_validate()
		return doc

	def test_full_day(self):
		d = self.cls_doc("08:00", "17:30")
		self.assertEqual(d.status, "Present")
		self.assertEqual(d.custom_work_credit, 1.0)
		self.assertEqual(d.custom_attendance_code, "X")  # cả ngày đi làm → MỘT mã đơn (không X/X)
		self.assertEqual(d.working_hours, 8.0)

	def test_short_hours_is_half_day_without_a_fake_leave(self):
		"""Thiếu giờ → 1/2X: Half Day, KHÔNG gắn loại nghỉ (trước đây bịa ra 'Nghỉ không lương')."""
		d = self.cls_doc("08:00", "12:00")
		self.assertEqual(d.working_hours, 4.0)
		self.assertEqual(d.custom_attendance_code, "1/2X")
		self.assertEqual(d.status, "Half Day")
		self.assertIsNone(d.leave_type)
		self.assertEqual(d.custom_work_credit, 0.5)
		self.assertIsNone(d.custom_morning_code)
		self.assertIsNone(d.custom_afternoon_code)

	def test_early_leave_is_short_hours(self):
		d = self.cls_doc("08:00", "15:00")
		self.assertEqual(d.working_hours, 5.5)
		self.assertEqual(d.custom_attendance_code, "1/2X")

	def test_no_worked_time_is_absent(self):
		d = self.cls_doc("12:10", "13:20")  # chỉ có mặt trong giờ nghỉ trưa
		self.assertEqual(d.working_hours, 0.0)
		self.assertEqual(d.custom_attendance_code, "V")
		self.assertEqual(d.status, "Absent")

	def test_gated_off_without_split_shift(self):
		"""Ca không bật tách buổi → bộ phân loại không chạy: không tính giờ, không đổi status.
		(Mã hiển thị "X" vẫn được cầu nối suy ngược từ status Present — đó là việc khác.)"""
		d = self.cls_doc("08:00", "12:00", shift=None, status="Present")
		self.assertIsNone(d.get("custom_morning_code"))
		self.assertFalse(d.get("working_hours"))
		self.assertEqual(d.status, "Present")

	def test_manual_code_wins(self):
		d = self.cls_doc("08:00", "12:00", custom_attendance_code="P")
		self.assertEqual(d.status, "On Leave")
		self.assertEqual(d.leave_type, "Nghỉ phép năm")

	def test_half_day_leave_keeps_its_leave_type_when_the_other_half_is_worked(self):
		"""Nửa ngày phép + nửa ngày đi làm: bộ phân loại KHÔNG được xoá `leave_type`.

		Nếu re-derive cả ngày từ đồng hồ thì cầu nối sẽ ghi đè leave_type bằng mã không mang phép
		→ mất phép của nhân viên, mà payroll thì đọc chính field đó."""
		d = self.cls_doc(
			"13:30", "17:30", status="Half Day", leave_type="Nghỉ phép năm", half_day_status="Present"
		)
		self.assertEqual(d.status, "Half Day")
		self.assertEqual(d.leave_type, "Nghỉ phép năm")

	def test_a_full_day_of_leave_is_never_reclassified_from_the_clock(self):
		d = self.cls_doc("13:30", "17:30", status="On Leave", leave_type="Nghỉ ốm")
		self.assertEqual(d.status, "On Leave")
		self.assertEqual(d.leave_type, "Nghỉ ốm")

	def test_holiday_is_never_auto_coded(self):
		"""Đi làm ngày nghỉ (T7/CN/lễ) không bị tự chấm — trước đây bị quy thành V hoặc nửa công."""
		holiday_list = frappe.db.get_value("Employee", self.emp, "holiday_list") or frappe.db.get_value(
			"Company", frappe.db.get_value("Employee", self.emp, "company"), "default_holiday_list"
		)
		self.assertTrue(holiday_list, "nhân viên phải có Holiday List thì mới test được nhánh này")
		holiday = frappe.db.get_value(
			"Holiday", {"parent": holiday_list}, "holiday_date", order_by="holiday_date desc"
		)
		d = self.cls_doc("09:00", "12:00", day=frappe.utils.getdate(holiday))
		self.assertIsNone(d.get("custom_attendance_code"))

	def test_half_day_code_docks_exactly_half_after_insert(self):
		"""Khoá cả 3 chặng: cầu nối đặt Present → check_leave_record ép Absent (không có đơn nghỉ)
		→ restore_code_driven_half_day_status KHÔNG hoàn tác vì mã không có leave_type.
		Payroll trừ 0,5 qua `get_half_absent_days`, nên chặng giữa mới là chặng quyết định."""
		doc = self.cls_doc("08:00", "12:00")
		doc.insert()
		self.assertEqual(doc.status, "Half Day")
		self.assertIsNone(doc.leave_type)
		self.assertEqual(doc.half_day_status, "Absent")
		self.assertEqual(doc.custom_work_credit, 0.5)


class TestLunchWindowFallback(PerTestRollback, FrappeTestCase):
	"""Khung nghỉ trưa rác của ca phải rơi về mặc định 12:00-13:30.

	Shift Type tạo mới mà không nhập giờ nghỉ trưa bị Frappe điền GIỜ HIỆN TẠI vào cả
	`custom_lunch_start` lẫn `custom_lunch_end` (ví dụ 11:25:08 → 11:25:08). Khung rộng 0 giây đó
	làm `classify_day` không trừ phút nghỉ trưa nào: ngày 08:00-17:30 được tính 9,5h thay vì 8,0h,
	tức ca cấu hình sai sẽ tính DƯ giờ công. `... or VN_DEFAULT_LUNCH_START` không bắt được vì giá
	trị có tồn tại, chỉ là vô nghĩa.
	"""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.emp = test_employee()
		cls.day = frappe.utils.getdate("2099-03-04")  # thứ Tư, ngày thường

	def test_resolve_keeps_a_valid_window(self):
		from hrms.hr.doctype.attendance.vn_day_classifier import resolve_lunch_window

		window = (timedelta(hours=11, minutes=30), timedelta(hours=12, minutes=30))
		self.assertEqual(resolve_lunch_window(*window), window)

	def test_resolve_falls_back_on_meaningless_windows(self):
		from hrms.hr.doctype.attendance.vn_day_classifier import (
			DEFAULT_LUNCH_END,
			DEFAULT_LUNCH_START,
			resolve_lunch_window,
		)

		default = (DEFAULT_LUNCH_START, DEFAULT_LUNCH_END)
		now = timedelta(hours=11, minutes=25, seconds=8)
		self.assertEqual(resolve_lunch_window(now, now), default)  # rộng 0 giây (Frappe điền now)
		self.assertEqual(resolve_lunch_window(timedelta(hours=14), timedelta(hours=12)), default)
		self.assertEqual(resolve_lunch_window(None, None), default)
		self.assertEqual(resolve_lunch_window(timedelta(hours=12), None), default)

	def test_shift_with_degenerate_lunch_window_still_deducts_lunch(self):
		shift = "VN Broken Lunch (test)"
		if not frappe.db.exists("Shift Type", shift):
			frappe.get_doc(
				{
					"doctype": "Shift Type",
					"__newname": shift,
					"start_time": "08:00:00",
					"end_time": "17:30:00",
					"custom_split_half_day": 1,
					"custom_lunch_start": "11:25:08",
					"custom_lunch_end": "11:25:08",
				}
			).insert()

		doc = frappe.get_doc(
			{
				"doctype": "Attendance",
				"employee": self.emp,
				"attendance_date": self.day,
				"shift": shift,
				"in_time": f"{self.day} 08:00:00",
				"out_time": f"{self.day} 17:30:00",
			}
		)
		doc.before_validate()

		self.assertEqual(doc.working_hours, 8.0)  # 9,5h - 1,5h mặc định, KHÔNG phải 9,5h
		self.assertEqual(doc.custom_attendance_code, "X")


class TestHolidayFollowsTheShiftSetting(PerTestRollback, FrappeTestCase):
	"""Cờ `Mark Auto Attendance on Holidays` của ca phải điều khiển TRỌN chuỗi.

	Chốt chặn ngày nghỉ của bộ phân loại sinh ra để người đi làm ngày nghỉ không bị quy thành V.
	Nhưng nếu công ty CHỦ ĐỘNG bật chấm công ngày nghỉ trên ca, thì ngày đó phải được chấm y như
	ngày thường: trừ nghỉ trưa, đủ giờ mới X. Không thì bật cờ xong ngày lễ đi đường riêng —
	`working_hours` là giờ thô chưa trừ trưa, và chấm 10 phút cũng thành X đủ công.
	"""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		ensure_short_hours_code()
		# TỰ DỰNG nhân viên, không vớ người có sẵn trên site: `get_value("Employee", {"status":
		# "Active"})` bám vào bất kỳ ai — hôm site có người bật cờ MIỄN CHẤM CÔNG thì test này đỏ oan
		# vì người đó luôn đủ công. Cùng bẫy đã vá ở 6 chỗ khác (commit 40331d5).
		cls.emp = test_employee("holiday_rule@codes.com")
		holiday_list = frappe.db.get_value(
			"Company", frappe.db.get_value("Employee", cls.emp, "company"), "default_holiday_list"
		)
		frappe.db.set_value("Employee", cls.emp, "holiday_list", holiday_list)
		cls.holiday = frappe.db.get_value(
			"Holiday",
			{"parent": holiday_list},
			"holiday_date",
			order_by="holiday_date desc",
		)

	def shift(self, mark_on_holidays: int) -> str:
		name = f"VN Holiday Rule {mark_on_holidays} (test)"
		if not frappe.db.exists("Shift Type", name):
			frappe.get_doc(
				{
					"doctype": "Shift Type",
					"__newname": name,
					"start_time": "08:00:00",
					"end_time": "17:30:00",
					"custom_split_half_day": 1,
					"custom_lunch_start": "12:00:00",
					"custom_lunch_end": "13:30:00",
					"custom_flexible_shift": 1,
					"custom_flex_band_minutes": 180,
					"custom_min_work_hours": 8,
					"mark_auto_attendance_on_holidays": mark_on_holidays,
				}
			).insert()
		return name

	def classify(self, mark_on_holidays: int, in_hm: str, out_hm: str):
		doc = frappe.get_doc(
			{
				"doctype": "Attendance",
				"employee": self.emp,
				"attendance_date": self.holiday,
				"shift": self.shift(mark_on_holidays),
				"in_time": f"{self.holiday} {in_hm}:00",
				"out_time": f"{self.holiday} {out_hm}:00",
			}
		)
		doc.before_validate()
		return doc

	def test_shift_that_does_not_mark_holidays_leaves_the_day_alone(self):
		d = self.classify(0, "09:00", "12:00")
		self.assertIsNone(d.get("custom_attendance_code"), "ngày nghỉ không tự chấm mã")

	def test_shift_that_marks_holidays_applies_the_normal_hours_rule(self):
		d = self.classify(1, "08:05", "18:40")
		self.assertEqual(d.custom_attendance_code, "X")
		self.assertAlmostEqual(d.working_hours, 9.08, places=2)  # 10h35 - 1h30 trưa, KHÔNG phải 10,58

	def test_a_short_stint_on_a_marked_holiday_is_not_a_full_day(self):
		"""Chấm 10 phút ngày lễ không được thành đủ công."""
		d = self.classify(1, "09:00", "09:10")
		self.assertEqual(d.custom_attendance_code, "1/2X")
