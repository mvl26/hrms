# Copyright (c) 2026, Miyano Việt Nam.
"""Bước soát công: cờ bất thường, lưới soát, và cửa ghi `apply_correction` (+ khoá kỳ)."""

import frappe
from frappe.tests.utils import FrappeTestCase

from hrms.hr.attendance_review import (
	FLAG_ABSENT,
	FLAG_CHECKIN_ON_HOLIDAY,
	FLAG_NO_RECORD,
	FLAG_SHORT_HOURS,
	FLAG_SINGLE_PUNCH,
	anomaly_flags,
	apply_correction,
	get_review_grid,
)
from hrms.tests.isolation import PerTestRollback
from hrms.tests.vn_test_utils import ensure_short_hours_code, test_employee


class TestAnomalyFlags(FrappeTestCase):
	"""Hàm thuần — không chạm DB."""

	def test_a_normal_full_day_has_no_flag(self):
		self.assertEqual(anomaly_flags("X", punches=2, has_record=True, is_rest_day=False), [])

	def test_short_hours_day_is_flagged(self):
		self.assertEqual(
			anomaly_flags("1/2X", punches=2, has_record=True, is_rest_day=False), [FLAG_SHORT_HOURS]
		)

	def test_absent_day_is_flagged(self):
		self.assertEqual(anomaly_flags("V", punches=0, has_record=True, is_rest_day=False), [FLAG_ABSENT])

	def test_single_punch_is_flagged(self):
		self.assertEqual(
			anomaly_flags("X", punches=1, has_record=True, is_rest_day=False), [FLAG_SINGLE_PUNCH]
		)

	def test_a_working_day_with_no_record_is_flagged(self):
		self.assertEqual(anomaly_flags("", punches=0, has_record=False, is_rest_day=False), [FLAG_NO_RECORD])

	def test_a_rest_day_is_quiet_unless_somebody_punched(self):
		self.assertEqual(anomaly_flags("-", punches=0, has_record=False, is_rest_day=True), [])
		self.assertEqual(
			anomaly_flags("-", punches=2, has_record=False, is_rest_day=True), [FLAG_CHECKIN_ON_HOLIDAY]
		)

	def test_a_day_can_carry_more_than_one_flag(self):
		self.assertEqual(
			anomaly_flags("1/2X", punches=1, has_record=True, is_rest_day=False),
			[FLAG_SHORT_HOURS, FLAG_SINGLE_PUNCH],
		)


