# Copyright (c) 2026, Miyano Việt Nam.
"""Khoá kỳ: chốt công rồi thì ngày công trong kỳ không thêm/sửa/huỷ được nữa."""

import frappe
from frappe.tests.utils import FrappeTestCase

from hrms.hr.period_lock import is_period_locked, locking_sheet
from hrms.tests.isolation import PerTestRollback
from hrms.tests.vn_test_utils import ensure_short_hours_code, test_employee


class TestPeriodLock(PerTestRollback, FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		ensure_short_hours_code()
		cls.emp = test_employee()
		cls.company = frappe.db.get_value("Employee", cls.emp, "company")

	def mk_sheet(self, month, year=2099, submit=True, department=None):
		sheet = frappe.get_doc(
			{
				"doctype": "Monthly Attendance Sheet",
				"company": self.company,
				"month": str(month),
				"year": year,
				"department": department,
			}
		).insert()
		if submit:
			sheet.submit()
		return sheet

	def mk_attendance(self, day, month=11, year=2099, submit=True, **kw):
		doc = frappe.get_doc(
			{
				"doctype": "Attendance",
				"employee": self.emp,
				"attendance_date": f"{year}-{month:02d}-{day:02d}",
				"company": self.company,
				"status": "Present",
				**kw,
			}
		).insert()
		if submit:
			doc.submit()
		return doc

	def test_an_open_period_is_not_locked(self):
		self.assertFalse(is_period_locked(self.emp, "2099-11-05"))

	def test_a_submitted_sheet_locks_its_own_month_only(self):
		sheet = self.mk_sheet(11)
		self.assertEqual(locking_sheet(self.emp, "2099-11-05"), sheet.name)
		self.assertIsNone(locking_sheet(self.emp, "2099-12-05"))

	def test_a_draft_sheet_locks_nothing(self):
		self.mk_sheet(11, submit=False)
		self.assertFalse(is_period_locked(self.emp, "2099-11-05"))

	def test_a_cancelled_sheet_reopens_the_period(self):
		sheet = self.mk_sheet(11)
		self.assertTrue(is_period_locked(self.emp, "2099-11-05"))
		sheet.cancel()
		self.assertFalse(is_period_locked(self.emp, "2099-11-05"))

	def test_a_sheet_for_another_department_does_not_lock_this_employee(self):
		other = frappe.db.get_value("Department", {"name": ["!=", ""]}, "name")
		emp_dept = frappe.db.get_value("Employee", self.emp, "department")
		if not other or other == emp_dept:
			self.skipTest("site không có phòng ban khác để phân biệt")
		self.mk_sheet(11, department=other)
		self.assertFalse(is_period_locked(self.emp, "2099-11-05"))

	def test_creating_attendance_inside_a_locked_period_is_blocked(self):
		self.mk_sheet(11)
		with self.assertRaises(frappe.exceptions.ValidationError):
			self.mk_attendance(6)

	def test_cancelling_attendance_inside_a_locked_period_is_blocked(self):
		att = self.mk_attendance(7)
		self.mk_sheet(11)
		with self.assertRaises(frappe.exceptions.ValidationError):
			att.cancel()

	def test_correcting_attendance_inside_a_locked_period_is_blocked(self):
		from hrms.hr.attendance_review import apply_correction

		att = self.mk_attendance(8)
		self.mk_sheet(11)
		with self.assertRaises(frappe.exceptions.ValidationError):
			apply_correction(att.name, "1/2X", "sửa sau khi đã chốt")

	def test_correcting_is_allowed_again_after_the_sheet_is_cancelled(self):
		from hrms.hr.attendance_review import apply_correction

		att = self.mk_attendance(9)
		sheet = self.mk_sheet(11)
		sheet.cancel()
		apply_correction(att.name, "1/2X", "mở lại kỳ để sửa theo biên bản")
		self.assertEqual(frappe.db.get_value("Attendance", att.name, "status"), "Half Day")


class TestLockedPeriodStopsAutoAttendance(PerTestRollback, FrappeTestCase):
	"""Kỳ đã chốt thì auto-attendance phải LẶNG LẼ bỏ qua, không được ném lỗi.

	Ném ở đây là giết cả job `process_auto_attendance_for_all_shifts` cho mọi nhân viên còn lại chỉ
	vì một kỳ đã khoá — đúng lỗi đã suýt lên production ngày 2026-07-29 (bảng T7 chốt giữa tháng
	trong khi tháng chưa hết, scheduler vẫn phải chấm những ngày sau đó)."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.emp = test_employee()
		cls.company = frappe.db.get_value("Employee", cls.emp, "company")
		cls.shift = "VN Lock Shift (test)"
		if not frappe.db.exists("Shift Type", cls.shift):
			frappe.get_doc(
				{
					"doctype": "Shift Type",
					"__newname": cls.shift,
					"start_time": "08:00:00",
					"end_time": "17:30:00",
					"enable_auto_attendance": 1,
				}
			).insert()

	def test_should_mark_attendance_says_no_inside_a_locked_period(self):
		shift = frappe.get_doc("Shift Type", self.shift)
		self.assertTrue(shift.should_mark_attendance(self.emp, "2099-11-05"))

		frappe.get_doc(
			{
				"doctype": "Monthly Attendance Sheet",
				"company": self.company,
				"month": "11",
				"year": 2099,
			}
		).insert().submit()

		self.assertFalse(shift.should_mark_attendance(self.emp, "2099-11-05"))

	def test_absent_marking_skips_locked_dates(self):
		shift = frappe.get_doc("Shift Type", self.shift)
		frappe.get_doc(
			{
				"doctype": "Monthly Attendance Sheet",
				"company": self.company,
				"month": "11",
				"year": 2099,
			}
		).insert().submit()

		dates = shift.get_dates_for_attendance(self.emp)
		locked = [d for d in dates if str(d).startswith("2099-11")]
		self.assertEqual(locked, [], "không được chấm vắng vào kỳ đã chốt")


class TestLockCoversEveryWritePath(PerTestRollback, FrappeTestCase):
	"""Khoá kỳ phải đứng trước MỌI đường ghi lên Attendance, không chỉ đường đi qua hook.

	Hook `guard_period_not_locked` chỉ chạy khi Attendance được insert / sửa sau submit / huỷ qua
	`Document`. Nhưng đơn nghỉ, Yêu cầu chấm công, job nửa ngày và lượt tính lại ăn trưa đều ghi
	bằng `db_set` / `set_value` — thẳng xuống DB, không hook nào chạy. Trước bản sửa này, chốt công
	xong vẫn duyệt được đơn nghỉ lùi ngày vào kỳ đã khoá: Attendance đổi, phiếu lương đổi theo,
	còn bảng công đã ký thì đứng im.
	"""

	LEAVE_TYPE = "Nghỉ phép năm"

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		ensure_short_hours_code()
		cls.emp = test_employee()
		cls.company = frappe.db.get_value("Employee", cls.emp, "company")

	def lock_november(self):
		frappe.get_doc(
			{"doctype": "Monthly Attendance Sheet", "company": self.company, "month": "11", "year": 2099}
		).insert().submit()

	def mk_attendance(self, day, **kw):
		doc = frappe.get_doc(
			{
				"doctype": "Attendance",
				"employee": self.emp,
				"attendance_date": f"2099-11-{day:02d}",
				"company": self.company,
				**kw,
			}
		).insert()
		doc.submit()
		return doc

	def allocate_leave(self):
		frappe.get_doc(
			{
				"doctype": "Leave Allocation",
				"employee": self.emp,
				"leave_type": self.LEAVE_TYPE,
				"from_date": "2099-01-01",
				"to_date": "2099-12-31",
				"new_leaves_allocated": 12,
				"company": self.company,
			}
		).insert(ignore_permissions=True).submit()

	def leave_application(self, day):
		date = f"2099-11-{day:02d}"
		return frappe.get_doc(
			{
				"doctype": "Leave Application",
				"employee": self.emp,
				"leave_type": self.LEAVE_TYPE,
				"from_date": date,
				"to_date": date,
				"company": self.company,
				"status": "Approved",
			}
		).insert(ignore_permissions=True)

	def payroll_fields(self, name):
		return frappe.db.get_value(
			"Attendance",
			name,
			["status", "leave_type", "half_day_status", "docstatus", "custom_attendance_code"],
			as_dict=True,
		)

	def test_approving_leave_onto_a_day_in_a_locked_period_is_blocked(self):
		"""Kịch bản L11 của báo cáo rà soát: đơn nghỉ lùi ngày vào kỳ đã chốt."""
		self.allocate_leave()
		att = self.mk_attendance(5, status="Absent")
		leave = self.leave_application(5)
		self.lock_november()
		before = self.payroll_fields(att.name)

		with self.assertRaises(frappe.exceptions.ValidationError):
			leave.submit()

		self.assertEqual(self.payroll_fields(att.name), before, "ngày công trong kỳ đã chốt bị đổi")

	def test_cancelling_leave_inside_a_locked_period_is_blocked(self):
		self.allocate_leave()
		self.mk_attendance(6, status="Absent")
		leave = self.leave_application(6)
		leave.submit()
		att = frappe.db.get_value("Attendance", {"leave_application": leave.name}, "name")
		self.lock_november()
		before = self.payroll_fields(att)

		with self.assertRaises(frappe.exceptions.ValidationError):
			leave.cancel()

		self.assertEqual(self.payroll_fields(att), before, "huỷ đơn nghỉ đã huỷ luôn ngày công đã chốt")

	def test_leave_outside_the_locked_period_still_goes_through(self):
		"""Khoá tháng 11 không được chặn đơn nghỉ của tháng 12."""
		self.allocate_leave()
		self.lock_november()
		leave = frappe.get_doc(
			{
				"doctype": "Leave Application",
				"employee": self.emp,
				"leave_type": self.LEAVE_TYPE,
				"from_date": "2099-12-01",
				"to_date": "2099-12-01",
				"company": self.company,
				"status": "Approved",
			}
		).insert(ignore_permissions=True)
		leave.submit()
		self.assertEqual(leave.docstatus, 1)

	def test_attendance_request_onto_a_day_in_a_locked_period_is_blocked(self):
		att = self.mk_attendance(10, status="Absent")
		request = frappe.get_doc(
			{
				"doctype": "Attendance Request",
				"employee": self.emp,
				"company": self.company,
				"from_date": "2099-11-10",
				"to_date": "2099-11-10",
				"reason": "Work From Home",
			}
		).insert(ignore_permissions=True)
		self.lock_november()
		before = self.payroll_fields(att.name)

		with self.assertRaises(frappe.exceptions.ValidationError):
			request.submit()

		self.assertEqual(self.payroll_fields(att.name), before, "ngày công trong kỳ đã chốt bị đổi")

	def test_lunch_recompute_leaves_a_locked_period_alone(self):
		from hrms.vn_payroll.lunch import recompute_lunch_flags

		att = self.mk_attendance(11, custom_attendance_code="X")
		# cờ lệch với luật (ngày X chấm tay đáng ra = 1) — đúng thứ lượt tính lại sẽ "sửa"
		frappe.db.set_value("Attendance", att.name, "custom_lunch", 0, update_modified=False)
		self.lock_november()

		recompute_lunch_flags(11, 2099, self.company)

		self.assertEqual(
			frappe.db.get_value("Attendance", att.name, "custom_lunch"),
			0,
			"số buổi ăn trưa của kỳ đã chốt bị tính lại → lệch với bảng công đã ký",
		)

	def test_lunch_recompute_still_fixes_an_open_period(self):
		from hrms.vn_payroll.lunch import recompute_lunch_flags

		att = self.mk_attendance(12, custom_attendance_code="X")
		frappe.db.set_value("Attendance", att.name, "custom_lunch", 0, update_modified=False)

		recompute_lunch_flags(11, 2099, self.company)

		self.assertEqual(frappe.db.get_value("Attendance", att.name, "custom_lunch"), 1)

	def test_half_day_absent_job_leaves_a_locked_period_alone(self):
		"""Job hằng giờ ép "nửa còn lại = Absent" khi thiếu lượt chấm — trừ 0,5 ngày lương. Kỳ đã
		chốt thì con số đó đã nằm trên bảng ký, không được đổi sau lưng."""
		shift = "VN Lock Shift (test)"
		if not frappe.db.exists("Shift Type", shift):
			frappe.get_doc(
				{
					"doctype": "Shift Type",
					"__newname": shift,
					"start_time": "08:00:00",
					"end_time": "17:30:00",
					"enable_auto_attendance": 1,
				}
			).insert()
		frappe.get_doc(
			{
				"doctype": "Shift Assignment",
				"employee": self.emp,
				"company": self.company,
				"shift_type": shift,
				"start_date": "2099-11-01",
				"end_date": "2099-11-30",
			}
		).insert().submit()
		att = self.mk_attendance(13, status="Present")
		# trạng thái mà upstream để lại sau khi duyệt đơn nghỉ nửa ngày lên một ngày đang Vắng
		frappe.db.set_value(
			"Attendance",
			att.name,
			{"status": "Half Day", "half_day_status": "Present", "modify_half_day_status": 1},
		)
		self.lock_november()

		frappe.get_doc("Shift Type", shift).mark_absent_for_half_day_dates(self.emp)

		self.assertEqual(frappe.db.get_value("Attendance", att.name, "half_day_status"), "Present")
