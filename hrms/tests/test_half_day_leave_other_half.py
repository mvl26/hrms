# Copyright (c) 2026, Miyano Việt Nam.
"""Nghỉ nửa ngày (đơn nghỉ) + nửa còn lại đi làm — kể cả làm bên ngoài theo Yêu cầu chấm công.

Tình huống (2026-10-30): sáng nghỉ không lương, chiều làm remote. Hai lỗi:

1. Job chấm công hằng giờ (`mark_absent_for_half_day_dates`) ép nửa còn lại thành **Absent** khi nửa
   đó không có lượt chấm — trái quy ước 2026-07-28 "nửa nghỉ + nửa kia không chấm công = coi như đi
   làm". Bảng công vẫn ghi 1/2P đủ công nhưng phiếu lương trừ thêm 0,5 ngày.
2. Đã có đơn nghỉ nửa ngày thì Yêu cầu chấm công cho buổi CÒN LẠI bị chặn ("No attendance records to
   create") — upstream bỏ qua mọi ngày có đơn nghỉ, kể cả nửa ngày.

Luật: đơn nghỉ giữ nguyên (mã 1/2K / 1/2P, payroll theo loại nghỉ), nửa kia Present; phần làm theo
đơn tính đủ nửa giờ ca. Đơn trùng ĐÚNG buổi đã nghỉ vẫn bị chặn.

Chạy qua harness rollback — KHÔNG `bench run-tests` trên miyano.
"""

from datetime import timedelta

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import getdate

from erpnext.setup.doctype.employee.test_employee import make_employee

from hrms.tests.isolation import PerTestRollback
from hrms.tests.vn_test_utils import default_company
from hrms.tests.work_calendar_fixture import work_every_day

SHIFT = "VN Half Leave Other Half Shift (test)"
ANNUAL, UNPAID = "Nghỉ phép năm", "Nghỉ không lương"


