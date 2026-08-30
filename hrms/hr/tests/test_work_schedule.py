# Copyright (c) 2026, Miyano Việt Nam.
"""Lịch tuần: lõi luật thuần + chuỗi phân giải ca / Holiday List theo ngày.

Lớp luật thuần chạy được bằng unittest trần; lớp phân giải chạm DB nên đi qua harness rollback
(KHÔNG `bench --site miyano run-tests`). Test seed lịch tuần bằng cách ghi THẲNG bảng con
`Assignment Rule Day`, không bao giờ insert Custom Field — DDL trong test là implicit commit và
rò rỉ vào site thật.
"""

import unittest
from datetime import date

import frappe
from frappe.tests.utils import FrappeTestCase

from hrms.hr.work_schedule import (
	WorkScheduleNotConfigured,
	dates_in_range,
	holiday_list_for,
	is_public_holiday,
	is_rest_day,
	is_scheduled_day,
	is_working_day,
	scheduled_dates,
	weekday_set,
)
from hrms.tests.isolation import PerTestRollback
from hrms.tests.vn_test_utils import default_company, test_employee

MON_TO_FRI = frozenset({0, 1, 2, 3, 4})
MON_TO_FRI_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]

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


class TestWorkScheduleResolution(PerTestRollback, FrappeTestCase):
	"""Chuỗi phân giải lịch tuần + Holiday List theo ngày (chạm DB, rollback từng test)."""

	def setUp(self):
		self.company = default_company()
		self.employee = test_employee("work_schedule@codes.com")
		self.shift = self.make_shift("_Test Lich Tuan")
		frappe.db.set_value("Employee", self.employee, "default_shift", self.shift)
		frappe.db.set_value("Employee", self.employee, "holiday_list", None)
		frappe.clear_cache(doctype="Employee")

	def make_shift(self, name: str) -> str:
		if not frappe.db.exists("Shift Type", name):
			frappe.get_doc(
				{"doctype": "Shift Type", "__newname": name, "start_time": "8:0:0", "end_time": "17:0:0"}
			).insert(ignore_permissions=True)
		return name

	def set_days(self, parent: str, parenttype: str, parentfield: str, days):
		"""Ghi thẳng bảng con: chạy được cả khi site chưa migrate custom field."""
		frappe.db.delete(
			"Assignment Rule Day",
			{"parent": parent, "parenttype": parenttype, "parentfield": parentfield},
		)
		for idx, day in enumerate(days, start=1):
			frappe.get_doc(
				{
					"doctype": "Assignment Rule Day",
					"parent": parent,
					"parenttype": parenttype,
					"parentfield": parentfield,
					"day": day,
					"idx": idx,
				}
			).insert(ignore_permissions=True)

	def set_shift_days(self, days, shift=None):
		self.set_days(shift or self.shift, "Shift Type", "custom_working_days", days)

	def set_company_days(self, days):
		self.set_days("Work Calendar Settings", "Work Calendar Settings", "default_working_days", days)

	def make_holiday_list(self, name, from_date, to_date, holidays=()):
		if frappe.db.exists("Holiday List", name):
			frappe.delete_doc("Holiday List", name, force=True, ignore_permissions=True)
		doc = frappe.get_doc(
			{
				"doctype": "Holiday List",
				"holiday_list_name": name,
				"from_date": from_date,
				"to_date": to_date,
				"holidays": [
					{"holiday_date": d, "description": desc, "weekly_off": 0} for d, desc in holidays
				],
			}
		)
		doc.insert(ignore_permissions=True)
		return doc.name

	# --- chuỗi phân giải ca ---------------------------------------------------

	def test_shift_days_drive_the_schedule(self):
		self.set_shift_days(MON_TO_FRI_NAMES)
		self.assertTrue(is_scheduled_day(self.employee, "2026-07-21"))  # T3
		self.assertFalse(is_scheduled_day(self.employee, "2026-07-25"))  # T7

	def test_shift_assignment_wins_over_default_shift(self):
		"""Đổi ca giữa năm mà vẫn đọc default_shift là sai mẫu số của cả tháng đó."""
		self.set_shift_days(MON_TO_FRI_NAMES)
		six_day = self.make_shift("_Test Lich Tuan 6 Ngay")
		self.set_shift_days([*MON_TO_FRI_NAMES, "Saturday"], shift=six_day)
		frappe.get_doc(
			{
				"doctype": "Shift Assignment",
				"employee": self.employee,
				"shift_type": six_day,
				"company": self.company,
				"start_date": "2026-07-01",
				"end_date": "2026-07-31",
			}
		).insert(ignore_permissions=True).submit()
		self.assertTrue(is_scheduled_day(self.employee, "2026-07-25"))  # T7 của ca 6 ngày

	def test_falls_back_to_company_default(self):
		"""NV có ca nhưng ca chưa khai lịch tuần → lưới an toàn ở Work Calendar Settings."""
		self.set_shift_days([])
		self.set_company_days(MON_TO_FRI_NAMES)
		self.assertTrue(is_scheduled_day(self.employee, "2026-07-21"))
		self.assertFalse(is_scheduled_day(self.employee, "2026-07-25"))

	def test_raises_when_nothing_is_configured(self):
		"""Tầng cuối là CHỦ Ý: nổ lỗi rõ ràng, không âm thầm coi mọi ngày là ngày làm việc."""
		self.set_shift_days([])
		self.set_company_days([])
		with self.assertRaises(WorkScheduleNotConfigured):
			is_scheduled_day(self.employee, "2026-07-21")

	# --- nghỉ tuần vs nghỉ lễ -------------------------------------------------

	def test_saturday_is_rest_day_not_public_holiday(self):
		self.set_shift_days(MON_TO_FRI_NAMES)
		self.assertTrue(is_rest_day(self.employee, "2026-07-25"))
		self.assertFalse(is_public_holiday(self.employee, "2026-07-25"))

	def test_public_holiday_on_a_scheduled_day(self):
		self.set_shift_days(MON_TO_FRI_NAMES)
		hl = self.make_holiday_list(
			"_Test VN 2026", "2026-01-01", "2026-12-31", [("2026-07-17", "Nghỉ lễ công ty")]
		)
		frappe.db.set_value("Employee", self.employee, "holiday_list", hl)
		self.assertTrue(is_scheduled_day(self.employee, "2026-07-17"))  # thứ Sáu
		self.assertTrue(is_public_holiday(self.employee, "2026-07-17"))
		self.assertFalse(is_working_day(self.employee, "2026-07-17"))  # lễ thì không phải đi làm

	def test_holiday_row_on_a_rest_day_is_not_a_public_holiday(self):
		"""PHÒNG THỦ: dòng lễ nhập nhầm vào Chủ nhật không được cộng khống một ngày công."""
		self.set_shift_days(MON_TO_FRI_NAMES)
		hl = self.make_holiday_list(
			"_Test VN 2026", "2026-01-01", "2026-12-31", [("2026-07-26", "Lễ nhập nhầm vào CN")]
		)
		frappe.db.set_value("Employee", self.employee, "holiday_list", hl)
		self.assertFalse(is_public_holiday(self.employee, "2026-07-26"))

	def test_holiday_list_resolved_by_date_not_by_employee_link(self):
		"""Mỗi năm một list: đứng ở lịch 2027 hỏi ngày của 2026 vẫn phải ra lịch 2026."""
		self.set_shift_days(MON_TO_FRI_NAMES)
		older = self.make_holiday_list(
			f"VN {self.company} 2026", "2026-01-01", "2026-12-31", [("2026-07-17", "Lễ công ty")]
		)
		newer = self.make_holiday_list(f"VN {self.company} 2027", "2027-01-01", "2027-12-31")
		frappe.db.set_value("Employee", self.employee, "holiday_list", newer)
		self.assertEqual(holiday_list_for(self.employee, "2026-07-17"), older)
		self.assertTrue(is_public_holiday(self.employee, "2026-07-17"))
