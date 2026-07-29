# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# See license.txt
"""End-to-end scenario tests for the VN timekeeping → payroll chain (Miyano).

Self-contained: every test builds its own employees / attendance / check-ins, so it runs both in
CI (test_site) and via the miyano rollback console harness. Covers, with realistic full-month data:
  1. mã công forward bridge for ALL 14 codes through the real insert+submit path (check_leave_record
     runs), incl. the half-day-leave fix;
  2. attendance-based payroll figures (payment_days / absent_days / leave_without_pay) for a month
     mixing every deduction shape — the numbers that decide "tính lương";
  3. the Bảng Công Tháng report totals across every category + calendar markers, multi-employee;
  4. check-in → process_auto_attendance → Attendance (auto-attendance ingestion + VN classifier).

Payroll is exercised through SalarySlip.get_working_days_details (no salary structure needed), so
the payroll-relevant numbers are proven without ERPNext's _Test Company chart-of-accounts fixtures.
"""

from datetime import datetime, timedelta

import frappe
from frappe.tests.utils import FrappeTestCase, change_settings
from frappe.utils import get_time, getdate

from erpnext.setup.doctype.employee.test_employee import make_employee

from hrms.tests.vn_test_utils import default_company


def mk_attendance(employee, date, submit=True, **codes):
	att = frappe.get_doc(
		{"doctype": "Attendance", "employee": employee, "attendance_date": getdate(date), **codes}
	)
	att.insert()
	if submit:
		att.submit()
	return att


# (code, expected status, expected leave_type, expected work_credit, expected half_day_status|None)
ALL_CODES = [
	("X", "Present", None, 1.0, None),
	("CT", "Work From Home", None, 1.0, None),
	("P", "On Leave", "Nghỉ phép năm", 0.0, None),
	("Ô", "On Leave", "Nghỉ ốm", 0.0, None),
	("Cô", "On Leave", "Nghỉ chăm con ốm", 0.0, None),
	("TS", "On Leave", "Nghỉ thai sản", 0.0, None),
	("T", "On Leave", "Nghỉ tai nạn lao động", 0.0, None),
	("NB", "On Leave", "Nghỉ bù", 0.0, None),
	("K", "On Leave", "Nghỉ không lương", 0.0, None),
	("KH", "On Leave", "Nghỉ kết hôn", 0.0, None),
	("V", "Absent", None, 0.0, None),
	("NN", "Half Day", None, 0.5, "Absent"),  # worked half + unexcused half
	("1/2P", "Half Day", "Nghỉ phép năm", 0.5, "Present"),  # worked half + paid-leave half
	("1/2K", "Half Day", "Nghỉ không lương", 0.5, "Present"),  # worked half + unpaid-leave half
]


class TestAllCodesForwardBridge(FrappeTestCase):
	"""Every mã công produces the right native triple through the real submit path."""

	def test_all_14_codes_map_correctly(self):
		emp = make_employee("e2e_allcodes@codes.com", company=default_company())
		for i, (code, status, leave_type, credit, hds) in enumerate(ALL_CODES, start=1):
			att = mk_attendance(emp, f"2099-06-{i:02d}", custom_attendance_code=code)
			self.assertEqual(att.status, status, f"{code}: status")
			self.assertEqual(att.custom_work_credit, credit, f"{code}: work_credit")
			if leave_type is None:
				self.assertIn(att.leave_type, (None, ""), f"{code}: leave_type should be empty")
			else:
				self.assertEqual(att.leave_type, leave_type, f"{code}: leave_type")
			if hds is not None:
				self.assertEqual(att.half_day_status, hds, f"{code}: half_day_status")


