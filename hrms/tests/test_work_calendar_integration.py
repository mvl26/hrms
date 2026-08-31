# Copyright (c) 2026, Miyano Việt Nam.
"""Các chức năng CŨ phải đọc lịch qua cửa mới, kể cả SAU khi gỡ dòng nghỉ cuối tuần.

Mỗi khẳng định ở đây chạy trên trạng thái **sau di trú** (mô phỏng ngay trong savepoint) — vì đó
chính là lúc những chỗ còn đọc thẳng `Holiday List` sẽ sai. Trạng thái hôm nay (lịch còn 104 dòng
cuối tuần) không phân biệt được đúng/sai, nên test ở đó là test rỗng.

Chạy qua harness rollback — KHÔNG `bench --site miyano run-tests`.
"""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import getdate

from hrms.tests.isolation import PerTestRollback
from hrms.tests.work_calendar_fixture import BRIDGE_SAME_MONTH, build_scenario

YEAR, MONTH = 2027, 6
MONTH_START, MONTH_END = "2027-06-01", "2027-06-30"
SATURDAY = "2027-06-19"
WEDNESDAY_HOLIDAY = "2027-06-16"  # lễ riêng của công ty
TUESDAY = "2027-06-15"


class WorkCalendarIntegrationBase(PerTestRollback, FrappeTestCase):
	def setUp(self):
		self.scenario = build_scenario()
		self.employee = self.scenario.employees["A"]
		self.drop_weekly_off_rows()

	def drop_weekly_off_rows(self):
		"""Mô phỏng bước di trú: Holiday List chỉ còn ngày lễ."""
		frappe.db.delete("Holiday", {"parent": self.scenario.holiday_list, "weekly_off": 1})
		frappe.clear_cache()


class TestCalendarEndpoints(WorkCalendarIntegrationBase):
	"""Lịch chấm công của PWA và calendar của Attendance trên Desk."""

	def test_pwa_calendar_marks_weekends(self):
		from hrms.api import get_holidays_for_calendar

		days = [getdate(d) for d in get_holidays_for_calendar(self.employee, MONTH_START, MONTH_END)]
		self.assertIn(getdate(SATURDAY), days, "cuối tuần phải được tô trên lịch PWA")
		self.assertIn(getdate(WEDNESDAY_HOLIDAY), days, "ngày lễ vẫn phải được tô")
		self.assertNotIn(getdate(TUESDAY), days)

	def test_pwa_calendar_does_not_mark_a_make_up_day(self):
		from hrms.api import get_holidays_for_calendar

		_, make_up = BRIDGE_SAME_MONTH
		start, end = "2027-08-01", "2027-08-31"
		days = [getdate(d) for d in get_holidays_for_calendar(self.employee, start, end)]
		self.assertNotIn(getdate(make_up), days, "ngày làm bù là ngày LÀM VIỆC")

	def test_upcoming_holidays_still_lists_only_public_holidays(self):
		"""Ngữ nghĩa GIỮ NGUYÊN: đây là 'ngày lễ sắp tới', không phải 'ngày nghỉ sắp tới'."""
		from hrms.api import get_holidays_for_employee

		days = [getdate(h["holiday_date"]) for h in get_holidays_for_employee(self.employee)]
		self.assertNotIn(getdate(SATURDAY), days)

	def test_desk_attendance_calendar_shows_rest_days(self):
		from hrms.hr.doctype.attendance.attendance import add_holidays

		events = []
		add_holidays(events, MONTH_START, MONTH_END, self.employee)
		days = [getdate(e["attendance_date"]) for e in events]
		self.assertIn(getdate(SATURDAY), days)
		self.assertIn(getdate(WEDNESDAY_HOLIDAY), days)

	def test_desk_calendar_names_holidays_and_rest_days_apart(self):
		from hrms.hr.doctype.attendance.attendance import add_holidays

		events = []
		add_holidays(events, MONTH_START, MONTH_END, self.employee)
		titles = {getdate(e["attendance_date"]): e["title"] for e in events}
		self.assertNotEqual(titles[getdate(SATURDAY)], titles[getdate(WEDNESDAY_HOLIDAY)])


class TestMarkAttendanceSuggestions(WorkCalendarIntegrationBase):
	"""Hộp thoại *Mark Attendance* và template upload không được gợi ý ngày nghỉ."""

	def test_unmarked_days_excludes_rest_days(self):
		"""Không sửa thì hộp thoại CHỦ ĐỘNG gợi ý T7/CN -> HR rất dễ chấm nhầm một ngày công."""
		from hrms.hr.doctype.attendance.attendance import get_unmarked_days

		days = [
			getdate(d)
			for d in get_unmarked_days(self.employee, MONTH_START, MONTH_END, exclude_holidays=1)
		]
		self.assertNotIn(getdate(SATURDAY), days)
		self.assertNotIn(getdate(WEDNESDAY_HOLIDAY), days)
		self.assertIn(getdate(TUESDAY), days)

	def test_unmarked_days_includes_a_make_up_day(self):
		"""Ngày làm bù PHẢI xuất hiện — nó là ngày công, thiếu bản ghi là thiếu thật."""
		from hrms.hr.doctype.attendance.attendance import get_unmarked_days

		_, make_up = BRIDGE_SAME_MONTH
		days = [
			getdate(d)
			for d in get_unmarked_days(self.employee, "2027-08-01", "2027-08-31", exclude_holidays=1)
		]
		self.assertIn(getdate(make_up), days)

	def test_upload_template_marks_rest_days_as_holiday(self):
		from hrms.hr.doctype.upload_attendance.upload_attendance import get_holidays_for_employees

		got = get_holidays_for_employees([self.employee], MONTH_START, MONTH_END)
		self.assertIn(getdate(SATURDAY), got[self.employee])
		self.assertNotIn(getdate(TUESDAY), got[self.employee])

	def test_upload_template_keys_by_employee_not_by_holiday_list(self):
		"""Hai người dùng chung một Holiday List vẫn có thể nghỉ khác ngày, vì lịch tuần từ CA."""
		from hrms.hr.doctype.upload_attendance.upload_attendance import get_holidays_for_employees

		office, six_day = self.scenario.employees["A"], self.scenario.employees["B"]
		got = get_holidays_for_employees([office, six_day], MONTH_START, MONTH_END)
		self.assertIn(getdate(SATURDAY), got[office])
		self.assertNotIn(getdate(SATURDAY), got[six_day], "ca 6 ngày vẫn đi làm thứ Bảy")
