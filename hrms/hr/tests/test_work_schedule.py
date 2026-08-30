# Copyright (c) 2026, Miyano Việt Nam.
"""Lõi luật lịch tuần — thuần, không chạm DB nên chạy được bằng unittest trần."""

import unittest
from datetime import date

from hrms.hr.work_schedule import dates_in_range, scheduled_dates, weekday_set

MON_TO_FRI = frozenset({0, 1, 2, 3, 4})

# Số ngày T2-T6 của từng tháng năm 2026 — mốc đối chiếu cho mẫu số lương.
SCHEDULED_DAYS_2026 = [22, 20, 22, 22, 21, 22, 23, 21, 22, 22, 21, 23]
LAST_DAY_2026 = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]


class TestWorkScheduleRules(unittest.TestCase):
	def test_weekday_set_maps_english_day_names(self):
		self.assertEqual(weekday_set(["Monday", "Friday"]), frozenset({0, 4}))

	def test_weekday_set_ignores_unknown_names(self):
		"""Tên rác bị bỏ qua chứ không nổ: một dòng hỏng không được làm chết cả kỳ lương."""
		self.assertEqual(weekday_set(["Monday", "", None, "Xyz"]), frozenset({0}))

	def test_weekday_set_of_none_is_empty(self):
		self.assertEqual(weekday_set(None), frozenset())

	def test_dates_in_range_is_inclusive_both_ends(self):
		days = list(dates_in_range("2026-07-01", "2026-07-03"))
		self.assertEqual(days, [date(2026, 7, 1), date(2026, 7, 2), date(2026, 7, 3)])

	def test_dates_in_range_of_a_single_day(self):
		self.assertEqual(list(dates_in_range("2026-07-01", "2026-07-01")), [date(2026, 7, 1)])

	def test_july_2026_has_23_scheduled_days(self):
		"""Con số neo: cả 6 phiếu lương 07/2026 trên site đang có total_working_days = 23.0."""
		self.assertEqual(len(scheduled_dates(MON_TO_FRI, "2026-07-01", "2026-07-31")), 23)

	def test_scheduled_dates_excludes_the_weekend(self):
		self.assertEqual(scheduled_dates(MON_TO_FRI, "2026-07-25", "2026-07-26"), set())  # T7 + CN

	def test_every_month_of_2026(self):
		for month, want in enumerate(SCHEDULED_DAYS_2026, start=1):
			last = LAST_DAY_2026[month - 1]
			got = scheduled_dates(MON_TO_FRI, f"2026-{month:02d}-01", f"2026-{month:02d}-{last:02d}")
			self.assertEqual(len(got), want, f"tháng {month}")

	def test_empty_weekday_set_yields_no_scheduled_day(self):
		self.assertEqual(scheduled_dates(frozenset(), "2026-07-01", "2026-07-31"), set())

	def test_six_day_week_includes_saturday(self):
		"""Nhóm làm 6 ngày/tuần: mô hình phải diễn đạt được, dù Miyano chưa dùng."""
		six_days = MON_TO_FRI | {5}
		self.assertEqual(len(scheduled_dates(six_days, "2026-07-01", "2026-07-31")), 27)
