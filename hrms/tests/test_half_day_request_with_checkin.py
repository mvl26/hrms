# Copyright (c) 2026, Miyano Việt Nam.
"""Nửa ngày làm bên ngoài (Yêu cầu chấm công) + nửa ngày chấm công tại công ty = ĐỦ một ngày.

Tình huống thật (2026-10-29): sáng đi gặp khách hàng, chiều về công ty chấm 13:30-17:30. Chấm công
chiều sinh `1/2X` (thiếu giờ, nửa kia vắng); sau đó nộp Yêu cầu chấm công nửa ngày buổi sáng.
Trước khi sửa: đơn bị chặn "No attendance records to create" (Half Day → Half Day bị coi là không
đổi), và kể cả khi lọt qua thì buổi chiều đã làm bị ghi `K` — trừ nửa ngày lương.

Luật chốt với HR:
- Có lượt chấm phủ buổi còn lại → nửa kia **Present**: `CT/X`, 1 công, payroll không trừ.
- Ngày nửa-nửa đó **có ăn trưa** (dù dấu chấm không phủ giờ trưa).
- Giờ làm: phần đơn phủ tính ĐỦ giờ ca (WFH / On Duty / Remote / Quên chấm), cộng giờ có mặt thật
  của phần còn lại. Đi muộn / về sớm giữ giờ thật.

Chạy qua harness rollback — KHÔNG `bench run-tests` trên miyano.
"""

from datetime import datetime, timedelta

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import get_time, getdate

from erpnext.setup.doctype.employee.test_employee import make_employee

from hrms.tests.isolation import PerTestRollback
from hrms.tests.vn_test_utils import default_company
from hrms.tests.work_calendar_fixture import work_every_day

SHIFT = "VN Half Outside Shift (test)"