class TestPayrollDaysScenarios(FrappeTestCase):
	"""Attendance-based payroll figures for a full month mixing every deduction shape."""

	@change_settings(
		"Payroll Settings",
		{
			"payroll_based_on": "Attendance",
			"daily_wages_fraction_for_half_day": 0.5,
			"consider_unmarked_attendance_as": "Present",
		},
	)
	def test_month_mixed_codes_payment_days(self):
		emp = make_employee("e2e_payroll@codes.com", company=default_company())
		company = frappe.db.get_value("Employee", emp, "company")
		# June 2099, no holiday list covers it -> a clean 30 working days.
		plan = {
			1: "X",  # present        -> 0
			2: "P",  # annual leave   -> 0 (paid, not in LWP map)
			3: "Ô",  # sick leave     -> 0 (paid)
			4: "KH",  # personal leave (kết hôn) -> 0 (paid)
			5: "CT",  # business trip  -> 0 (WFH, not read by payroll)
			6: "K",  # unpaid leave   -> lwp 1.0
			7: "V",  # absent         -> absent 1.0
			8: "1/2P",  # half paid leave  -> 0 (the fix; was 0.5)
			9: "1/2K",  # half unpaid leave -> lwp 0.5 (not doubled by the fix)
			10: "NN",  # half worked      -> half-absent 0.5
		}
		for day, code in plan.items():
			mk_attendance(emp, f"2099-06-{day:02d}", custom_attendance_code=code)

		ss = frappe.new_doc("Salary Slip")
		ss.employee = emp
		ss.company = company
		ss.start_date = getdate("2099-06-01")
		ss.end_date = getdate("2099-06-30")
		ss.get_working_days_details()

		self.assertEqual(ss.leave_without_pay, 1.5, "K 1.0 + 1/2K 0.5")
		self.assertEqual(ss.absent_days, 1.5, "V 1.0 + NN half-absent 0.5")
		# payment_days = total_working_days - lwp(1.5) - absent(V 1.0) - half_absent(NN 0.5)
		self.assertEqual(ss.total_working_days - ss.payment_days, 3.0)

	@change_settings(
		"Payroll Settings",
		{
			"payroll_based_on": "Attendance",
			"daily_wages_fraction_for_half_day": 0.5,
			"consider_unmarked_attendance_as": "Absent",
		},
	)
	def test_half_paid_leave_not_docked_even_when_unmarked_is_absent(self):
		# regression for the fix: a paid half-day leave must never be docked, even in the strict
		# "unmarked = Absent" mode where every other blank day is docked.
		emp = make_employee("e2e_payroll_strict@codes.com", company=default_company())
		company = frappe.db.get_value("Employee", emp, "company")
		# mark the whole month present except one 1/2P day, so unmarked-absent does not interfere
		for day in range(1, 31):
			code = "1/2P" if day == 15 else "X"
			mk_attendance(emp, f"2099-06-{day:02d}", custom_attendance_code=code)

		ss = frappe.new_doc("Salary Slip")
		ss.employee = emp
		ss.company = company
		ss.start_date = getdate("2099-06-01")
		ss.end_date = getdate("2099-06-30")
		ss.get_working_days_details()

		self.assertEqual(ss.leave_without_pay, 0.0)
		self.assertEqual(ss.absent_days, 0.0)  # 1/2P must NOT count as a half-absent
		self.assertEqual(ss.total_working_days, ss.payment_days)  # full pay


class TestBangCongMonthEndToEnd(FrappeTestCase):
	"""Bảng Công Tháng report: every category total + calendar markers, over a realistic month."""

	def test_every_category_total_and_markers(self):
		from hrms.hr.report.monthly_attendance_report.monthly_attendance_report import get_sheet_rows

		worker = make_employee("e2e_bcct_worker@codes.com", company=default_company())
		plan = {
			1: "X",
			2: "P",
			3: "Ô",
			4: "Cô",
			5: "K",
			6: "V",
			7: "NN",
			8: "1/2P",
			9: "1/2K",
			10: "KH",
			11: "TS",
			12: "NB",
			13: "T",
		}
		for day, code in plan.items():
			mk_attendance(worker, f"2099-06-{day:02d}", custom_attendance_code=code)

		rows = get_sheet_rows({"month": 6, "year": 2099})
		row = next(r for r in rows if r["employee"] == worker)
		t = row["totals"]
		self.assertEqual(t["Công"], 2.5, "X1 + NN.5 + 1/2P.5 + 1/2K.5")
		self.assertEqual(t["Phép"], 1.5, "P1 + 1/2P.5")
		self.assertEqual(t["Ốm"], 2.0, "Ô1 + Cô1")
		self.assertEqual(t["Không lương"], 1.5, "K1 + 1/2K.5")
		self.assertEqual(t["Vắng"], 1.5, "V1 + NN.5")
		self.assertEqual(t["Việc riêng"], 1.0)
		self.assertEqual(t["Thai sản"], 1.0)
		self.assertEqual(t["Nghỉ bù"], 1.0)
		self.assertEqual(t["Tai nạn LĐ"], 1.0)
		# cell rendering
		self.assertEqual(row["days"][1], "X")
		self.assertEqual(row["days"][8], "1/2P")

	def test_holiday_rest_and_terminated_markers(self):
		from hrms.hr.report.monthly_attendance_report.monthly_attendance_report import get_sheet_rows

		hl = frappe.get_doc(
			{
				"doctype": "Holiday List",
				"holiday_list_name": "E2E BCCT HL 2099-06",
				"from_date": "2099-06-01",
				"to_date": "2099-06-30",
				"holidays": [
					{"holiday_date": "2099-06-07", "description": "CN", "weekly_off": 1},
					{"holiday_date": "2099-06-02", "description": "Lễ", "weekly_off": 0},
				],
			}
		).insert()
		emp = make_employee("e2e_bcct_markers@codes.com", company=default_company())
		frappe.db.set_value(
			"Employee", emp, {"holiday_list": hl.name, "relieving_date": "2099-06-20", "status": "Left"}
		)
		rows = get_sheet_rows({"month": 6, "year": 2099})
		row = next(r for r in rows if r["employee"] == emp)
		self.assertEqual(row["days"][7], "-", "weekly-off rest day")
		self.assertEqual(row["days"][2], "NL", "paid public holiday stays visible")
		self.assertEqual(row["days"][25], "-", "after relieving date")


