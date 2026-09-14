# Copyright (c) 2026, Miyano Việt Nam.
"""E2E: tách lịch làm việc khỏi lịch nghỉ lễ — một tháng đầy đủ, hai trạng thái lịch.

Chạy trọn chuỗi *chấm công → bảng công → phiếu lương* ở hai trạng thái:

1. Holiday List VẪN còn các dòng nghỉ cuối tuần (trạng thái hôm nay);
2. đã gỡ chúng (trạng thái sau di trú, mô phỏng ngay trong savepoint).

Hai lượt phải cho **cùng** ký hiệu từng ngày, cùng cột tổng, và cùng bốn con số lương. Đây là bằng
chứng cuối cùng rằng việc đổi nguồn lịch không dịch một ô nào trên bảng công và không dịch một đồng
nào trên phiếu lương.

Hai tháng được chọn có chủ đích:
- **07/2026** — có một ngày lễ rơi vào thứ Sáu (ngày làm việc);
- **02/2026** — tháng Tết, có ngày lễ rơi vào thứ Bảy nên sinh ra NGHỈ BÙ vào thứ Hai kế tiếp.

Chạy qua harness rollback — KHÔNG `bench --site miyano run-tests`.
"""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt, getdate

from hrms.hr.report.monthly_attendance_report.monthly_attendance_report import get_sheet_rows
from hrms.tests.isolation import PerTestRollback
from hrms.tests.vn_test_utils import default_company, test_employee

MON_TO_FRI = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
PAYROLL_FIELDS = ("total_working_days", "payment_days", "absent_days", "leave_without_pay")

# 07/2026: 23 ngày T2-T6, lễ công ty 17/07 (thứ Sáu).
# 02/2026: 20 ngày T2-T6, Tết mùng 1-4 (17-20/02) + nghỉ bù mùng 5 vào thứ Hai 23/02.
MONTHS = {
	7: {"holidays": [("2026-07-17", "Nghỉ lễ công ty")], "scheduled": 23},
	2: {
		"holidays": [
			("2026-02-17", "Tết Nguyên Đán (mùng 1)"),
			("2026-02-18", "Tết Nguyên Đán (mùng 2)"),
			("2026-02-19", "Tết Nguyên Đán (mùng 3)"),
			("2026-02-20", "Tết Nguyên Đán (mùng 4)"),
			("2026-02-23", "Nghỉ bù Tết Nguyên Đán (mùng 5)"),
		],
		"scheduled": 20,
	},
}


