# Copyright (c) 2026, Miyano Việt Nam.
"""Giờ định mức suy từ CA và LỊCH LÀM VIỆC — không hardcode 8h, không đọc Holiday List.

Bối cảnh (báo cáo rà soát 2026-09-23, mục B2): `working_hours.get_standard_hours_map` tính định mức
= (số ngày trong tháng - số dòng của Holiday List) x 8h. Từ khi ngày nghỉ tuần được gỡ khỏi Holiday
List (14/09), danh sách đó chỉ còn ngày lễ, nên định mức tháng nhảy từ ~168h lên ~248h và cả công
ty bị báo "thiếu giờ".

Định mức là KỲ VỌNG CÓ MẶT: Σ giờ ca của những ngày phải đi làm, trừ ngày đã nghỉ có đơn.

Chạy qua harness rollback (KHÔNG bench run-tests trên miyano).
"""

from calendar import monthrange
from datetime import date

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import getdate

from hrms.hr.work_schedule import (
	scheduled_days_between,
	shift_hours_per_day,
	standard_hours_between,
	working_days_between,
)
from hrms.tests.isolation import PerTestRollback
from hrms.tests.work_calendar_fixture import BRIDGE_SAME_MONTH, COMPANY_HOLIDAY, build_scenario

JUNE = ("2027-06-01", "2027-06-30")


def weekdays_in(year: int, month: int) -> int:
	"""Số ngày T2-T6 của tháng — mốc đối chiếu độc lập với code đang đo."""
	last = monthrange(year, month)[1]
	return sum(1 for d in range(1, last + 1) if date(year, month, d).weekday() < 5)


class StandardHoursBase(PerTestRollback, FrappeTestCase):
	def setUp(self):
		self.scenario = build_scenario()
		self.company = self.scenario.company
		self.office = self.scenario.shifts["office"]
		self.emp = self.scenario.employees["A"]  # ca hành chính T2-T6
		self.set_shift_hours(self.office, "8:0:0", "17:30:0")
		self.set_shift_hours(self.scenario.shifts["six_day"], "8:0:0", "17:30:0")

	def set_shift_hours(self, shift, start, end, lunch=("12:0:0", "13:30:0")):
		frappe.db.set_value(
			"Shift Type",
			shift,
			{
				"start_time": start,
				"end_time": end,
				"custom_lunch_start": lunch[0],
				"custom_lunch_end": lunch[1],
			},
		)
		frappe.clear_cache(doctype="Shift Type")

	def mark(self, day, code):
		doc = frappe.get_doc(
			{
				"doctype": "Attendance",
				"employee": self.emp,
				"attendance_date": day,
				"company": self.company,
				"custom_attendance_code": code,
			}
		).insert()
		doc.submit()
		return doc


class TestShiftHours(StandardHoursBase):
	def test_shift_hours_subtract_the_lunch_window(self):
		"""8:00-17:30 trừ trưa 1,5h = 8,0h. Đây là con số mà hằng số 8.0 đang ăn may."""
		self.assertEqual(shift_hours_per_day(self.office), 8.0)

	def test_shift_hours_follow_the_shift_not_a_constant(self):
		"""Ca 8:00-17:00 trừ trưa 1,5h = 7,5h — chính là ca mà hardcode 8.0 nói dối."""
		self.set_shift_hours(self.office, "8:0:0", "17:0:0")
		self.assertEqual(shift_hours_per_day(self.office), 7.5)

	def test_shift_hours_fall_back_when_the_lunch_window_is_nonsense(self):
		"""Shift Type mới bị Frappe điền GIỜ HIỆN TẠI vào hai ô nghỉ trưa → khung rộng 0 giây.
		Phải rơi về khung mặc định, nếu không ca đó tính dư 1,5h mỗi ngày."""
		self.set_shift_hours(self.office, "8:0:0", "17:30:0", lunch=("11:25:08", "11:25:08"))
		self.assertEqual(shift_hours_per_day(self.office), 8.0)

	def test_no_shift_uses_the_fallback(self):
		"""Nhân viên không có ca vẫn phải có một định mức — 8h là lưới an toàn, không phải chính sách."""
		self.assertEqual(shift_hours_per_day(None), 8.0)

	def test_working_days_exclude_public_holidays(self):
		"""`scheduled_*` KỂ CẢ lễ (mẫu số lương); `working_*` thì KHÔNG (kỳ vọng có mặt)."""
		scheduled = scheduled_days_between(self.emp, *JUNE)
		working = working_days_between(self.emp, *JUNE)
		self.assertIn(getdate(COMPANY_HOLIDAY), scheduled)
		self.assertNotIn(getdate(COMPANY_HOLIDAY), working)
		self.assertEqual(len(working), len(scheduled) - 1)