class TestHalfDayLeaveOtherHalf(PerTestRollback, FrappeTestCase):
	def setUp(self):
		from hrms.hr.doctype.shift_type.test_shift_type import setup_shift_type
		from hrms.hr.period_lock import locking_sheet

		self.date = getdate()  # cửa sổ xử lý của setup_shift_type neo vào hôm nay
		self.shift = setup_shift_type(shift_type=SHIFT, start_time="08:00:00", end_time="17:30:00")
		self.shift.custom_split_half_day = 1
		self.shift.custom_lunch_start = timedelta(hours=12)
		self.shift.custom_lunch_end = timedelta(hours=13, minutes=30)
		self.shift.custom_min_work_hours = 8
		self.shift.save()

		self.company = default_company()
		# Mỗi test một nhân viên: job chấm công tự `commit`, nên trên site CI (không harness) phân ca
		# và ngày công của test trước còn lại → test sau vướng MultipleShiftError / đọc nhầm ngày.
		self.emp = make_employee(
			f"vn_half_leave_other_{frappe.generate_hash(length=8)}@codes.com", company=self.company
		)
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
		frappe.get_doc(
			{
				"doctype": "Leave Allocation",
				"employee": self.emp,
				"leave_type": ANNUAL,
				"from_date": self.date.replace(month=1, day=1),
				"to_date": self.date.replace(month=12, day=31),
				"new_leaves_allocated": 12,
				"company": self.company,
			}
		).submit()

	# --- dựng tình huống -------------------------------------------------------------------------
	def leave(self, leave_type, period="Sáng"):
		code = {ANNUAL: "1/2P", UNPAID: "1/2K"}[leave_type]
		la = frappe.get_doc(
			{
				"doctype": "Leave Application",
				"employee": self.emp,
				"company": self.company,
				"leave_type": leave_type,
				"from_date": self.date,
				"to_date": self.date,
				"half_day": 1,
				"half_day_date": self.date,
				"custom_half_day_period": period,
				"custom_attendance_code": code,
				"status": "Approved",
			}
		)
		la.insert()
		la.submit()
		return la

	def request(self, reason="Remote Work", session="Chiều"):
		ar = frappe.get_doc(
			{
				"doctype": "Attendance Request",
				"employee": self.emp,
				"company": self.company,
				"from_date": self.date,
				"to_date": self.date,
				"half_day": 1,
				"half_day_date": self.date,
				"custom_half_day_session": session,
				"reason": reason,
				"explanation": "Làm remote buổi còn lại",
			}
		)
		ar.insert()
		ar.submit()
		return ar

	def hourly_job(self):
		self.shift.reload()
		self.shift.process_auto_attendance()

	def day(self):
		return frappe.db.get_value(
			"Attendance",
			{"employee": self.emp, "attendance_date": self.date, "docstatus": 1},
			[
				"name",
				"status",
				"half_day_status",
				"leave_type",
				"attendance_request",
				"custom_attendance_code",
				"custom_work_credit",
				"custom_lunch",
				"working_hours",
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

	# --- 1. job hằng giờ không trừ oan nửa còn lại ----------------------------------------------
	def test_hourly_job_keeps_the_other_half_of_annual_leave_paid(self):
		self.leave(ANNUAL)
		self.hourly_job()
		day = self.day()
		self.assertEqual(day.half_day_status, "Present")
		self.assertEqual(day.custom_attendance_code, "1/2P")
		self.assertEqual(self.payable_days(), 1.0, "nửa phép có lương + nửa kia coi như đi làm")

	def test_hourly_job_docks_unpaid_half_leave_only_once(self):
		self.leave(UNPAID)
		self.hourly_job()
		self.assertEqual(self.day().half_day_status, "Present")
		self.assertEqual(self.payable_days(), 0.5, "chỉ trừ nửa không lương, không trừ thêm nửa kia")

	def test_punches_synced_after_the_hourly_job_still_merge_into_the_leave_day(self):
		"""Job hằng giờ chạy TRƯỚC khi lượt chấm buổi chiều về (máy chấm công đồng bộ trễ). Bản cũ ép
		nửa kia Absent + tắt `modify_half_day_status` → lượt chấm về sau đâm vào bản ghi đã có, bị
		`skip_auto_attendance`; ngày vẫn ghi 1/2P đủ công nhưng phiếu lương trừ 0,5 (2026-11-03)."""
		from datetime import datetime, time

		from hrms.hr.doctype.employee_checkin.test_employee_checkin import make_checkin

		self.leave(ANNUAL, "Sáng")
		self.hourly_job()
		logs = [
			make_checkin(self.emp, datetime.combine(self.date, time(13, 30))).name,
			make_checkin(self.emp, datetime.combine(self.date, time(17, 35))).name,
		]
		self.hourly_job()

		day = self.day()
		for log in logs:
			skip, attendance = frappe.db.get_value(
				"Employee Checkin", log, ["skip_auto_attendance", "attendance"]
			)
			self.assertEqual(skip, 0, "lượt chấm nửa kia không được bị bỏ qua")
			self.assertEqual(attendance, day.name)
		self.assertEqual(day.half_day_status, "Present")
		self.assertEqual(day.custom_attendance_code, "1/2P")
		self.assertEqual(day.custom_work_credit, 1.0)
		self.assertEqual(self.payable_days(), 1.0, "phiếu lương phải khớp số công của bảng công")

	# --- 2. đơn nghỉ trước, Yêu cầu chấm công cho buổi còn lại sau ------------------------------
	def test_remote_afternoon_after_unpaid_morning_is_accepted(self):
		self.leave(UNPAID, "Sáng")
		ar = self.request("Remote Work", "Chiều")
		day = self.day()
		self.assertEqual(day.attendance_request, ar.name)
		self.assertEqual(day.leave_type, UNPAID, "đơn nghỉ giữ nguyên")
		self.assertEqual(day.half_day_status, "Present")
		self.assertEqual(day.custom_attendance_code, "1/2K")
		self.assertEqual(day.custom_work_credit, 0.5)
		self.assertEqual(self.payable_days(), 0.5)

	def test_remote_half_counts_half_a_shift_of_hours(self):
		self.leave(UNPAID, "Sáng")
		self.request("Remote Work", "Chiều")
		self.assertEqual(self.day().working_hours, 4.0)
		self.assertEqual(self.day().custom_lunch, 0)

	def test_on_duty_afternoon_after_annual_leave_morning_is_a_full_paid_day(self):
		self.leave(ANNUAL, "Sáng")
		self.request("On Duty", "Chiều")
		day = self.day()
		self.assertEqual(day.custom_attendance_code, "1/2P")
		self.assertEqual(day.custom_work_credit, 1.0)
		self.assertEqual(self.payable_days(), 1.0)

	def test_hourly_job_after_request_keeps_the_day(self):
		self.leave(UNPAID, "Sáng")
		self.request("Remote Work", "Chiều")
		self.hourly_job()
		self.assertEqual(self.day().half_day_status, "Present")
		self.assertEqual(self.payable_days(), 0.5)
		self.assertEqual(self.day().working_hours, 4.0)

	def test_request_on_the_same_half_as_the_leave_is_still_rejected(self):
		self.leave(UNPAID, "Sáng")
		with self.assertRaises(frappe.ValidationError):
			self.request("Remote Work", "Sáng")

	def test_cancelling_the_request_keeps_the_leave_day(self):
		self.leave(UNPAID, "Sáng")
		self.request("Remote Work", "Chiều").cancel()
		day = self.day()
		self.assertIsNotNone(day, "huỷ đơn chấm công không được huỷ luôn ngày nghỉ")
		self.assertEqual(day.leave_type, UNPAID)
		self.assertIsNone(day.attendance_request)
		self.assertEqual(day.working_hours, 0.0)
		self.assertEqual(self.payable_days(), 0.5)

	# --- 3. thứ tự ngược: Yêu cầu chấm công trước, đơn nghỉ sau ---------------------------------
	def test_request_first_then_unpaid_leave(self):
		self.request("Remote Work", "Chiều")
		self.leave(UNPAID, "Sáng")
		day = self.day()
		self.assertEqual(day.custom_attendance_code, "1/2K")
		self.assertEqual(day.half_day_status, "Present")
		self.assertEqual(self.payable_days(), 0.5)
		self.assertEqual(day.working_hours, 4.0)

	def test_cancelling_the_earlier_request_keeps_the_later_leave_day(self):
		ar = self.request("Remote Work", "Chiều")
		self.leave(UNPAID, "Sáng")
		ar.reload()
		ar.cancel()
		day = self.day()
		self.assertIsNotNone(day)
		self.assertEqual(day.leave_type, UNPAID)
		self.assertEqual(self.payable_days(), 0.5)

	# --- 4. patch sửa dữ liệu đã hỏng bởi bản job cũ -------------------------------------------
	def damage_like_the_old_hourly_job(self):
		"""Trạng thái bản job cũ để lại: nửa kia Absent, cờ gộp tắt, lượt chấm về sau bị skip."""
		from datetime import datetime, time

		from hrms.hr.doctype.employee_checkin.test_employee_checkin import make_checkin

		self.leave(ANNUAL, "Chiều")
		frappe.db.set_value(
			"Attendance", self.day().name, {"half_day_status": "Absent", "modify_half_day_status": 0}
		)
		logs = [
			make_checkin(self.emp, datetime.combine(self.date, time(9, 10))).name,
			make_checkin(self.emp, datetime.combine(self.date, time(13, 24))).name,
		]
		self.hourly_job()
		for log in logs:
			self.assertEqual(frappe.db.get_value("Employee Checkin", log, "skip_auto_attendance"), 1)
		self.assertEqual(self.payable_days(), 0.5, "tiền đề: bản ghi hỏng làm phiếu lương trừ 0,5")
		return logs

	def test_patch_repairs_the_other_half_and_lets_the_punches_merge(self):
		from hrms.patches.v15_0.repair_half_day_leave_other_half_absent import execute

		logs = self.damage_like_the_old_hourly_job()
		execute()
		self.assertEqual(self.day().half_day_status, "Present")
		self.assertEqual(self.payable_days(), 1.0, "nửa phép có lương + nửa kia đi làm = đủ 1 ngày")

		self.hourly_job()
		day = self.day()
		for log in logs:
			self.assertEqual(frappe.db.get_value("Employee Checkin", log, "attendance"), day.name)
		self.assertGreater(day.working_hours, 0)
		self.assertEqual(day.half_day_status, "Present")
		self.assertEqual(day.custom_attendance_code, "1/2P")
		self.assertEqual(day.custom_work_credit, 1.0)
		self.assertEqual(self.payable_days(), 1.0)

	def test_patch_leaves_locked_periods_alone(self):
		from unittest.mock import patch

		from hrms.patches.v15_0.repair_half_day_leave_other_half_absent import execute

		self.damage_like_the_old_hourly_job()
		with patch("hrms.hr.period_lock.is_period_locked", return_value=True):
			execute()
		self.assertEqual(self.day().half_day_status, "Absent", "kỳ đã chốt: không sửa lén số đã ký")

	# --- 5. mã công là chuẩn: Công trên bản ghi = số ngày phiếu lương trả (HR chốt 2026-11-03) ------
	def test_review_correction_to_a_half_leave_code_pays_what_the_code_says(self):
		from hrms.hr.attendance_review import apply_correction

		short = frappe.get_doc(
			{
				"doctype": "Attendance",
				"employee": self.emp,
				"attendance_date": self.date,
				"company": self.company,
				"custom_attendance_code": "1/2X",
			}
		)
		short.insert()
		short.submit()
		self.assertEqual(self.day().half_day_status, "Absent", "tiền đề: 1/2X trừ nửa kia")

		apply_correction(short.name, "1/2P", "nửa ngày nghỉ phép, quên làm đơn")
		day = self.day()
		self.assertEqual(day.half_day_status, "Present")
		self.assertEqual(self.payable_days(), day.custom_work_credit)
		self.assertEqual(self.payable_days(), 1.0)

	def test_half_leave_code_entered_by_hand_over_an_absent_half_pays_in_full(self):
		self.leave(ANNUAL, "Sáng")
		frappe.get_doc("Attendance", self.day().name).cancel()
		hand = frappe.get_doc(
			{
				"doctype": "Attendance",
				"employee": self.emp,
				"attendance_date": self.date,
				"company": self.company,
				"custom_attendance_code": "1/2P",
				"half_day_status": "Absent",
			}
		)
		hand.insert()
		hand.submit()
		day = self.day()
		self.assertEqual(day.half_day_status, "Present")
		self.assertEqual(self.payable_days(), day.custom_work_credit)
		self.assertEqual(self.payable_days(), 1.0)

	def test_short_hours_on_the_worked_half_do_not_dock_a_half_leave_day(self):
		"""Chu Văn Hiếu 16/10/2026: chiều nghỉ phép, sáng chấm 09:10:48 → 13:23:58 (2,8h sau khi trừ
		nghỉ trưa). Giờ làm dưới ngưỡng VẮNG của ca (ngưỡng cho CẢ ngày) → lượt gộp ghi nửa kia
		Absent → phiếu lương 0,5 trong khi Công 1. Đi muộn / thiếu giờ để bước soát công bắt, không
		được lặng lẽ trừ nửa ngày lương."""
		from datetime import datetime, time

		from hrms.hr.doctype.employee_checkin.test_employee_checkin import make_checkin

		self.shift.working_hours_threshold_for_absent = 4
		self.shift.save()
		self.leave(ANNUAL, "Chiều")
		make_checkin(self.emp, datetime.combine(self.date, time(9, 10, 48)))
		make_checkin(self.emp, datetime.combine(self.date, time(12, 0)))
		self.hourly_job()

		day = self.day()
		self.assertGreater(day.working_hours, 0, "lượt chấm đã gộp vào ngày nghỉ")
		self.assertEqual(day.half_day_status, "Present")
		self.assertEqual(day.custom_attendance_code, "1/2P")
		self.assertEqual(self.payable_days(), day.custom_work_credit)
		self.assertEqual(self.payable_days(), 1.0)

	def test_hand_made_record_choosing_absent_on_an_approved_half_day_leave_pays_in_full(self):
		"""HR-ATT-2026-04029 (Chu Văn Hiếu 16/10/2026): HR tạo TAY Attendance, chọn Half Day + Nghỉ phép
		năm + Status for Other Half = Absent, KHÔNG nhập mã công, trên ngày có đơn nghỉ nửa ngày đã duyệt
		và có giờ vào/ra. Ngày có đơn nghỉ nửa buổi thì nửa kia đi làm (HR 2026-07-28) — người nhập chọn
		gì ở ô nửa kia cũng không được trừ 0,5."""
		self.leave(ANNUAL, "Chiều")
		frappe.get_doc("Attendance", self.day().name).cancel()
		hand = frappe.get_doc(
			{
				"doctype": "Attendance",
				"employee": self.emp,
				"attendance_date": self.date,
				"company": self.company,
				"status": "Half Day",
				"leave_type": ANNUAL,
				"half_day_status": "Absent",
				"in_time": f"{self.date} 09:10:48",
				"out_time": f"{self.date} 13:23:58",
				"working_hours": 2.8,
			}
		)
		hand.insert()
		hand.submit()
		day = self.day()
		self.assertEqual(day.half_day_status, "Present")
		self.assertEqual(day.custom_attendance_code, "1/2P")
		self.assertEqual(self.payable_days(), day.custom_work_credit)
		self.assertEqual(self.payable_days(), 1.0)

	def test_patch_does_not_reopen_a_day_whose_punches_are_already_merged(self):
		"""`modify_half_day_status = 1` là đúng cái cờ job đánh vắng bản cũ nhắm vào: bật lại nó cho một
		ngày đã gộp xong lượt chấm thì server còn chạy code cũ (hoặc chưa restart) sẽ ép Absent lại ở
		lần auto-attendance kế tiếp — "soát công xong hết lỗi, chạy auto attendance lại lỗi"."""
		from datetime import datetime, time

		from hrms.hr.doctype.employee_checkin.test_employee_checkin import make_checkin
		from hrms.patches.v15_0.repair_half_day_leave_other_half_absent import execute

		self.leave(ANNUAL, "Chiều")
		make_checkin(self.emp, datetime.combine(self.date, time(9, 10, 48)))
		make_checkin(self.emp, datetime.combine(self.date, time(13, 23, 58)))
		self.hourly_job()
		name = self.day().name
		frappe.db.set_value("Attendance", name, {"half_day_status": "Absent", "modify_half_day_status": 0})

		execute()
		self.assertEqual(self.day().half_day_status, "Present")
		self.assertEqual(frappe.db.get_value("Attendance", name, "modify_half_day_status"), 0)

	def test_consistency_scan_flags_the_broken_day_and_clears_after_the_patch(self):
		from hrms.attendance_payroll_consistency import mismatches
		from hrms.patches.v15_0.repair_half_day_leave_other_half_absent import execute

		self.damage_like_the_old_hourly_job()
		rows = mismatches(self.date, self.date, self.emp)
		self.assertEqual([r.name for r in rows], [self.day().name])
		self.assertEqual((rows[0].cong, rows[0].payroll_days), (1.0, 0.5))

		execute()
		self.assertEqual(mismatches(self.date, self.date, self.emp), [])
