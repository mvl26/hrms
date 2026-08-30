# Copyright (c) 2026, Miyano Việt Nam.
from datetime import timedelta

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import get_datetime

from erpnext.setup.doctype.employee.test_employee import make_employee

from hrms.tests.isolation import PerTestRollback
from hrms.tests.vn_test_utils import default_company
from hrms.vn_payroll.lunch import (
	DEFAULT_LUNCH_END,
	DEFAULT_LUNCH_START,
	count_lunch_days,
	shift_lunch_window,
)


class TestShiftLunchWindow(PerTestRollback, FrappeTestCase):
	def test_falls_back_to_default_when_no_shift(self):
		self.assertEqual(shift_lunch_window(None), (DEFAULT_LUNCH_START, DEFAULT_LUNCH_END))

	def test_reads_window_from_shift_type(self):
		from hrms.hr.doctype.shift_type.test_shift_type import setup_shift_type

		st = setup_shift_type(shift_type="MVL Lunch Win", start_time="08:00:00", end_time="17:00:00")
		st.custom_lunch_start = timedelta(hours=11)
		st.custom_lunch_end = timedelta(hours=14)
		st.save()
		self.assertEqual(shift_lunch_window(st.name), (11 * 60, 14 * 60))


class TestCountLunchDays(PerTestRollback, FrappeTestCase):
	def setUp(self):
		self.emp = make_employee("lunch_test@codes.com", company=default_company())

	def day(self, d, status, ins=()):
		att = frappe.get_doc(
			{
				"doctype": "Attendance",
				"employee": self.emp,
				"attendance_date": f"2099-06-{d:02d}",
				"custom_attendance_code": "X" if status == "Present" else None,
				"status": status,
			}
		)
		att.flags.ignore_validate = True
		att.insert()
		att.submit()
		for hm in ins:
			frappe.get_doc(
				{
					"doctype": "Employee Checkin",
					"employee": self.emp,
					"time": get_datetime(f"2099-06-{d:02d} {hm}"),
				}
			).insert()

	def count(self):
		return count_lunch_days(self.emp, "2099-06-01", "2099-06-30")

	def test_full_shift_present_counts(self):
		self.day(1, "Present", ("08:00:00", "17:30:00"))
		self.assertEqual(self.count(), 1)

	def test_morning_only_does_not_count(self):
		# ra 11:30 < 13:30 → chỉ làm sáng, không ăn trưa tại công ty
		self.day(2, "Present", ("08:00:00", "11:30:00"))
		self.assertEqual(self.count(), 0)

	def test_afternoon_only_does_not_count(self):
		# vào 14:00 >= 12:00 → chỉ làm chiều
		self.day(3, "Present", ("14:00:00", "17:00:00"))
		self.assertEqual(self.count(), 0)

	def test_boundary_out_exactly_1330_counts(self):
		self.day(4, "Present", ("11:59:00", "13:30:00"))
		self.assertEqual(self.count(), 1)

	def test_leave_day_with_full_checkins_does_not_count(self):
		# ngày nghỉ phép dù có checkin cũng không tính ăn trưa (không phải ngày công)
		self.day(5, "On Leave", ("08:00:00", "17:30:00"))
		self.assertEqual(self.count(), 0)

	def test_present_without_checkin_does_not_count(self):
		self.day(6, "Present", ())
		self.assertEqual(self.count(), 0)

	def test_multiple_days_sum(self):
		self.day(7, "Present", ("08:00:00", "17:30:00"))  # +1
		self.day(8, "Present", ("08:00:00", "11:00:00"))  # sáng, 0
		self.day(9, "Half Day", ("08:00:00", "17:30:00"))  # +1 (Half Day cũng là ngày công)
		self.assertEqual(self.count(), 2)


