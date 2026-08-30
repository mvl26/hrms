# Copyright (c) 2026, Miyano Việt Nam.
"""Chính sách lịch làm việc là nguồn sự thật; Holiday List là kết quả sinh ra từ nó.

Sau khi tách, trang này giữ hai thứ: lịch làm việc MẶC ĐỊNH của công ty (ca có khai riêng thì ca
thắng) và bảng NGÀY ĐẶC BIỆT — `Nghỉ lễ` (đẩy xuống Holiday List) và `Làm bù` (ngày cuối tuần phải
đi làm, KHÔNG xuống Holiday List vì nó là ngày làm việc).

Chạy qua harness rollback — mọi thay đổi đều được rollback.
"""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import getdate

from hrms.hr.doctype.work_calendar_settings.work_calendar_settings import generate_holiday_list
from hrms.hr.work_schedule import is_rest_day, is_scheduled_day
from hrms.tests.isolation import PerTestRollback
from hrms.tests.vn_test_utils import default_company, test_employee

MON_TO_FRI = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]


class TestWorkCalendarSettings(PerTestRollback, FrappeTestCase):
	def setUp(self):
		self.company = default_company()
		self.settings = frappe.get_single("Work Calendar Settings")
		self.settings.company = self.company
		self.set_default_days(MON_TO_FRI)
		self.set_calendar_days([])

	def set_default_days(self, days):
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
		self.settings = frappe.get_single("Work Calendar Settings")
		self.settings.company = self.company
		self.settings.calendar_days = []
		for year, day, day_type, desc in rows:
			self.settings.append(
				"calendar_days",
				{"year": year, "holiday_date": day, "day_type": day_type, "description": desc},
			)
		self.settings.flags.ignore_permissions = True
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

	# --- chính sách -> lịch sinh ra -------------------------------------------

	def test_public_holidays_are_filtered_by_year_and_type(self):
		self.set_calendar_days(
			[
				(2028, "2028-01-26", "Nghỉ lễ", "Tết Nguyên Đán"),
				(2028, "2028-03-04", "Làm bù", "Làm bù Tết"),
				(2029, "2029-02-13", "Nghỉ lễ", "Tết Nguyên Đán"),
			]
		)
		self.assertEqual(self.settings.get_public_holidays(2028), {"2028-01-26": "Tết Nguyên Đán"})
		self.assertEqual(self.settings.get_make_up_days(2028), {"2028-03-04": "Làm bù Tết"})
		self.assertEqual(self.settings.get_public_holidays(2029), {"2029-02-13": "Tết Nguyên Đán"})

	def test_generated_list_follows_the_policy(self):
		"""Điểm mấu chốt: sinh lịch KHÔNG cần truyền tham số, chính sách tự được áp."""
		self.set_calendar_days([(2028, "2028-01-26", "Nghỉ lễ", "Tết Nguyên Đán (mùng 1)")])
		name = generate_holiday_list(year=2028, company=self.company)
		dates = self.dates(name)

		self.assertFalse(any(dates.values()), "Holiday List không được còn dòng nghỉ cuối tuần")
		self.assertIn(getdate("2028-01-26"), dates, "lễ đã khai phải có mặt")
		self.assertIn(getdate("2028-05-01"), dates, "lễ dương Điều 112 vẫn tự sinh")
		# 30/04/2028 rơi đúng Chủ nhật -> nghỉ bù phải NHẢY QUA 1/5 (đã là lễ) để rơi vào 02/05
		self.assertNotIn(getdate("2028-04-30"), dates)
		self.assertIn(getdate("2028-05-02"), dates)

	def test_make_up_days_never_reach_the_holiday_list(self):
		"""Ngày `Làm bù` là ngày LÀM VIỆC — nhét vào bảng ngày nghỉ là sai ngay từ tên gọi."""
		self.set_calendar_days([(2028, "2028-03-04", "Làm bù", "Làm bù Tết")])
		name = generate_holiday_list(year=2028, company=self.company)
		self.assertNotIn(getdate("2028-03-04"), self.dates(name))

	def test_generating_twice_does_not_duplicate(self):
		self.set_calendar_days([(2028, "2028-01-26", "Nghỉ lễ", "Tết")])
		name = generate_holiday_list(year=2028, company=self.company)
		n1 = len(self.dates(name))
		generate_holiday_list(year=2028, company=self.company)
		self.assertEqual(len(self.dates(name)), n1)

	# --- ngoại lệ đổi lịch tuần ----------------------------------------------

	def test_a_make_up_day_turns_a_saturday_into_a_working_day(self):
		"""Lý do bảng ngoại lệ tồn tại: mẫu tuần lặp lại không nói được 'riêng T7 này thì đi làm'."""
		employee = test_employee("wcs_makeup@codes.com")
		saturday = "2028-03-04"
		self.assertTrue(is_rest_day(employee, saturday))

		self.set_calendar_days([(2028, saturday, "Làm bù", "Làm bù Tết")])
		self.assertTrue(is_scheduled_day(employee, saturday))
		self.assertFalse(is_rest_day(employee, saturday))

	# --- chốt chặn -----------------------------------------------------------

	def test_year_must_match_the_date(self):
		"""Khai sai năm thì ngày sẽ lặng lẽ không được áp -> chặn ngay lúc lưu."""
		with self.assertRaises(frappe.ValidationError):
			self.set_calendar_days([(2028, "2029-02-13", "Nghỉ lễ", "Tết")])

	def test_a_date_cannot_be_declared_twice(self):
		"""Vừa nghỉ vừa làm bù thì kết quả tuỳ thứ tự dòng — chặn thay vì để tuỳ hên xui."""
		with self.assertRaises(frappe.ValidationError):
			self.set_calendar_days(
				[
					(2028, "2028-03-04", "Làm bù", "Làm bù"),
					(2028, "2028-03-04", "Nghỉ lễ", "Nghỉ"),
				]
			)

	def test_company_is_required_to_generate(self):
		"""Site chưa cấu hình bao giờ (company trống) phải báo lỗi rõ ràng, không sinh lịch rỗng."""
		frappe.db.set_single_value("Work Calendar Settings", "company", None)
		frappe.clear_document_cache("Work Calendar Settings", "Work Calendar Settings")
		with self.assertRaises(frappe.ValidationError):
			generate_holiday_list(year=2028, company=None)

	# --- xem trước tác động lên mẫu số ---------------------------------------

	def test_preview_shows_the_working_days_of_each_month(self):
		"""Bắt lỗi 'khai làm bù mà quên khai nghỉ ghép' — vốn im lặng đổi lương cả tháng."""
		preview = frappe.get_single("Work Calendar Settings").working_days_preview(2026)
		self.assertEqual(preview[7]["before"], 23)  # T2-T6 của 07/2026
		self.assertEqual(preview[2]["before"], 20)

	def test_preview_counts_a_make_up_day(self):
		self.set_calendar_days([(2026, "2026-08-29", "Làm bù", "Làm bù Quốc khánh")])
		preview = frappe.get_single("Work Calendar Settings").working_days_preview(2026)
		self.assertEqual(preview[8]["after"], 22)  # 21 ngày T2-T6 + 1 ngày làm bù