class TestHalfDayRequestWithCheckin(PerTestRollback, FrappeTestCase):
	def setUp(self):
		from hrms.hr.doctype.shift_type.test_shift_type import setup_shift_type
		from hrms.hr.period_lock import locking_sheet

		self.date = getdate()  # cửa sổ xử lý của setup_shift_type neo vào hôm nay
		# Như "Ca Hành Chính" thật: 08:00-17:30, tách buổi, nghỉ trưa 12:00-13:30, giờ linh hoạt.
		self.shift = setup_shift_type(shift_type=SHIFT, start_time="08:00:00", end_time="17:30:00")
		self.shift.custom_split_half_day = 1
		self.shift.custom_lunch_start = timedelta(hours=12)
		self.shift.custom_lunch_end = timedelta(hours=13, minutes=30)
		self.shift.custom_flexible_shift = 1
		self.shift.custom_flex_band_minutes = 180
		self.shift.custom_min_work_hours = 8
		self.shift.save()

		self.company = default_company()
		self.emp = make_employee("vn_half_outside@codes.com", company=self.company)
		if locking_sheet(self.emp, self.date):
			self.skipTest(f"kỳ chứa {self.date} đã chốt — auto-attendance không chấm nữa")
		work_every_day(self.emp, shift=self.shift.name)
		frappe.get_doc(
			{
				"doctype": "Shift Assignment",
				"shift_type": self.shift.name,
				"company": self.company,
				"employee": self.emp,
				"start_date": self.date,
			}
		).submit()

	# --- dựng tình huống -------------------------------------------------------------------------
	def punch(self, *clock):
		from hrms.hr.doctype.employee_checkin.test_employee_checkin import make_checkin

		for c in clock:
			make_checkin(self.emp, datetime.combine(self.date, get_time(c)))
		self.shift.reload()
		self.shift.process_auto_attendance()

	def request(self, reason, half=True, session="Sáng"):
		ar = frappe.get_doc(
			{
				"doctype": "Attendance Request",
				"employee": self.emp,
				"company": self.company,
				"from_date": self.date,
				"to_date": self.date,
				"half_day": 1 if half else 0,
				"half_day_date": self.date if half else None,
				"custom_half_day_session": session if half else None,
				"reason": reason,
				"explanation": "Ra ngoài gặp khách hàng",
			}
		)
		ar.insert()
		ar.submit()
		return ar

	def day(self):
		return frappe.db.get_value(
			"Attendance",
			{"employee": self.emp, "attendance_date": self.date, "docstatus": 1},
			[
				"name",
				"status",
				"half_day_status",
				"custom_attendance_code",
				"custom_morning_code",
				"custom_afternoon_code",
				"custom_work_credit",
				"custom_lunch",
				"working_hours",
				"in_time",
				"out_time",
			],
			as_dict=True,
		)

	def payable_days(self):
		"""Đúng hai truy vấn payroll đọc cho một ngày Half Day / Absent (`get_half_absent_days` +
		`calculate_lwp_ppl_and_absent_days_based_on_attendance`)."""
		ss = frappe.new_doc("Salary Slip")
		ss.employee = self.emp
		ss.start_date = ss.end_date = self.date
		lwp, absent = ss.calculate_lwp_ppl_and_absent_days_based_on_attendance(
			holidays=[], daily_wages_fraction_for_half_day=0.5, consider_marked_attendance_on_holidays=False
		)
		half_absent = frappe.db.count(
			"Attendance",
			{
				"employee": self.emp,
				"attendance_date": self.date,
				"docstatus": 1,
				"status": "Half Day",
				"half_day_status": "Absent",
			},
		)
		return 1 - lwp - absent - 0.5 * half_absent

	def report_row(self):
		from hrms.hr.report.employee_working_hours.employee_working_hours import get_daily_rows

		rows = get_daily_rows(
			{"from_date": self.date, "to_date": self.date, "employee": self.emp, "company": self.company}
		)
		self.assertEqual(len(rows), 1)
		return rows[0]

	def office_hours(self):
		from hrms.hr.working_hours import office_hours_map

		return office_hours_map([self.emp], self.date, self.date).get(self.emp)

	# --- chấm chiều trước, nộp đơn buổi sáng sau ------------------------------------------------
	def test_checkin_then_morning_request_is_accepted(self):
		self.punch("13:30:00", "17:30:00")
		self.assertEqual(self.day().custom_attendance_code, "1/2X")

		self.request("On Duty")  # không được ném "No attendance records to create"

		self.assertIsNotNone(self.day().get("name"))

	def test_checkin_then_morning_request_is_a_full_paid_day(self):
		self.punch("13:30:00", "17:30:00")
		self.request("On Duty")

		d = self.day()
		self.assertEqual((d.status, d.half_day_status), ("Half Day", "Present"))
		self.assertEqual((d.custom_morning_code, d.custom_afternoon_code), ("CT", "X"))
		self.assertEqual(d.custom_work_credit, 1.0)
		self.assertEqual(self.payable_days(), 1.0)

	def test_remote_work_morning_keeps_the_afternoon_as_work(self):
		self.punch("13:30:00", "17:30:00")
		self.request("Remote Work")

		d = self.day()
		self.assertEqual((d.custom_morning_code, d.custom_afternoon_code), ("X", "X"))
		self.assertEqual(d.custom_work_credit, 1.0)
		self.assertEqual(self.payable_days(), 1.0)

	def test_afternoon_request_over_morning_checkin(self):
		self.punch("08:00:00", "12:00:00")
		self.request("On Duty", session="Chiều")

		d = self.day()
		self.assertEqual((d.custom_morning_code, d.custom_afternoon_code), ("X", "CT"))
		self.assertEqual(self.payable_days(), 1.0)

	# --- nộp đơn trước, chấm chiều về sau ------------------------------------------------------
	def test_request_then_afternoon_checkin_becomes_a_full_paid_day(self):
		self.request("On Duty")
		self.assertEqual(self.day().custom_afternoon_code, "K")  # chưa có lượt chấm: nửa kia chưa làm

		self.punch("13:30:00", "17:30:00")

		d = self.day()
		self.assertEqual((d.status, d.half_day_status), ("Half Day", "Present"))
		self.assertEqual((d.custom_morning_code, d.custom_afternoon_code), ("CT", "X"))
		self.assertEqual(d.custom_work_credit, 1.0)
		self.assertIsNotNone(d.in_time, "lượt chấm chiều phải gắn vào ngày công của đơn")
		self.assertEqual(self.payable_days(), 1.0)

	def test_request_without_any_checkin_stays_half_paid(self):
		# đối chứng: chỉ làm nửa ngày bên ngoài, chiều không đến → vẫn CT/K, trừ nửa ngày
		self.request("On Duty")

		d = self.day()
		self.assertEqual((d.custom_morning_code, d.custom_afternoon_code), ("CT", "K"))
		self.assertEqual(d.custom_work_credit, 0.5)
		self.assertEqual(self.payable_days(), 0.5)
		self.assertEqual(d.custom_lunch, 0)

	# --- ăn trưa ---------------------------------------------------------------------------------
	def test_half_outside_half_office_day_has_lunch(self):
		self.punch("13:30:00", "17:30:00")
		self.request("On Duty")
		self.assertEqual(self.day().custom_lunch, 1)

	def test_lunch_survives_when_checkin_arrives_after_the_request(self):
		self.request("Work From Home")
		self.punch("13:30:00", "17:30:00")
		self.assertEqual(self.day().custom_lunch, 1)

	def test_lunch_recompute_before_payroll_keeps_the_half_half_day(self):
		from hrms.vn_payroll.lunch import compute_lunch_flags_for_period

		self.punch("13:30:00", "17:30:00")
		self.request("On Duty")
		flags = compute_lunch_flags_for_period(self.date.month, self.date.year, self.company)
		self.assertEqual(flags[self.day().name], 1)

	def test_full_day_on_duty_still_has_no_lunch(self):
		self.request("On Duty", half=False)
		self.assertEqual(self.day().custom_lunch, 0)

	# --- giờ làm ---------------------------------------------------------------------------------
	def test_half_half_day_counts_a_full_shift_of_hours(self):
		self.punch("13:30:00", "17:30:00")
		self.request("On Duty")

		self.assertEqual(self.day().working_hours, 8.0)
		row = self.report_row()
		self.assertEqual((row["hours"], row["credited_hours"]), (8.0, 8.0))
		self.assertEqual(self.office_hours(), {"hours": 8.0, "days": 1.0})

	def test_request_then_checkin_counts_a_full_shift_of_hours(self):
		self.request("On Duty")
		self.assertEqual(self.day().working_hours, 4.0)  # mới có nửa buổi đơn

		self.punch("13:30:00", "17:30:00")

		self.assertEqual(self.day().working_hours, 8.0)
		self.assertEqual(self.report_row()["hours"], 8.0)

	def test_full_day_work_from_home_counts_a_full_shift(self):
		self.request("Work From Home", half=False)

		self.assertEqual(self.day().working_hours, 8.0)
		self.assertEqual(self.report_row()["hours"], 8.0)
		self.assertEqual(self.office_hours(), {"hours": 8.0, "days": 1.0})

	def test_missed_punch_counts_a_full_shift(self):
		self.request("Missed Punch", half=False)
		self.assertEqual(self.report_row()["hours"], 8.0)

	def test_late_arrival_keeps_the_real_hours(self):
		self.punch("09:30:00", "17:30:00")  # 6,5h có mặt
		self.request("Late Or Early Leave", half=False)

		self.assertEqual(self.report_row()["hours"], 6.5)
