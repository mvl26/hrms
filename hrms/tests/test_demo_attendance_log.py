# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# See license.txt
"""Kịch bản của bộ sinh nhật ký chấm công: neo theo ngày công, và giờ giấc tái lập được.

Toàn bộ test ở đây là hàm thuần — không chạm DB, không sinh chứng từ.
"""

import datetime
import random

from frappe.tests.utils import FrappeTestCase

from hrms.demo_attendance_log import (
	ABSENT_DAYS,
	HALF_DAYS,
	OVERTIME_DAYS,
	clock_times,
	daterange,
	day_plan,
	leave_dates,
	month_bounds,
)

D = datetime.date
# Tháng 6/2026: mùng 1 là thứ Hai, không ngày lễ -> 26 ngày công, chỉ nghỉ Chủ nhật 7/14/21/28.
JUNE_2026_WORKDAYS = [d for d in daterange(D(2026, 6, 1), D(2026, 6, 30)) if d.weekday() != 6]


class TestDemoAttendanceLog(FrappeTestCase):
	def test_june_2026_has_26_workdays(self):
		self.assertEqual(len(JUNE_2026_WORKDAYS), 26)

	def test_leave_plan_lands_on_the_documented_june_2026_dates(self):
		"""Kịch bản neo theo thứ tự ngày công; docstring của module hứa các ngày dương lịch này."""
		for key, expected_days, expected_type in (
			("binh", [D(2026, 6, 15), D(2026, 6, 16), D(2026, 6, 17)], "Nghỉ phép năm"),
			("cuong", [D(2026, 6, 9), D(2026, 6, 10)], "Nghỉ ốm"),
			("dung", [D(2026, 6, 25)], "Nghỉ không lương"),
		):
			span, bounds = leave_dates(key, JUNE_2026_WORKDAYS)
			self.assertEqual(sorted(span), expected_days, msg=key)
			self.assertEqual(set(span.values()), {expected_type}, msg=key)
			self.assertEqual(bounds[0], expected_days[0], msg=key)
			self.assertEqual(bounds[1], expected_days[-1], msg=key)

	def test_half_day_and_absent_ordinals_land_on_the_documented_dates(self):
		self.assertEqual(JUNE_2026_WORKDAYS[next(iter(HALF_DAYS["cuong"])) - 1], D(2026, 6, 22))
		self.assertEqual(JUNE_2026_WORKDAYS[next(iter(HALF_DAYS["em"])) - 1], D(2026, 6, 18))
		self.assertEqual(JUNE_2026_WORKDAYS[next(iter(ABSENT_DAYS["dung"])) - 1], D(2026, 6, 4))

	def test_day_plan_gives_leave_absent_half_day_present(self):
		self.assertEqual(day_plan("binh", D(2026, 6, 15), 13, JUNE_2026_WORKDAYS)[0], "On Leave")
		self.assertEqual(day_plan("binh", D(2026, 6, 15), 13, JUNE_2026_WORKDAYS)[1], "Nghỉ phép năm")
		self.assertEqual(day_plan("dung", D(2026, 6, 4), 4, JUNE_2026_WORKDAYS)[0], "Absent")
		self.assertEqual(day_plan("cuong", D(2026, 6, 22), 19, JUNE_2026_WORKDAYS)[0], "Half Day")
		self.assertEqual(day_plan("an", D(2026, 6, 3), 3, JUNE_2026_WORKDAYS)[0], "Present")

	def test_a_leave_or_absent_day_produces_no_clock_times(self):
		for status in ("On Leave", "Absent"):
			self.assertEqual(clock_times("an", D(2026, 6, 3), 3, status, random.Random("x")), (None, None))

	def test_half_day_clocks_out_at_noon(self):
		_, out = clock_times("cuong", D(2026, 6, 22), 19, "Half Day", random.Random("x"))
		self.assertEqual(out, datetime.datetime(2026, 6, 22, 12, 0))

	def test_overtime_day_clocks_out_well_after_shift_end(self):
		ot_ordinal = sorted(OVERTIME_DAYS["an"])[0]
		day = JUNE_2026_WORKDAYS[ot_ordinal - 1]
		_, out = clock_times("an", day, ot_ordinal, "Present", random.Random("x"))
		self.assertGreaterEqual(out, datetime.datetime.combine(day, datetime.time(19, 0)))

	def test_clock_times_are_reproducible_for_the_same_seed(self):
		def run():
			rnd = random.Random("HR-EMP-00002")
			return [
				clock_times("an", d, i, "Present", rnd) for i, d in enumerate(JUNE_2026_WORKDAYS, start=1)
			]

		self.assertEqual(run(), run())

	def test_month_bounds_handles_december_rollover(self):
		self.assertEqual(month_bounds(2026, 12), (D(2026, 12, 1), D(2026, 12, 31)))
		self.assertEqual(month_bounds(2026, 2), (D(2026, 2, 1), D(2026, 2, 28)))
		self.assertEqual(month_bounds(2026, 6), (D(2026, 6, 1), D(2026, 6, 30)))
