# Copyright (c) 2026, Miyano Việt Nam.
"""Bộ dựng cảnh lịch làm việc phải dựng đúng thứ nó hứa.

Mỗi bộ test khác sẽ khẳng định phần của mình TRÊN cảnh này, nên nếu chính cảnh sai thì mọi khẳng
định phía sau đều vô nghĩa. Đây là bộ test canh cho bộ dựng cảnh.

Chạy qua harness rollback — KHÔNG `bench --site miyano run-tests`.
"""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import getdate

from hrms.hr.work_schedule import (
	is_public_holiday,
	is_rest_day,
	is_scheduled_day,
	scheduled_days_between,
	shift_weekdays,
)
from hrms.tests.isolation import PerTestRollback
from hrms.tests.work_calendar_fixture import (
	BRIDGE_CROSS_MONTH,
	BRIDGE_SAME_MONTH,
	COMPANY_HOLIDAY,
	SCHEDULED_DAYS_2027,
	build_scenario,
	month_range,
)


class TestWorkCalendarFixture(PerTestRollback, FrappeTestCase):
	def setUp(self):
		self.scenario = build_scenario()

	# --- ba ca phủ ba tầng phân giải -----------------------------------------

	def test_three_shifts_have_the_expected_weekly_patterns(self):
		shifts = self.scenario.shifts
		self.assertEqual(len(shift_weekdays(shifts["office"])), 5)
		self.assertEqual(len(shift_weekdays(shifts["six_day"])), 6)
		self.assertEqual(len(shift_weekdays(shifts["all_week"])), 7)

	def test_employee_a_follows_the_office_shift(self):
		emp = self.scenario.employees["A"]
		self.assertTrue(is_scheduled_day(emp, "2027-06-16"))  # thứ Tư
		self.assertTrue(is_rest_day(emp, "2027-06-19"))  # thứ Bảy

	def test_employee_b_works_saturdays(self):
		emp = self.scenario.employees["B"]
		self.assertTrue(is_scheduled_day(emp, "2027-06-19"))  # thứ Bảy của ca 6 ngày
		self.assertTrue(is_rest_day(emp, "2027-06-20"))  # Chủ nhật vẫn nghỉ

	def test_employee_c_falls_back_to_the_company_default(self):
		"""Tầng 3 của chuỗi phân giải phải có người thật đi qua, không chỉ có test riêng."""
		emp = self.scenario.employees["C"]
		self.assertIsNone(frappe.db.get_value("Employee", emp, "default_shift"))
		self.assertTrue(is_scheduled_day(emp, "2027-06-16"))
		self.assertTrue(is_rest_day(emp, "2027-06-19"))

	def test_employee_d_is_exempt_from_checkin(self):
		emp = self.scenario.employees["D"]
		self.assertEqual(frappe.db.get_value("Employee", emp, "custom_exempt_from_checkin"), 1)

	def test_employee_e_joins_and_leaves_mid_period(self):
		emp = self.scenario.employees["E"]
		row = frappe.db.get_value("Employee", emp, ["date_of_joining", "relieving_date"], as_dict=True)
		self.assertEqual(getdate(row.date_of_joining), getdate("2027-03-16"))
		self.assertEqual(getdate(row.relieving_date), getdate("2027-11-15"))

	# --- lịch 2027 ------------------------------------------------------------

	def test_the_company_holiday_is_a_paid_holiday_on_a_working_day(self):
		emp = self.scenario.employees["A"]
		self.assertTrue(is_scheduled_day(emp, COMPANY_HOLIDAY))
		self.assertTrue(is_public_holiday(emp, COMPANY_HOLIDAY))

	def test_a_holiday_falling_on_a_rest_day_became_a_compensatory_day(self):
		"""01/05/2027 rơi thứ Bảy -> generator phải đẩy thành nghỉ bù ngày làm việc kế tiếp."""
		emp = self.scenario.employees["A"]
		self.assertFalse(is_public_holiday(emp, "2027-05-01"))
		self.assertTrue(is_public_holiday(emp, "2027-05-03"))  # thứ Hai kế tiếp

	def test_every_holiday_row_lands_on_a_working_day(self):
		"""Bất biến: dòng lễ không bao giờ nằm ngoài lịch tuần, nếu không nó cộng khống ngày công."""
		emp = self.scenario.employees["A"]
		rows = frappe.get_all("Holiday", filters={"parent": self.scenario.holiday_list}, pluck="holiday_date")
		for day in rows:
			self.assertTrue(is_scheduled_day(emp, day), f"dòng lễ {day} rơi vào ngày nghỉ")

	# --- hai cặp nghỉ ghép / làm bù -------------------------------------------

	def test_a_bridge_off_day_stays_in_the_denominator(self):
		"""Ngày nghỉ ghép khai là `Nghỉ lễ` -> nó là ngày CÓ LƯƠNG, nên vẫn nằm trong mẫu số.

		Đây là chỗ dễ hiểu nhầm nhất của mô hình: nghỉ ghép KHÔNG rút ngắn tháng.
		"""
		off, _ = BRIDGE_SAME_MONTH
		emp = self.scenario.employees["A"]
		self.assertTrue(is_scheduled_day(emp, off))
		self.assertTrue(is_public_holiday(emp, off))

	def test_a_bridge_pair_adds_one_day_to_the_denominator_not_zero(self):
		"""Một cặp nghỉ ghép + làm bù CÙNG tháng làm mẫu số +1, KHÔNG phải không đổi.

		Số học: 22 ngày T2-T6 -> 21 ngày đi làm + 1 ngày lễ (nghỉ ghép) + 1 ngày làm bù = 23 ngày
		được trả. Nhất quán với 'ngày công chuẩn = ngày đi làm + nghỉ lễ + nghỉ có lương'.

		Nếu HR hiểu nghỉ ghép là ĐỔI NGÀY (net 0) thì mô hình hiện tại chưa diễn đạt được — cần
		một loại thứ ba 'nghỉ không tính công'. Xem Open Questions của spec.
		"""
		off, make_up = BRIDGE_SAME_MONTH
		self.assertEqual(getdate(off).month, getdate(make_up).month)
		emp = self.scenario.employees["A"]
		got = scheduled_days_between(emp, *month_range(off))
		self.assertEqual(len(got), SCHEDULED_DAYS_2027[getdate(off).month - 1] + 1)

	def test_a_cross_month_make_up_day_lands_in_its_own_month(self):
		"""Bù khác tháng: tháng NGHỈ giữ nguyên mẫu số (nghỉ ghép là lễ có lương), tháng BÙ +1.

		Hệ quả thật, cần HR biết trước khi ký: lương một ngày công của hai tháng khác nhau.
		"""
		off, make_up = BRIDGE_CROSS_MONTH
		self.assertNotEqual(getdate(off).month, getdate(make_up).month)
		emp = self.scenario.employees["A"]

		off_month = len(scheduled_days_between(emp, *month_range(off)))
		up_month = len(scheduled_days_between(emp, *month_range(make_up)))
		self.assertEqual(off_month, SCHEDULED_DAYS_2027[getdate(off).month - 1])
		self.assertEqual(up_month, SCHEDULED_DAYS_2027[getdate(make_up).month - 1] + 1)

	def test_the_make_up_day_is_a_working_day_for_everyone(self):
		_, make_up = BRIDGE_SAME_MONTH
		for key in ("A", "C"):
			self.assertTrue(is_scheduled_day(self.scenario.employees[key], make_up), key)

	# --- dựng lại không nhân đôi ---------------------------------------------

	def test_scenario_is_idempotent(self):
		holidays = frappe.db.count("Holiday", {"parent": self.scenario.holiday_list})
		again = build_scenario()
		self.assertEqual(again.holiday_list, self.scenario.holiday_list)
		self.assertEqual(frappe.db.count("Holiday", {"parent": again.holiday_list}), holidays)
		self.assertEqual(len(shift_weekdays(again.shifts["office"])), 5)