class TestReviewGrid(PerTestRollback, FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		ensure_short_hours_code()
		cls.emp = test_employee()
		cls.company = frappe.db.get_value("Employee", cls.emp, "company")

	def mk(self, day, **kw):
		return frappe.get_doc(
			{
				"doctype": "Attendance",
				"employee": self.emp,
				"attendance_date": f"2099-09-{day:02d}",
				"company": self.company,
				**kw,
			}
		).insert()

	def test_grid_rows_match_the_shared_derivation(self):
		from hrms.hr.report.monthly_attendance_report.monthly_attendance_report import get_sheet_rows

		self.mk(1, custom_attendance_code="X")
		filters = {"month": 9, "year": 2099, "company": self.company}
		grid = get_review_grid(filters)
		self.assertEqual(len(grid["rows"]), len(get_sheet_rows(filters)))
		self.assertIn("flag_labels", grid)

	def test_grid_flags_a_short_hours_day(self):
		att = self.mk(2, custom_attendance_code="1/2X")
		att.submit()
		grid = get_review_grid({"month": 9, "year": 2099, "company": self.company})
		self.assertIn(FLAG_SHORT_HOURS, grid["flags"][self.emp][2])

	def test_grid_flags_a_working_day_with_no_record(self):
		"""Ô trống trên ngày làm việc = thiếu bản ghi công, phải nổi cờ.

		Từng bị nuốt vì ô trống bị xếp chung nhóm "ngày nghỉ" — cờ NO_RECORD không bao giờ nổi."""
		self.mk(1, custom_attendance_code="X").submit()  # để tháng có ít nhất một ngày có bản ghi
		grid = get_review_grid({"month": 9, "year": 2099, "company": self.company})
		flags = grid["flags"].get(self.emp, {})
		self.assertTrue(
			any(FLAG_NO_RECORD in f for f in flags.values()),
			"ngày làm việc không có bản ghi phải mang cờ NO_RECORD",
		)

	def test_grid_does_not_flag_days_before_the_employee_joined(self):
		"""Ngày trước khi vào làm cũng cho ô trống — không được coi là thiếu bản ghi."""
		joined = frappe.db.get_value("Employee", self.emp, "date_of_joining")
		month = frappe.utils.getdate(joined).month
		year = frappe.utils.getdate(joined).year
		grid = get_review_grid({"month": month, "year": year, "company": self.company})
		flags = grid["flags"].get(self.emp, {})
		before = [d for d in flags if d < frappe.utils.getdate(joined).day]
		self.assertEqual(before, [], f"ngày trước khi vào làm bị gắn cờ: {before}")

	def test_grid_exposes_the_attendance_name_so_the_cell_knows_what_to_fix(self):
		att = self.mk(3, custom_attendance_code="X")
		att.submit()
		grid = get_review_grid({"month": 9, "year": 2099, "company": self.company})
		row = next(r for r in grid["rows"] if r["employee"] == self.emp)
		self.assertEqual(row["attendance_names"][3], att.name)


class TestApplyCorrection(PerTestRollback, FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		ensure_short_hours_code()
		cls.emp = test_employee()
		cls.company = frappe.db.get_value("Employee", cls.emp, "company")

	def mk(self, day, **kw):
		doc = frappe.get_doc(
			{
				"doctype": "Attendance",
				"employee": self.emp,
				"attendance_date": f"2099-10-{day:02d}",
				"company": self.company,
				**kw,
			}
		).insert()
		doc.submit()
		return doc

	def test_it_rewrites_the_payroll_fields_of_a_submitted_day(self):
		att = self.mk(1, status="Absent")
		apply_correction(att.name, "X", "quên chấm công, quản lý xác nhận")

		row = frappe.db.get_value(
			"Attendance", att.name, ["status", "custom_attendance_code", "custom_work_credit"], as_dict=True
		)
		self.assertEqual(row.status, "Present")
		self.assertEqual(row.custom_attendance_code, "X")
		self.assertEqual(row.custom_work_credit, 1.0)

	def test_a_half_day_correction_docks_exactly_half(self):
		att = self.mk(2, status="Present")
		apply_correction(att.name, "1/2X", "về sớm không phép")

		row = frappe.db.get_value(
			"Attendance", att.name, ["status", "leave_type", "half_day_status"], as_dict=True
		)
		self.assertEqual(row.status, "Half Day")
		self.assertIsNone(row.leave_type)
		self.assertEqual(row.half_day_status, "Absent")

	def test_a_leave_code_carries_its_leave_type(self):
		att = self.mk(3, status="Absent")
		apply_correction(att.name, "P", "có đơn nghỉ phép đã duyệt")
		row = frappe.db.get_value("Attendance", att.name, ["status", "leave_type"], as_dict=True)
		self.assertEqual(row.status, "On Leave")
		self.assertEqual(row.leave_type, "Nghỉ phép năm")

	def test_every_correction_leaves_a_trace(self):
		att = self.mk(4, status="Absent")
		apply_correction(att.name, "X", "bổ sung theo biên bản 12/10")

		log = frappe.get_all(
			"Attendance Correction Log",
			filters={"attendance": att.name},
			fields=["old_code", "new_code", "old_status", "new_status", "reason"],
		)
		self.assertEqual(len(log), 1)
		self.assertEqual(log[0].new_code, "X")
		self.assertEqual(log[0].old_status, "Absent")
		self.assertEqual(log[0].reason, "bổ sung theo biên bản 12/10")

	def test_a_correction_without_a_reason_is_refused(self):
		att = self.mk(5, status="Absent")
		for bad in (None, "", "   "):
			with self.assertRaises(frappe.exceptions.ValidationError):
				apply_correction(att.name, "X", bad)

	def test_an_unknown_code_is_refused(self):
		att = self.mk(6, status="Absent")
		with self.assertRaises(frappe.exceptions.ValidationError):
			apply_correction(att.name, "KHONG-CO", "lý do hợp lệ")

	def test_a_refused_correction_writes_nothing(self):
		att = self.mk(7, status="Absent")
		with self.assertRaises(frappe.exceptions.ValidationError):
			apply_correction(att.name, "X", "")
		self.assertEqual(frappe.db.get_value("Attendance", att.name, "status"), "Absent")
		self.assertEqual(frappe.db.count("Attendance Correction Log", {"attendance": att.name}), 0)


class TestApplyCorrectionLunchFlag(PerTestRollback, FrappeTestCase):
	"""Cờ ăn trưa phải theo kịp mã công mới (spec §5.5).

	`apply_correction` ghi bằng `frappe.db.set_value` nên KHÔNG chạy `before_validate` — mọi field
	cần cập nhật phải được liệt kê tường minh. Thiếu `custom_lunch` thì cờ kẹt giá trị cũ: đã gặp
	trên dữ liệu thật 7/2026 (một ngày `P` mang cờ 1 vì trước đó là `X` có checkin → trả thừa)."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		ensure_short_hours_code()
		cls.emp = test_employee()
		cls.company = frappe.db.get_value("Employee", cls.emp, "company")

	def mk(self, day, **kw):
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

	def checkin(self, day, hhmm):
		frappe.get_doc(
			{
				"doctype": "Employee Checkin",
				"employee": self.emp,
				"time": f"2099-11-{day:02d} {hhmm}:00",
			}
		).insert(ignore_permissions=True)

	def lunch(self, att):
		return frappe.db.get_value("Attendance", att.name, "custom_lunch")

	def test_correcting_a_work_day_to_leave_clears_the_lunch_flag(self):
		"""Đúng ca đang sai tiền trên dữ liệu thật: X (có ăn) → P thì phải hết ăn trưa."""
		self.checkin(1, "08:00")
		self.checkin(1, "17:30")
		att = self.mk(1, status="Present", custom_attendance_code="X")
		self.assertEqual(self.lunch(att), 1)

		apply_correction(att.name, "P", "có đơn nghỉ phép đã duyệt")
		self.assertEqual(self.lunch(att), 0)

	def test_correcting_absent_to_a_full_day_grants_lunch(self):
		"""Chiều ngược lại: vắng → X chấm tay (không checkin) thì được tính ăn."""
		att = self.mk(2, status="Absent")
		self.assertEqual(self.lunch(att), 0)

		apply_correction(att.name, "X", "quên chấm công, quản lý xác nhận")
		self.assertEqual(self.lunch(att), 1)

	def test_correcting_to_business_trip_gives_no_lunch(self):
		self.checkin(3, "08:00")
		self.checkin(3, "17:30")
		att = self.mk(3, status="Present", custom_attendance_code="X")
		self.assertEqual(self.lunch(att), 1)

		apply_correction(att.name, "CT", "đi công tác theo quyết định")
		self.assertEqual(self.lunch(att), 0)

	def test_a_manual_override_is_not_overwritten_by_a_correction(self):
		"""Người đã quyết thì soát công cũng không đè."""
		att = self.mk(4, status="Absent")
		frappe.db.set_value("Attendance", att.name, "custom_lunch_override", "Không")

		apply_correction(att.name, "X", "bổ sung theo biên bản")
		self.assertEqual(self.lunch(att), 0)


class TestCreateDayFromReview(PerTestRollback, FrappeTestCase):
	"""Ô "ngày làm việc không có bản ghi" phải xử lý được NGAY trên lưới soát công.

	Lưới gắn cờ `NO_RECORD` nhưng trước đây chỉ sửa được ô đã có bản ghi; gặp ô trống HR phải bỏ
	sang Mark Attendance — đường đó không bắt lý do và không để lại vết nào. `create_reviewed_day`
	là cùng một cửa: bắt lý do, tôn trọng khoá kỳ, ghi `Attendance Correction Log`."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		ensure_short_hours_code()
		cls.emp = test_employee()
		cls.company = frappe.db.get_value("Employee", cls.emp, "company")

	def setUp(self):
		from hrms.tests.work_calendar_fixture import MON_TO_FRI, set_company_weekdays

		set_company_weekdays(MON_TO_FRI)  # 2099-12-01 là thứ Ba, 2099-12-05 là thứ Bảy

	def day(self, date):
		return frappe.db.get_value(
			"Attendance",
			{"employee": self.emp, "attendance_date": date, "docstatus": ["<", 2]},
			["name", "docstatus", "status", "custom_attendance_code", "custom_work_credit"],
			as_dict=True,
		)

	def test_it_creates_a_submitted_day_with_the_chosen_code(self):
		from hrms.hr.attendance_review import create_reviewed_day

		create_reviewed_day(self.emp, "2099-12-01", "X", "quên chấm công, quản lý xác nhận")

		row = self.day("2099-12-01")
		self.assertEqual(row.docstatus, 1)
		self.assertEqual(row.status, "Present")
		self.assertEqual(row.custom_attendance_code, "X")
		self.assertEqual(row.custom_work_credit, 1.0)

	def test_the_new_day_leaves_a_trace(self):
		from hrms.hr.attendance_review import create_reviewed_day

		out = create_reviewed_day(self.emp, "2099-12-02", "V", "không đi làm, không báo")

		log = frappe.get_all(
			"Attendance Correction Log",
			filters={"attendance": out["attendance"]},
			fields=["old_code", "new_code", "old_status", "new_status", "reason"],
		)
		self.assertEqual(len(log), 1)
		self.assertFalse(log[0].old_code)
		self.assertFalse(log[0].old_status)
		self.assertEqual(log[0].new_code, "V")
		self.assertEqual(log[0].new_status, "Absent")
		self.assertEqual(log[0].reason, "không đi làm, không báo")

	def test_a_reason_is_required(self):
		from hrms.hr.attendance_review import create_reviewed_day

		for bad in (None, "", "   "):
			with self.assertRaises(frappe.exceptions.ValidationError):
				create_reviewed_day(self.emp, "2099-12-03", "X", bad)
		self.assertIsNone(self.day("2099-12-03"))

	def test_a_day_that_already_has_a_record_is_refused(self):
		"""Ngày đã có bản ghi thì phải đi đường SỬA (`apply_correction`), không tạo chồng lên."""
		from hrms.hr.attendance_review import create_reviewed_day

		create_reviewed_day(self.emp, "2099-12-04", "X", "bổ sung lần đầu")
		with self.assertRaises(frappe.exceptions.ValidationError):
			create_reviewed_day(self.emp, "2099-12-04", "V", "tạo chồng")
		self.assertEqual(self.day("2099-12-04").custom_attendance_code, "X")

	def test_a_rest_day_is_refused(self):
		"""Thứ Bảy không phải ngày làm việc: ô đó không mang cờ NO_RECORD, không có gì để bổ sung."""
		from hrms.hr.attendance_review import create_reviewed_day

		with self.assertRaises(frappe.exceptions.ValidationError):
			create_reviewed_day(self.emp, "2099-12-05", "X", "làm thêm thứ Bảy")
		self.assertIsNone(self.day("2099-12-05"))

	def test_a_locked_period_is_refused(self):
		from hrms.hr.attendance_review import create_reviewed_day

		frappe.get_doc(
			{"doctype": "Monthly Attendance Sheet", "company": self.company, "month": "12", "year": 2099}
		).insert().submit()
		with self.assertRaises(frappe.exceptions.ValidationError):
			create_reviewed_day(self.emp, "2099-12-07", "X", "bổ sung sau khi đã chốt")
		self.assertIsNone(self.day("2099-12-07"))

	def test_bulk_save_handles_new_days_and_edits_together(self):
		"""Lưới gom mọi ô chờ lưu vào MỘT lần bấm — có ô sửa, có ô tạo mới."""
		from hrms.hr.attendance_review import apply_corrections_bulk

		existing = frappe.get_doc(
			{
				"doctype": "Attendance",
				"employee": self.emp,
				"attendance_date": "2099-12-08",
				"company": self.company,
				"status": "Absent",
			}
		).insert()
		existing.submit()

		out = apply_corrections_bulk(
			[
				{"attendance": existing.name, "code": "X", "reason": "quên chấm công"},
				{"employee": self.emp, "date": "2099-12-09", "code": "X", "reason": "máy chấm hỏng"},
			]
		)

		self.assertEqual(out["applied"], 2)
		self.assertEqual(self.day("2099-12-08").custom_attendance_code, "X")
		self.assertEqual(self.day("2099-12-09").custom_attendance_code, "X")
