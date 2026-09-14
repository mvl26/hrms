# Copyright (c) 2026, Miyano Việt Nam.
"""Ghi tay một ngày công vào ngày ngoài lịch — bảng công và phiếu lương không được lệch.

HR được phép chấm công vào thứ Bảy (quyết định 2026-08-30). Hệ quả phải xử: ô đó hiện ký hiệu để HR
thấy có người đi làm, nhưng KHÔNG cộng vào cột tổng nào — vì `set_working_days` đếm mẫu số theo lịch
tuần, `payment_days` không nhúc nhích, mà `sheet_gate.reconcile_with_sheet` so đúng hai con số này và
lệch quá `TOLERANCE` thì chặn sạch mọi phiếu lương của tháng.

Chạy qua harness rollback — KHÔNG `bench --site miyano run-tests`.
"""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt, getdate

from hrms.hr.report.monthly_attendance_report.monthly_attendance_report import (
	TOTAL_PAID,
	get_sheet_rows,
)
from hrms.tests.isolation import PerTestRollback
from hrms.tests.work_calendar_fixture import BRIDGE_SAME_MONTH, build_scenario, month_range

# Tháng 6/2027 — không dính cặp nghỉ ghép/làm bù nào, để phép đo chỉ nói về đúng một biến.
YEAR, MONTH = 2027, 6
SATURDAY = "2027-06-19"
SUNDAY = "2027-06-20"
WEDNESDAY = "2027-06-16"  # cũng là ngày lễ riêng của công ty


class TestManualAttendanceOnRestDay(PerTestRollback, FrappeTestCase):
	def setUp(self):
		self.scenario = build_scenario()
		self.employee = self.scenario.employees["A"]

	def mark(self, day, status="Present", code=None):
		att = frappe.get_doc(
			{
				"doctype": "Attendance",
				"employee": self.employee,
				"attendance_date": getdate(day),
				"company": self.scenario.company,
				"status": status,
				"custom_attendance_code": code,
			}
		)
		att.flags.ignore_validate = True
		att.insert(ignore_permissions=True)
		att.submit()
		return att

	def mark_full_month(self, month=MONTH):
		"""Chấm Present cho MỌI ngày phải đi làm của tháng.

		Cần chấm đủ thì hai vế mới so được: `Tổng công` đếm bản ghi thật, còn `payment_days` mặc
		định coi ngày chưa chấm là Present (`consider_unmarked_attendance_as`). Đây cũng đúng trạng
		thái lúc chốt công thật — bảng chỉ được chốt khi công đã đủ.

		Ngày lễ cố ý KHÔNG chấm: bảng công tự cộng nó qua nhánh `NL`, và phiếu lương cũng đã tính
		nó trong mẫu số.
		"""
		from hrms.hr.work_schedule import dates_in_range, is_working_day

		start, end = month_range(f"{YEAR}-{month:02d}-01")
		for d in dates_in_range(start, end):
			if is_working_day(self.employee, d):
				self.mark(d)

	def row(self, month=MONTH):
		rows = get_sheet_rows({"year": YEAR, "month": month, "company": self.scenario.company})
		return next(r for r in rows if r["employee"] == self.employee)

	def payment_days(self, month=MONTH):
		"""`payment_days` đi qua ĐÚNG đường thật: controller tính rồi hook đặt lại."""
		from hrms.vn_payroll.salary_slip_hook import set_working_days

		start, end = month_range(f"{YEAR}-{month:02d}-01")
		slip = frappe.new_doc("Salary Slip")
		slip.employee = self.employee
		slip.company = frappe.db.get_value("Employee", self.employee, "company")
		slip.start_date, slip.end_date = getdate(start), getdate(end)
		slip.get_working_days_details()
		set_working_days(slip)
		return flt(slip.payment_days)

	def drop_weekly_off_rows(self):
		frappe.db.delete("Holiday", {"parent": self.scenario.holiday_list, "weekly_off": 1})
		frappe.clear_cache()

	# --- cổng: bảng công phải khớp phiếu lương --------------------------------

	def test_a_manual_workday_on_a_saturday_keeps_sheet_and_slip_in_step(self):
		"""Defect cụ thể mà quyết định "cho phép ghi tay" mở ra.

		Không có quy tắc này thì Tổng công = 23 còn payment_days = 22 -> `reconcile_with_sheet`
		chặn SẠCH mọi phiếu lương của tháng đó."""
		self.mark_full_month()
		self.assertEqual(flt(self.row()["totals"].get(TOTAL_PAID)), self.payment_days())

		self.mark(SATURDAY)
		self.assertEqual(flt(self.row()["totals"].get(TOTAL_PAID)), self.payment_days())

	def test_sheet_and_slip_agree_after_the_migration_too(self):
		"""Bất biến phải đúng ở CẢ HAI trạng thái lịch, không chỉ trạng thái hôm nay."""
		self.mark_full_month()
		self.mark(SATURDAY)
		self.drop_weekly_off_rows()
		self.assertEqual(flt(self.row()["totals"].get(TOTAL_PAID)), self.payment_days())

	# --- hiển thị vẫn phải thấy -----------------------------------------------

	def test_the_symbol_still_shows_on_a_rest_day(self):
		"""Không giấu ngày đó đi — HR phải nhìn ra ai đi làm thứ Bảy."""
		self.mark(SATURDAY)
		self.assertEqual(self.row()["days"][19], "X")

	# --- nhưng không cộng vào cột tổng nào ------------------------------------

	def test_a_rest_day_record_adds_to_no_total(self):
		before = dict(self.row()["totals"])
		self.mark(SATURDAY)
		self.assertEqual(dict(self.row()["totals"]), before)

	def test_an_absent_row_on_a_sunday_docks_nothing(self):
		"""Chiều ngược lại: `V` ghi nhầm vào Chủ nhật không được trừ vào cột Vắng."""
		before = dict(self.row()["totals"])
		self.mark(SUNDAY, status="Absent", code="V")
		self.assertEqual(dict(self.row()["totals"]), before)

	# --- ngày lễ và ngày làm bù KHÔNG thuộc quy tắc này -----------------------

	def test_working_on_a_public_holiday_still_counts(self):
		"""Ngày lễ nằm TRONG lịch tuần nên vẫn cộng bình thường."""
		before = flt(self.row()["totals"].get(TOTAL_PAID))
		self.mark(WEDNESDAY)
		self.assertEqual(flt(self.row()["totals"].get(TOTAL_PAID)), before)
		self.assertEqual(self.row()["days"][16], "X")

	def test_working_on_a_make_up_day_counts_normally(self):
		"""Ngày `Làm bù` LÀ ngày làm việc -> cộng tổng như mọi ngày công khác."""
		_, make_up = BRIDGE_SAME_MONTH
		month = getdate(make_up).month
		before = flt(self.row(month)["totals"].get(TOTAL_PAID))
		self.mark(make_up)
		self.assertEqual(flt(self.row(month)["totals"].get(TOTAL_PAID)), before + 1.0)
		self.assertEqual(self.row(month)["days"][getdate(make_up).day], "X")