class TestStandardHours(StandardHoursBase):
	def june_working_days(self):
		return weekdays_in(2027, 6) - 1  # trừ ngày lễ công ty 16/06 (thứ Tư)

	def test_standard_hours_are_working_days_times_shift_hours(self):
		"""Tháng 6/2027: 22 ngày T2-T6, trừ 1 ngày lễ = 21 ngày x 8,0h — KHÔNG phải 30 x 8."""
		self.assertEqual(standard_hours_between(self.emp, *JUNE), self.june_working_days() * 8.0)

	def test_standard_hours_follow_the_shift(self):
		"""Đổi ca sang 8:00-17:00 → định mức giảm đúng 0,5h mỗi ngày làm việc."""
		self.set_shift_hours(self.office, "8:0:0", "17:0:0")
		self.assertEqual(standard_hours_between(self.emp, *JUNE), self.june_working_days() * 7.5)

	def test_a_public_holiday_adds_nothing(self):
		"""Ngày lễ có lương nhưng KHÔNG kỳ vọng có mặt → không vào định mức giờ."""
		self.assertEqual(standard_hours_between(self.emp, COMPANY_HOLIDAY, COMPANY_HOLIDAY), 0.0)

	def test_a_make_up_day_counts_and_its_bridge_day_does_not(self):
		"""Nghỉ ghép thứ Sáu, làm bù thứ Bảy: ngày làm bù là ngày phải đi làm."""
		bridge_off, make_up = BRIDGE_SAME_MONTH
		self.assertEqual(standard_hours_between(self.emp, bridge_off, bridge_off), 0.0)
		self.assertEqual(standard_hours_between(self.emp, make_up, make_up), 8.0)

	def test_leave_days_are_taken_out(self):
		"""Nghỉ phép 2 ngày → định mức giảm đúng 2 x giờ ca.

		Không trừ thì người nghỉ phép đúng quy định luôn nằm trong danh sách thiếu giờ."""
		full = standard_hours_between(self.emp, *JUNE)
		self.mark("2027-06-01", "P")
		self.mark("2027-06-02", "K")
		self.assertEqual(standard_hours_between(self.emp, *JUNE), full - 2 * 8.0)

	def test_a_half_day_leave_takes_out_half_a_shift(self):
		full = standard_hours_between(self.emp, *JUNE)
		self.mark("2027-06-03", "1/2P")
		self.assertEqual(standard_hours_between(self.emp, *JUNE), full - 4.0)

	def test_an_absent_day_stays_in_the_standard(self):
		"""Vắng không phép là ngày ĐÁNG RA phải có mặt — chính là thứ định mức phải bắt được."""
		full = standard_hours_between(self.emp, *JUNE)
		self.mark("2027-06-04", "V")
		self.assertEqual(standard_hours_between(self.emp, *JUNE), full)

	def test_leave_can_be_kept_in_on_request(self):
		full = standard_hours_between(self.emp, *JUNE)
		self.mark("2027-06-07", "P")
		self.assertEqual(standard_hours_between(self.emp, *JUNE, exclude_leave=False), full)

	def test_a_six_day_shift_has_more_standard_hours(self):
		"""Hai người cùng Holiday List, khác ca → khác định mức. Định mức đi theo CA."""
		six_day = self.scenario.employees["B"]
		self.assertGreater(standard_hours_between(six_day, *JUNE), standard_hours_between(self.emp, *JUNE))

	def test_weekly_off_rows_in_the_holiday_list_change_nothing(self):
		"""Chốt chặn cho lỗi B2: định mức KHÔNG được phụ thuộc Holiday List còn hay hết dòng nghỉ
		cuối tuần. Thêm đủ 8 dòng T7/CN của tháng 6 vào danh sách — con số phải đứng yên."""
		before = standard_hours_between(self.emp, *JUNE)
		holiday_list = frappe.get_doc("Holiday List", self.scenario.holiday_list)
		for d in range(1, 31):
			day = date(2027, 6, d)
			if day.weekday() >= 5:
				holiday_list.append(
					"holidays", {"holiday_date": day, "description": "Nghỉ tuần", "weekly_off": 1}
				)
		holiday_list.flags.ignore_permissions = True
		frappe.flags.generating_work_calendar = True
		try:
			holiday_list.save()
		finally:
			frappe.flags.generating_work_calendar = False
		self.assertEqual(standard_hours_between(self.emp, *JUNE), before)


class TestStandardHoursConsumers(StandardHoursBase):
	"""Hai nơi tiêu thụ định mức phải dùng chung nguồn ở trên."""

	def test_the_kpi_map_uses_the_work_schedule(self):
		from hrms.hr.working_hours import get_standard_hours_map

		got = get_standard_hours_map(
			{"month": 6, "year": 2027, "company": self.company}, employees=[self.emp]
		)
		self.assertEqual(got, {self.emp: (weekdays_in(2027, 6) - 1) * 8.0})

	def test_the_report_row_uses_the_work_schedule(self):
		from hrms.hr.report.monthly_attendance_sheet.monthly_attendance_sheet import (
			set_standard_and_variance,
		)

		row = {"total_working_hours": 100.0}
		set_standard_and_variance(row, self.emp, *JUNE)
		standard = (weekdays_in(2027, 6) - 1) * 8.0
		self.assertEqual(row["standard_hours"], standard)
		self.assertEqual(row["variance"], round(100.0 - standard, 2))
