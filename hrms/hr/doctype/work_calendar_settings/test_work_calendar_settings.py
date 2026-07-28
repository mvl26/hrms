# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# See license.txt
"""Chính sách lịch làm việc là nguồn sự thật; Holiday List là kết quả sinh ra từ nó.

Chạy qua harness rollback — mọi thay đổi đều được rollback.
"""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import getdate

from hrms.hr.doctype.work_calendar_settings.work_calendar_settings import generate_holiday_list
from hrms.tests.isolation import PerTestRollback


class TestWorkCalendarSettings(PerTestRollback, FrappeTestCase):
	def setUp(self):
		self.company = frappe.db.get_value("Company", {}, "name")
		self.settings = frappe.get_single("Work Calendar Settings")
		self.settings.company = self.company
		self.settings.weekly_off_days = []
		self.settings.lunar_holidays = []

	def set_policy(self, days=(), lunar=()):
		self.settings.weekly_off_days = []
		self.settings.lunar_holidays = []
		for d in days:
			self.settings.append("weekly_off_days", {"day": d})
		for year, date, desc in lunar:
			self.settings.append("lunar_holidays", {"year": year, "holiday_date": date, "description": desc})
		self.settings.save()

	def dates(self, name):
		return {
			getdate(r.holiday_date): r.weekly_off
			for r in frappe.get_all(
				"Holiday",
				filters={"parent": name, "parenttype": "Holiday List"},
				fields=["holiday_date", "weekly_off"],
			)
		}

	def test_weekly_off_days_are_read_from_the_policy(self):
		self.set_policy(days=("Saturday", "Sunday"))
		self.assertEqual(set(self.settings.get_weekly_off_days()), {"Saturday", "Sunday"})

	def test_lunar_holidays_are_filtered_by_year(self):
		self.set_policy(
			lunar=(
				(2028, "2028-01-26", "Tết Nguyên Đán (mùng 1)"),
				(2029, "2029-02-13", "Tết Nguyên Đán (mùng 1)"),
			)
		)
		self.assertEqual(self.settings.get_lunar_holidays(2028), {"2028-01-26": "Tết Nguyên Đán (mùng 1)"})
		self.assertEqual(self.settings.get_lunar_holidays(2029), {"2029-02-13": "Tết Nguyên Đán (mùng 1)"})

	def test_generated_list_follows_the_policy(self):
		"""Đây là điểm mấu chốt: sinh lịch KHÔNG cần truyền tham số, chính sách tự được áp."""
		self.set_policy(days=("Saturday", "Sunday"), lunar=((2028, "2028-01-26", "Tết Nguyên Đán (mùng 1)"),))
		name = generate_holiday_list(year=2028, company=self.company)
		dates = self.dates(name)

		weekly = [d for d, wo in dates.items() if wo]
		self.assertTrue(all(d.weekday() in (5, 6) for d in weekly), "chỉ T7/CN được là nghỉ tuần")
		self.assertGreaterEqual(len(weekly), 104)
		# lễ âm đã khai phải có mặt (26/01/2028 = T4), và là ngày nghỉ LỄ chứ không phải nghỉ tuần
		self.assertEqual(dates.get(getdate("2028-01-26")), 0)
		# lễ dương Điều 112 vẫn tự sinh, không cần khai (01/05/2028 = T2)
		self.assertEqual(dates.get(getdate("2028-05-01")), 0)
		# 30/04/2028 rơi đúng Chủ nhật -> giữ là nghỉ tuần, và nghỉ bù phải NHẢY QUA 1/5 (đã là lễ)
		# để rơi vào 02/05 (T3) — chứng minh nghỉ bù không đè lên ngày nghỉ khác.
		self.assertEqual(dates.get(getdate("2028-04-30")), 1)
		self.assertEqual(dates.get(getdate("2028-05-02")), 0)

	def test_changing_the_policy_changes_the_next_generation(self):
		"""Sửa chính sách rồi sinh lại thì lịch phải đi theo — đó là lý do doctype này tồn tại."""
		self.set_policy(days=("Sunday",))
		name = generate_holiday_list(year=2028, company=self.company)
		self.assertFalse(any(d.weekday() == 5 for d, wo in self.dates(name).items() if wo))

		self.set_policy(days=("Saturday", "Sunday"))
		generate_holiday_list(year=2028, company=self.company)
		self.assertTrue(any(d.weekday() == 5 for d, wo in self.dates(name).items() if wo))

	def test_generating_twice_does_not_duplicate(self):
		self.set_policy(days=("Saturday", "Sunday"), lunar=((2028, "2028-01-26", "Tết"),))
		name = generate_holiday_list(year=2028, company=self.company)
		n1 = len(self.dates(name))
		generate_holiday_list(year=2028, company=self.company)
		self.assertEqual(len(self.dates(name)), n1)

	def test_lunar_holiday_year_must_match_its_date(self):
		"""Khai sai năm thì ngày lễ sẽ lặng lẽ không được áp -> chặn ngay lúc lưu."""
		self.settings.append(
			"lunar_holidays", {"year": 2028, "holiday_date": "2029-02-13", "description": "Tết"}
		)
		self.assertRaises(frappe.ValidationError, self.settings.save)

	def test_company_is_required_to_generate(self):
		"""Site chưa cấu hình bao giờ (company trống) phải báo lỗi rõ ràng, không sinh lịch rỗng.
		Ghi thẳng vào Single để bỏ qua ràng buộc reqd — mô phỏng đúng trạng thái chưa cấu hình."""
		frappe.db.set_single_value("Work Calendar Settings", "company", None)
		frappe.clear_document_cache("Work Calendar Settings", "Work Calendar Settings")
		self.assertRaises(frappe.ValidationError, generate_holiday_list, year=2028)
