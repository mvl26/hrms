# Copyright (c) 2026, Miyano Việt Nam.
"""Generator Holiday List VN — sau khi tách, danh sách CHỈ còn ngày nghỉ lễ.

Ngày làm việc trong tuần nay thuộc `Shift Type` (xem `hrms/hr/work_schedule.py`), nên generator
không sinh dòng `weekly_off` nào nữa. Quy tắc nghỉ bù (Điều 112 khoản 3) giữ nguyên, chỉ đổi chỗ
hỏi: hỏi lịch tuần thay vì hỏi cờ `weekly_off` của chính danh sách đang dựng.

Chạy qua harness rollback — mọi thay đổi đều được rollback.
"""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import getdate

from hrms.setup_vn_holiday import SOLAR_HOLIDAYS, create_vn_holiday_list
from hrms.tests.isolation import PerTestRollback
from hrms.tests.vn_test_utils import default_company

MON_TO_FRI = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]


class TestSetupVNHoliday(PerTestRollback, FrappeTestCase):
	def setUp(self):
		self.company = default_company()
		self.year = 2027
		self.set_company_weekdays(MON_TO_FRI)
		self.set_calendar_days([])

	def set_company_weekdays(self, days):
		frappe.db.delete(
			"Assignment Rule Day",
			{
				"parent": "Work Calendar Settings",
				"parenttype": "Work Calendar Settings",
				"parentfield": "default_working_days",
			},
		)
		for idx, day in enumerate(days, start=1):
			frappe.get_doc(
				{
					"doctype": "Assignment Rule Day",
					"parent": "Work Calendar Settings",
					"parenttype": "Work Calendar Settings",
					"parentfield": "default_working_days",
					"day": day,
					"idx": idx,
				}
			).insert(ignore_permissions=True)

	def set_calendar_days(self, rows):
		settings = frappe.get_single("Work Calendar Settings")
		settings.calendar_days = []
		for year, day, day_type, desc in rows:
			settings.append(
				"calendar_days",
				{"year": year, "holiday_date": day, "day_type": day_type, "description": desc},
			)
		settings.flags.ignore_permissions = True
		settings.save()

	def generate(self, year, extra=None):
		"""Sinh vào một Holiday List RIÊNG của test.

		Không mượn tên theo quy ước (`VN <company> <year>`): trên site thật lịch 2026 đang tồn tại và
		còn nguyên 104 dòng nghỉ cuối tuần của mô hình cũ, generator thì idempotent nên nó sẽ nạp lại
		đúng danh sách đó và test đo nhầm dữ liệu thật.
		"""
		return create_vn_holiday_list(year, self.company, name=f"_Test VN {year}", extra_holidays=extra)

	def dates(self, name):
		return {
			getdate(r.holiday_date): r.weekly_off
			for r in frappe.get_all(
				"Holiday",
				filters={"parent": name, "parenttype": "Holiday List"},
				fields=["holiday_date", "weekly_off"],
			)
		}

	# --- danh sách chỉ còn ngày lễ -------------------------------------------

	def test_generated_list_has_no_weekly_off_rows(self):
		"""Cốt lõi của đợt này: cuối tuần KHÔNG còn là dòng trong Holiday List."""
		name = self.generate(self.year)
		self.assertEqual(frappe.db.count("Holiday", {"parent": name, "weekly_off": 1}), 0)

	def test_solar_holidays_are_generated(self):
		name = self.generate(self.year)
		dates = self.dates(name)
		for mm, dd in SOLAR_HOLIDAYS:
			day = getdate(f"{self.year}-{mm:02d}-{dd:02d}")
			# lễ rơi vào T7/CN được dời thành nghỉ bù, nên chỉ đòi "có mặt hoặc có ngày bù"
			if day.weekday() < 5:
				self.assertIn(day, dates, f"thiếu lễ {day}")
				self.assertEqual(dates[day], 0)

	def test_every_holiday_row_lands_on_a_scheduled_day(self):
		"""BẤT BIẾN: dòng lễ chỉ nằm trên ngày làm việc.

		Nhờ đó một dòng lễ không bao giờ cộng khống một ngày công vào lương — `set_working_days`
		đếm ngày theo lịch tuần và ngày lễ phải nằm sẵn trong đó."""
		name = self.generate(self.year)
		for day in self.dates(name):
			self.assertLess(day.weekday(), 5, f"dòng lễ {day} rơi vào ngày nghỉ cuối tuần")

	def test_idempotent(self):
		name1 = self.generate(self.year)
		n1 = len(self.dates(name1))
		name2 = self.generate(self.year)
		self.assertEqual(name1, name2)
		self.assertEqual(len(self.dates(name2)), n1)

	# --- nghỉ bù (Điều 112 khoản 3) ------------------------------------------

	def test_compensatory_day_when_a_holiday_falls_outside_the_weekly_pattern(self):
		"""01/05/2022 rơi đúng Chủ nhật -> nghỉ bù thứ Hai 02/05."""
		name = self.generate(2022)
		dates = self.dates(name)
		self.assertNotIn(getdate("2022-05-01"), dates, "ngày lễ trùng CN không tự thành dòng lễ")
		self.assertIn(getdate("2022-05-02"), dates, "nghỉ bù rơi vào thứ Hai kế tiếp")

	def test_compensatory_day_is_idempotent(self):
		name = self.generate(2022)
		n1 = len(self.dates(name))
		self.generate(2022)
		self.assertEqual(len(self.dates(name)), n1)

	def test_compensatory_day_never_swallows_another_holiday(self):
		"""30/04/2028 rơi Chủ nhật: ngày bù phải NHẢY QUA 1/5 (đã là lễ) để rơi vào 02/05."""
		name = self.generate(2028)
		dates = self.dates(name)
		self.assertIn(getdate("2028-05-01"), dates, "Quốc tế Lao động không được bị nuốt")
		self.assertIn(getdate("2028-05-02"), dates, "nghỉ bù của 30/4 rơi vào 02/05")

	# --- ngày đặc biệt khai tay ----------------------------------------------

	def test_extra_holidays_are_added_as_public_holidays(self):
		name = self.generate(2027, extra={"2027-02-08": "Tết Nguyên Đán (mùng 1)"})
		self.assertEqual(self.dates(name).get(getdate("2027-02-08")), 0)

	def test_extra_holiday_on_a_rest_day_gets_a_compensatory_day(self):
		"""Điều 112 khoản 3 áp cho cả lễ âm: 2026-04-26 (Giỗ Tổ) rơi đúng Chủ nhật."""
		name = self.generate(2026, extra={"2026-04-26": "Giỗ Tổ Hùng Vương"})
		dates = self.dates(name)
		self.assertNotIn(getdate("2026-04-26"), dates)
		self.assertIn(getdate("2026-04-27"), dates, "nghỉ bù rơi vào thứ Hai kế tiếp")

	def test_extra_holidays_are_idempotent(self):
		extra = {"2027-02-08": "Tết Nguyên Đán (mùng 1)", "2027-04-16": "Giỗ Tổ Hùng Vương"}
		name = self.generate(2027, extra=extra)
		n1 = len(self.dates(name))
		self.generate(2027, extra=extra)
		self.assertEqual(len(self.dates(name)), n1)

	def test_a_make_up_day_keeps_a_holiday_in_place_instead_of_moving_it(self):
		"""Ngày làm bù là ngày LÀM VIỆC, nên lễ rơi trúng nó không cần nghỉ bù nữa."""
		self.set_calendar_days([(2026, "2026-04-26", "Làm bù", "Làm bù Giỗ Tổ")])
		name = self.generate(2026, extra={"2026-04-26": "Giỗ Tổ Hùng Vương"})
		dates = self.dates(name)
		self.assertIn(getdate("2026-04-26"), dates, "26/4 nay là ngày làm việc nên lễ đứng nguyên")
		self.assertNotIn(getdate("2026-04-27"), dates, "không cần nghỉ bù nữa")