class TestCheckinAutoAttendanceE2E(FrappeTestCase):
	"""Check-in → process_auto_attendance → Attendance, including the VN split-half-day classifier."""

	def _shift(self, name, split=False):
		from hrms.hr.doctype.shift_type.test_shift_type import setup_shift_type

		st = setup_shift_type(shift_type=name, start_time="08:00:00", end_time="17:00:00")
		if split:
			st.custom_split_half_day = 1
			st.custom_lunch_start = timedelta(hours=12)
			st.custom_lunch_end = timedelta(hours=13, minutes=30)
		st.save()
		return st

	def _assign(self, shift_type, employee, date):
		frappe.get_doc(
			{
				"doctype": "Shift Assignment",
				"shift_type": shift_type,
				"company": frappe.db.get_value("Employee", employee, "company"),
				"employee": employee,
				"start_date": date,
			}
		).submit()

	def test_full_day_checkins_create_present_attendance(self):
		from hrms.hr.doctype.employee_checkin.test_employee_checkin import make_checkin

		st = self._shift("E2E Full Day Shift")
		emp = make_employee("e2e_checkin_full@codes.com", company=default_company())
		date = getdate()  # setup_shift_type's process window is anchored on today
		self._assign(st.name, emp, date)
		make_checkin(emp, datetime.combine(date, get_time("08:00:00")))
		make_checkin(emp, datetime.combine(date, get_time("17:05:00")))

		st.process_auto_attendance()

		att = frappe.db.get_value(
			"Attendance",
			{"employee": emp, "attendance_date": date, "docstatus": 1},
			["status", "working_hours"],
			as_dict=True,
		)
		self.assertIsNotNone(att, "auto-attendance did not create an Attendance from the check-ins")
		self.assertEqual(att.status, "Present")

	def test_morning_only_checkins_classified_as_half_day(self):
		from hrms.hr.doctype.employee_checkin.test_employee_checkin import make_checkin

		st = self._shift("E2E Split Shift", split=True)
		emp = make_employee("e2e_checkin_half@codes.com", company=default_company())
		date = getdate()  # setup_shift_type's process window is anchored on today
		self._assign(st.name, emp, date)
		# only the morning window is covered -> classifier: token đơn 1/2K (làm nửa + nửa không lương) -> Half Day
		make_checkin(emp, datetime.combine(date, get_time("08:00:00")))
		make_checkin(emp, datetime.combine(date, get_time("12:00:00")))

		st.process_auto_attendance()

		att = frappe.db.get_value(
			"Attendance",
			{"employee": emp, "attendance_date": date, "docstatus": 1},
			["status", "custom_attendance_code"],
			as_dict=True,
		)
		self.assertIsNotNone(att, "auto-attendance did not create an Attendance")
		self.assertEqual(att.status, "Half Day")
		self.assertEqual(att.custom_attendance_code, "1/2K")