class TestHolidaySeparationE2E(PerTestRollback, FrappeTestCase):
	def setUp(self):
		self.company = default_company()
		self.employee = test_employee("holiday_sep_e2e@codes.com")
		self.shift = "_Test E2E Lich Tuan"
		if not frappe.db.exists("Shift Type", self.shift):
			frappe.get_doc(
				{
					"doctype": "Shift Type",
					"__newname": self.shift,
					"start_time": "8:0:0",
					"end_time": "17:0:0",
				}
			).insert(ignore_permissions=True)
		for idx, day in enumerate(MON_TO_FRI, start=1):
			frappe.get_doc(
				{
					"doctype": "Assignment Rule Day",
					"parent": self.shift,
					"parenttype": "Shift Type",
					"parentfield": "custom_working_days",
					"day": day,
					"idx": idx,
				}
			).insert(ignore_permissions=True)
		frappe.db.set_value("Employee", self.employee, "default_shift", self.shift)
		frappe.db.set_value("Employee", self.employee, "date_of_joining", "2020-01-01")
		frappe.db.set_value("Employee", self.employee, "relieving_date", None)
		frappe.clear_cache(doctype="Employee")

	def build_holiday_list(self, holidays) -> str:
		"""Lịch của trạng thái HÔM NAY: dòng nghỉ cuối tuần + dòng lễ, y như site thật."""
		name = "_Test E2E VN 2026"
		if frappe.db.exists("Holiday List", name):
			frappe.delete_doc("Holiday List", name, force=True, ignore_permissions=True)
		doc = frappe.get_doc(
			{
				"doctype": "Holiday List",
				"holiday_list_name": name,
				"from_date": "2026-01-01",
				"to_date": "2026-12-31",
				"holidays": [
					{"holiday_date": d, "description": desc, "weekly_off": 0} for d, desc in holidays
				],
			}
		)
		for weekday in ("Saturday", "Sunday"):
			doc.weekly_off = weekday
			doc.get_weekly_off_dates()
		doc.save(ignore_permissions=True)
		frappe.db.set_value("Employee", self.employee, "holiday_list", doc.name)
		frappe.clear_cache(doctype="Employee")
		return doc.name

	def mark_month(self, month: int, days: int):
		"""Chấm Present cho mọi ngày làm việc của tháng, trừ một ngày vắng cố ý."""
		from hrms.hr.work_schedule import is_working_day

		absent_day = None
		for day in range(1, days + 1):
			d = getdate(f"2026-{month:02d}-{day:02d}")
			if not is_working_day(self.employee, d):
				continue
			if absent_day is None and day > 5:
				absent_day, status = d, "Absent"
			else:
				status = "Present"
			att = frappe.get_doc(
				{
					"doctype": "Attendance",
					"employee": self.employee,
					"attendance_date": d,
					"company": self.company,
					"status": status,
				}
			)
			att.flags.ignore_validate = True
			att.insert(ignore_permissions=True)
			att.submit()
		return absent_day

	def sheet(self, month: int) -> dict:
		rows = get_sheet_rows({"year": 2026, "month": month, "company": self.company})
		row = next(r for r in rows if r["employee"] == self.employee)
		return {"days": dict(row["days"]), "totals": dict(row["totals"])}

	def payroll(self, month: int, days: int) -> dict:
		from hrms.vn_payroll.salary_slip_hook import set_working_days

		slip = frappe.new_doc("Salary Slip")
		slip.employee = self.employee
		slip.company = frappe.db.get_value("Employee", self.employee, "company")
		slip.start_date = getdate(f"2026-{month:02d}-01")
		slip.end_date = getdate(f"2026-{month:02d}-{days:02d}")
		slip.get_working_days_details()
		set_working_days(slip)
		return {f: flt(slip.get(f)) for f in PAYROLL_FIELDS}

	def drop_weekly_off_rows(self):
		hl = frappe.db.get_value("Employee", self.employee, "holiday_list")
		frappe.db.delete("Holiday", {"parent": hl, "weekly_off": 1})
		frappe.clear_cache()

	def run_month(self, month: int, days: int):
		cfg = MONTHS[month]
		self.build_holiday_list(cfg["holidays"])
		self.mark_month(month, days)

		before = (self.sheet(month), self.payroll(month, days))
		self.drop_weekly_off_rows()
		after = (self.sheet(month), self.payroll(month, days))
		return cfg, before, after

	# --- tháng có ngày lễ rơi vào ngày làm việc -------------------------------

	def test_july_2026_is_identical_in_both_calendar_states(self):
		cfg, before, after = self.run_month(7, 31)
		self.assertEqual(before[0]["days"], after[0]["days"], "ký hiệu từng ngày phải giống hệt")
		self.assertEqual(before[0]["totals"], after[0]["totals"], "cột tổng phải giống hệt")
		self.assertEqual(before[1], after[1], "bốn con số lương phải giống hệt")
		self.assertEqual(after[1]["total_working_days"], cfg["scheduled"])

	def test_july_2026_markers_are_right(self):
		self.run_month(7, 31)
		days = self.sheet(7)["days"]
		self.assertEqual(days[25], "-", "thứ Bảy 25/07")
		self.assertEqual(days[26], "-", "Chủ nhật 26/07")
		self.assertEqual(days[17], "NL", "lễ công ty 17/07 (thứ Sáu)")
		self.assertEqual(days[21], "X", "thứ Ba 21/07 đi làm")

	# --- tháng Tết: lễ rơi vào cuối tuần -> nghỉ bù ---------------------------

	def test_february_2026_with_a_compensatory_day_is_identical(self):
		cfg, before, after = self.run_month(2, 28)
		self.assertEqual(before[0]["days"], after[0]["days"])
		self.assertEqual(before[0]["totals"], after[0]["totals"])
		self.assertEqual(before[1], after[1])
		self.assertEqual(after[1]["total_working_days"], cfg["scheduled"])

	def test_february_2026_compensatory_day_shows_as_a_paid_holiday(self):
		self.run_month(2, 28)
		days = self.sheet(2)["days"]
		self.assertEqual(days[21], "-", "thứ Bảy 21/02 (mùng 5) là ngày nghỉ cuối tuần")
		self.assertEqual(days[23], "NL", "nghỉ bù rơi vào thứ Hai 23/02")
		self.assertEqual(days[17], "NL", "Tết mùng 1")

	def test_public_holidays_count_into_the_paid_total(self):
		"""Quyết định HR 2026-08-04: ngày lễ vào Tổng công. Việc tách nguồn không được đổi điều đó."""
		self.run_month(7, 31)
		totals = self.sheet(7)["totals"]
		self.assertEqual(flt(totals.get("Nghỉ lễ")), 1.0)
		self.assertGreater(flt(totals.get("Tổng công")), 0.0)