class TestEffectiveLunchFlag(PerTestRollback, FrappeTestCase):
	"""Luật ăn trưa per-ngày (spec §5.4, 2026-08-27) — thuần hàm, không đụng DB.

	Điểm mới so với bản 2026-07-25: ngày công KHÔNG có đủ dấu chấm (chấm tay, sửa qua soát công,
	quên chấm ra) không còn bị mất suất ăn; và người có thể ép có/không, máy không đè lại."""

	def dt(self, hhmm):
		return get_datetime(f"2026-07-06 {hhmm}:00")

	def flag(self, status="Present", code="X", punches=(), override=None):
		from hrms.vn_payroll.lunch import effective_lunch_flag

		return effective_lunch_flag(status, code, None, [self.dt(p) for p in punches], override)

	# --- không đủ dấu chấm: theo mặc định của status (PHẦN MỚI) ---
	def test_present_without_any_punch_counts(self):
		"""Chấm tay / sửa qua soát công: đã công nhận ngày công đủ thì mặc định có ăn."""
		self.assertEqual(self.flag(punches=()), 1)

	def test_present_with_one_morning_punch_counts(self):
		"""Quên chấm ra — có mặt từ sáng thì coi như ở lại ăn, không phạt vì lỗi thao tác."""
		self.assertEqual(self.flag(punches=("08:00",)), 1)

	def test_present_with_one_afternoon_punch_does_not_count(self):
		"""Một dấu duy nhất lúc 14:00 = chiều mới tới ⇒ KHÔNG ăn tại công ty.

		Đếm số dấu thôi thì ca này ra sai — phải xét cả giờ."""
		self.assertEqual(self.flag(punches=("14:00",)), 0)

	def test_half_day_with_one_morning_punch_does_not_count(self):
		"""Nửa ngày một dấu: vẫn không đủ bằng chứng ở lại qua trưa."""
		self.assertEqual(self.flag(status="Half Day", code="1/2X", punches=("08:00",)), 0)

	def test_half_day_without_punch_does_not_count(self):
		"""Không có dấu thì không chứng minh được là ở lại qua trưa."""
		self.assertEqual(self.flag(status="Half Day", code="1/2X", punches=()), 0)

	# --- đủ dấu chấm: giữ nguyên luật cũ (phủ giờ nghỉ trưa) ---
	def test_two_punches_covering_lunch_counts(self):
		self.assertEqual(self.flag(punches=("08:00", "17:30")), 1)

	def test_two_punches_leaving_before_lunch_does_not_count(self):
		self.assertEqual(self.flag(punches=("08:00", "11:00")), 0)

	def test_half_day_covering_lunch_still_counts(self):
		self.assertEqual(self.flag(status="Half Day", code="1/2X", punches=("08:00", "17:30")), 1)

	# --- loại trừ theo mã / trạng thái ---
	def test_business_trip_never_counts(self):
		"""Đi công tác ăn ngoài, đã có Expense Claim riêng."""
		self.assertEqual(self.flag(code="CT", punches=("08:00", "17:30")), 0)

	def test_work_from_home_never_counts(self):
		self.assertEqual(self.flag(code="W", punches=("08:00", "17:30")), 0)

	def test_leave_day_does_not_count(self):
		self.assertEqual(self.flag(status="On Leave", code="P", punches=("08:00", "17:30")), 0)

	# --- override: quyết định của người, máy không đè ---
	def test_override_yes_wins_over_every_rule(self):
		self.assertEqual(self.flag(status="On Leave", code="P", punches=(), override="Có"), 1)
		self.assertEqual(self.flag(code="CT", punches=(), override="Có"), 1)

	def test_override_no_wins_over_covering_punches(self):
		self.assertEqual(self.flag(punches=("08:00", "17:30"), override="Không"), 0)

	def test_blank_override_means_automatic(self):
		for auto in (None, "", "Tự động"):
			self.assertEqual(self.flag(punches=(), override=auto), 1, auto)


class TestAutoLunchForExemptEmployees(PerTestRollback, FrappeTestCase):
	"""Người MIỄN CHẤM CÔNG: ngày `X` tự sinh chỉ được ăn trưa khi hồ sơ có tick "Tự chấm ăn trưa".

	Không có tick thì ngày tự sinh KHÔNG tự cấp phụ cấp: hệ thống sinh `X` cho mọi ngày làm việc mà
	không ai xác nhận người đó có mặt tại công ty (spec §5.8, user chốt 2026-08-27)."""

	def dt(self, hhmm):
		return get_datetime(f"2026-08-05 {hhmm}:00")

	def flag(self, punches=(), auto_filled=False, tick=False, override=None):
		from hrms.vn_payroll.lunch import effective_lunch_flag

		return effective_lunch_flag(
			"Present",
			"X",
			None,
			[self.dt(p) for p in punches],
			override,
			auto_filled=auto_filled,
			auto_lunch_when_exempt=tick,
		)

	def test_auto_filled_day_without_tick_gets_no_lunch(self):
		"""Đúng 20 ngày tháng 8 của 2 người miễn chấm công."""
		self.assertEqual(self.flag(auto_filled=True, tick=False), 0)

	def test_auto_filled_day_with_tick_gets_lunch(self):
		"""HR bật tick cho người thật sự lên văn phòng → data tự chạy chuẩn, khỏi sửa tay từng ngày."""
		self.assertEqual(self.flag(auto_filled=True, tick=True), 1)

	def test_real_punches_win_over_a_missing_tick(self):
		"""Có dấu chấm phủ giờ trưa là BẰNG CHỨNG có mặt — không cần tick."""
		self.assertEqual(self.flag(punches=("08:00", "17:30"), auto_filled=True, tick=False), 1)

	def test_manual_day_is_unaffected_by_the_tick(self):
		"""Ngày chấm tay / sửa qua soát công không phải ngày tự sinh → giữ nguyên luật cũ."""
		self.assertEqual(self.flag(auto_filled=False, tick=False), 1)

	def test_override_still_wins_on_an_auto_filled_day(self):
		self.assertEqual(self.flag(auto_filled=True, tick=False, override="Có"), 1)
		self.assertEqual(self.flag(auto_filled=True, tick=True, override="Không"), 0)
