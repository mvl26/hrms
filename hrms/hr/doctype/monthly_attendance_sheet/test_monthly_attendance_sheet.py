# Copyright (c) 2026, Miyano Việt Nam.
import frappe
from frappe.tests.utils import FrappeTestCase

from erpnext.setup.doctype.employee.test_employee import make_employee

from hrms.tests.isolation import PerTestRollback
from hrms.tests.vn_test_utils import test_employee


class TestMonthlyAttendanceSheet(PerTestRollback, FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.company = frappe.db.get_value("Company", {}, "name")

	def _sheet(self, month="4", year=2097, department=None):
		return frappe.get_doc(
			{
				"doctype": "Monthly Attendance Sheet",
				"company": self.company,
				"department": department,
				"month": month,
				"year": year,
			}
		)

	def test_validate_derives_period_dates(self):
		d = self._sheet(month="4", year=2097)
		d.insert()
		self.assertEqual(str(d.from_date), "2097-04-01")
		self.assertEqual(str(d.to_date), "2097-04-30")  # April = 30 days

	def test_no_duplicate_sheet_per_unit_month(self):
		self._sheet(month="5", year=2097).insert()
		dup = self._sheet(month="5", year=2097)
		self.assertRaises(frappe.ValidationError, dup.insert)

	def test_different_month_is_allowed(self):
		self._sheet(month="6", year=2097).insert()
		self._sheet(month="7", year=2097).insert()  # different month -> no duplicate

	def _seed_attendance(self, emp, year, month, day, **codes):
		att = frappe.get_doc(
			{
				"doctype": "Attendance",
				"employee": emp,
				"company": self.company,
				"attendance_date": f"{year}-{month:02d}-{day:02d}",
				**codes,
			}
		)
		att.insert()
		att.submit()  # snapshot counts only submitted Attendance (matches payroll's docstatus==1)

	def test_populate_snapshots_attendance(self):
		emp = frappe.db.get_value("Employee", {"company": self.company, "status": "Active"}, "name")
		if not emp:
			self.skipTest("no employee in company")
		Y, M = 2097, 8
		self._seed_attendance(emp, Y, M, 4, custom_attendance_code="X")
		self._seed_attendance(emp, Y, M, 5, custom_attendance_code="P")
		self._seed_attendance(emp, Y, M, 6, custom_attendance_code="1/2P")

		sheet = self._sheet(month=str(M), year=Y)
		sheet.insert()
		n = sheet.populate_from_attendance()
		self.assertGreaterEqual(n, 1)

		row = next((r for r in sheet.employees if r.employee == emp), None)
		self.assertIsNotNone(row, "seeded employee missing from the sheet")
		self.assertEqual(row.d04, "X")
		self.assertEqual(row.d05, "P")
		self.assertEqual(row.d06, "1/2P")
		# Công = X 1.0 + 1/2P 0.5 = 1.5 ; Phép = P 1.0 + 1/2P 0.5 = 1.5
		self.assertEqual(row.work_days, 1.5)
		self.assertEqual(row.annual_leave, 1.5)

	def test_total_paid_days_counts_paid_leave_like_the_report(self):
		"""Cột "Tổng công" của bảng = SỐ NGÀY CÔNG TY TRẢ LƯƠNG, y hệt báo cáo chấm công tháng.

		Cột "Công đi làm" chỉ đếm phần ĐI LÀM nên nghỉ phép có lương không nằm trong đó — nhìn một
		mình nó thì tưởng công ty không trả ngày phép. Hai cột phải tách bạch và Tổng công = công đi
		làm + mọi nghỉ CÓ LƯƠNG do công ty trả."""
		emp = frappe.db.get_value("Employee", {"company": self.company, "status": "Active"}, "name")
		if not emp:
			self.skipTest("no employee in company")
		Y, M = 2096, 11
		for day, code in ((2, "X"), (3, "P"), (4, "KH"), (5, "NB"), (6, "T")):
			self._seed_attendance(emp, Y, M, day, custom_attendance_code=code)
		for day, code in ((9, "Ô"), (10, "TS"), (11, "K"), (12, "V")):  # BHXH trả / không ai trả
			self._seed_attendance(emp, Y, M, day, custom_attendance_code=code)

		sheet = self._sheet(month=str(M), year=Y)
		sheet.insert()
		sheet.populate_from_attendance()

		row = next((r for r in sheet.employees if r.employee == emp), None)
		self.assertIsNotNone(row, "seeded employee missing from the sheet")
		self.assertEqual(row.work_days, 1.0, "công đi làm: chỉ mỗi ngày X")
		self.assertEqual(row.total_paid_days, 5.0, "X + P + KH + NB + T đều do công ty trả")
		# nhóm không tính vào Tổng công vẫn phải hiện rõ ở cột riêng của nó
		self.assertEqual(row.sick_leave, 1.0)
		self.assertEqual(row.maternity_leave, 1.0)
		self.assertEqual(row.unpaid_leave, 1.0)
		self.assertEqual(row.absent, 1.0)

	def test_total_paid_days_matches_the_report_column(self):
		"""Cùng một kỳ, Tổng công của bảng phải bằng đúng cột Tổng công của báo cáo — không được
		có hai con số công khác nhau cho cùng một nhân viên."""
		from hrms.hr.report.monthly_attendance_report.monthly_attendance_report import execute as bcct

		emp = frappe.db.get_value("Employee", {"company": self.company, "status": "Active"}, "name")
		if not emp:
			self.skipTest("no employee in company")
		Y, M = 2096, 12
		for day, code in ((2, "X"), (3, "1/2P"), (4, "P"), (5, "Ô")):
			self._seed_attendance(emp, Y, M, day, custom_attendance_code=code)

		sheet = self._sheet(month=str(M), year=Y)
		sheet.insert()
		sheet.populate_from_attendance()
		row = next(r for r in sheet.employees if r.employee == emp)

		_cols, data, *_ = bcct(
			frappe._dict(month=str(M), year=Y, company=self.company, include_company_descendants=1)
		)
		report_row = next(r for r in data if r.get("employee") == emp)
		self.assertEqual(row.total_paid_days, report_row["tong_cong"])

	def test_total_paid_days_is_exactly_worked_plus_company_paid_leave(self):
		"""Tổng công phải CỘNG ĐƯỢC từ các cột bên cạnh, không phải một con số rơi từ trên trời:

		    Tổng công = Công đi làm + Phép + Việc riêng + Nghỉ bù + Tai nạn LĐ

		Ốm / thai sản (BHXH trả), không lương và vắng đứng ngoài. Người ký bảng phải tự kiểm được."""
		emp = frappe.db.get_value("Employee", {"company": self.company, "status": "Active"}, "name")
		if not emp:
			self.skipTest("no employee in company")
		Y, M = 2095, 3
		for day, code in (
			(1, "X"),
			(2, "P"),
			(3, "KH"),
			(4, "NB"),
			(5, "T"),
			(6, "Ô"),
			(7, "K"),
			(8, "1/2X"),
		):
			self._seed_attendance(emp, Y, M, day, custom_attendance_code=code)

		sheet = self._sheet(month=str(M), year=Y)
		sheet.insert()
		sheet.populate_from_attendance()
		row = next(r for r in sheet.employees if r.employee == emp)

		company_paid = ("work_days", "annual_leave", "personal_leave", "comp_off", "work_accident_leave")
		self.assertEqual(row.total_paid_days, sum((row.get(f) or 0) for f in company_paid))
		self.assertEqual(row.total_paid_days, 5.5)  # X 1 + P 1 + KH 1 + NB 1 + T 1 + nửa buổi 1/2X

	def test_populate_personal_leave_total(self):
		# code N (nghỉ việc riêng có lương) must land in the personal_leave totals column
		emp = frappe.db.get_value("Employee", {"company": self.company, "status": "Active"}, "name")
		if not emp:
			self.skipTest("no employee in company")
		Y, M = 2097, 2
		self._seed_attendance(emp, Y, M, 7, custom_attendance_code="KH")

		sheet = self._sheet(month=str(M), year=Y)
		sheet.insert()
		sheet.populate_from_attendance()

		row = next((r for r in sheet.employees if r.employee == emp), None)
		self.assertIsNotNone(row, "seeded employee missing from the sheet")
		self.assertEqual(row.d07, "KH")
		self.assertEqual(row.personal_leave, 1.0)  # full-day personal leave = 1.0

	def test_populate_all_leave_category_columns(self):
		# every leave/absence category maps to its own totals column — backfills the 5 buckets
		# (sick/maternity/work-accident/comp-off/unpaid) + absent that no other test exercised.
		emp = frappe.db.get_value("Employee", {"company": self.company, "status": "Active"}, "name")
		if not emp:
			self.skipTest("no active employee in company")
		Y, M = 2096, 3
		for day, code in ((3, "Ô"), (4, "TS"), (5, "T"), (6, "NB"), (7, "K"), (8, "V")):
			self._seed_attendance(emp, Y, M, day, custom_attendance_code=code)

		sheet = self._sheet(month=str(M), year=Y)
		sheet.insert()
		sheet.populate_from_attendance()

		row = next((r for r in sheet.employees if r.employee == emp), None)
		self.assertIsNotNone(row, "seeded employee missing from the sheet")
		self.assertEqual(row.sick_leave, 1.0)  # Ô
		self.assertEqual(row.maternity_leave, 1.0)  # TS
		self.assertEqual(row.work_accident_leave, 1.0)  # T
		self.assertEqual(row.comp_off, 1.0)  # NB
		self.assertEqual(row.unpaid_leave, 1.0)  # K
		self.assertEqual(row.absent, 1.0)  # V

	def test_row_totals_foot_to_attended_days(self):
		# a fully-resolved attended day contributes exactly 1.0 across the 9 buckets, so the row
		# sums to the number of attended days — nothing evaporates or is double counted.
		emp = frappe.db.get_value("Employee", {"company": self.company, "status": "Active"}, "name")
		if not emp:
			self.skipTest("no active employee in company")
		Y, M = 2096, 5
		for day, code in ((1, "X"), (2, "P"), (3, "1/2X"), (4, "1/2P")):
			self._seed_attendance(emp, Y, M, day, custom_attendance_code=code)

		sheet = self._sheet(month=str(M), year=Y)
		sheet.insert()
		sheet.populate_from_attendance()

		row = next((r for r in sheet.employees if r.employee == emp), None)
		self.assertIsNotNone(row, "seeded employee missing from the sheet")
		fields = (
			"work_days",
			"annual_leave",
			"personal_leave",
			"sick_leave",
			"maternity_leave",
			"work_accident_leave",
			"comp_off",
			"unpaid_leave",
			"absent",
		)
		self.assertEqual(sum((row.get(f) or 0) for f in fields), 4.0)  # 4 attended days

	def test_public_holiday_populates_nghi_le_column(self):
		# a paid public holiday must land in the Detail's public_holiday (Nghỉ lễ) column
		Y, M = 2096, 9
		hl = frappe.get_doc(
			{
				"doctype": "Holiday List",
				"holiday_list_name": "MAS NL Test 2096-09",
				"from_date": f"{Y}-{M:02d}-01",
				"to_date": f"{Y}-{M:02d}-30",
				"holidays": [{"holiday_date": f"{Y}-{M:02d}-05", "description": "Lễ", "weekly_off": 0}],
			}
		).insert()
		emp = make_employee("mas_nghi_le@codes.com", company=self.company)
		frappe.db.set_value("Employee", emp, {"holiday_list": hl.name, "relieving_date": None})

		sheet = self._sheet(month=str(M), year=Y)
		sheet.insert()
		sheet.populate_from_attendance()

		row = next((r for r in sheet.employees if r.employee == emp), None)
		self.assertIsNotNone(row, "seeded employee missing from the sheet")
		self.assertEqual(row.public_holiday, 1.0)

	def test_populate_blocked_after_submit(self):
		sheet = self._sheet(month="9", year=2097)
		sheet.insert()
		sheet.submit()
		self.assertRaises(frappe.ValidationError, sheet.populate_from_attendance)

	def test_sheet_is_payroll_neutral_never_writes_attendance(self):
		# creating + populating + submitting the sheet must not create or modify ANY Attendance
		emp = frappe.db.get_value("Employee", {"company": self.company, "status": "Active"}, "name")
		if not emp:
			self.skipTest("no employee in company")
		Y, M = 2097, 10
		self._seed_attendance(emp, Y, M, 3, custom_attendance_code="P")
		att = frappe.db.get_value(
			"Attendance",
			{"employee": emp, "attendance_date": f"{Y}-{M:02d}-03"},
			["name", "status", "leave_type", "half_day_status"],
			as_dict=True,
		)
		before_count = frappe.db.count("Attendance")

		sheet = self._sheet(month=str(M), year=Y)
		sheet.insert()
		sheet.populate_from_attendance()
		sheet.save()
		sheet.submit()

		self.assertEqual(frappe.db.count("Attendance"), before_count)  # no new Attendance rows
		after = frappe.db.get_value(
			"Attendance", att.name, ["status", "leave_type", "half_day_status"], as_dict=True
		)
		# payroll-relevant fields on the existing Attendance are byte-identical
		self.assertEqual(after.status, att.status)
		self.assertEqual(after.leave_type, att.leave_type)
		self.assertEqual(after.half_day_status, att.half_day_status)

	def test_submit_and_cancel_lifecycle(self):
		sheet = self._sheet(month="11", year=2097)
		sheet.insert()
		sheet.submit()
		self.assertEqual(sheet.docstatus, 1)
		sheet.cancel()
		self.assertEqual(sheet.docstatus, 2)

	def test_print_format_renders(self):
		emp = frappe.db.get_value("Employee", {"company": self.company, "status": "Active"}, "name")
		if not emp:
			self.skipTest("no employee in company")
		Y, M = 2097, 12
		self._seed_attendance(emp, Y, M, 2, custom_attendance_code="X")
		sheet = self._sheet(month=str(M), year=Y)
		sheet.insert()
		sheet.populate_from_attendance()
		sheet.save()

		html = frappe.get_print(
			"Monthly Attendance Sheet", sheet.name, print_format="Monthly Attendance Sheet"
		)
		self.assertIn("BẢNG CHẤM CÔNG THÁNG", html)
		self.assertIn("NGƯỜI CHẤM CÔNG", html)  # sign box 1
		self.assertIn("PHÒNG NHÂN SỰ", html)  # sign box 2
		self.assertIn("Chú thích", html)  # symbol legend
		self.assertIn("Tổng<br>công", html)  # cột chủ đạo: số ngày công ty trả lương
		self.assertIn("Công<br>đi làm", html)  # tách bạch với phần đi làm thực tế


class TestSubmitWarnsAboutUnreviewedDays(PerTestRollback, FrappeTestCase):
	"""Chốt công khoá kỳ, nên trước khi khoá phải nói rõ còn bao nhiêu ô đáng ngờ."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.emp = test_employee()
		cls.company = frappe.db.get_value("Employee", cls.emp, "company")

	def sheet(self, month=8, year=2099):
		doc = frappe.get_doc(
			{
				"doctype": "Monthly Attendance Sheet",
				"company": self.company,
				"month": str(month),
				"year": year,
			}
		).insert()
		doc.populate_from_attendance()
		doc.save()
		return doc

	def test_it_warns_when_days_still_carry_flags(self):
		frappe.get_doc(
			{
				"doctype": "Attendance",
				"employee": self.emp,
				"attendance_date": "2099-08-03",
				"company": self.company,
				"status": "Absent",
			}
		).insert().submit()

		doc = self.sheet()
		frappe.local.message_log = []
		doc.submit()

		messages = " ".join(str(m) for m in frappe.message_log)
		self.assertIn("chưa xử lý", messages)


class TestFlowFromReportToPayroll(PerTestRollback, FrappeTestCase):
	"""Luồng nối: báo cáo -> soát -> CHỐT CÔNG -> LƯƠNG. Test phần server của hai chặng cuối."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.emp = test_employee()
		cls.company = frappe.db.get_value("Employee", cls.emp, "company")

	def test_get_or_create_sheet_opens_the_existing_one_instead_of_duplicating(self):
		from hrms.hr.doctype.monthly_attendance_sheet.monthly_attendance_sheet import get_or_create_sheet

		first = get_or_create_sheet("8", 2099, self.company)
		second = get_or_create_sheet("8", 2099, self.company)
		self.assertEqual(first, second, "bấm Chốt công hai lần không được đẻ ra hai bảng")

	def test_get_or_create_sheet_fills_the_rows_right_away(self):
		from hrms.hr.doctype.monthly_attendance_sheet.monthly_attendance_sheet import get_or_create_sheet

		name = get_or_create_sheet("8", 2099, self.company)
		doc = frappe.get_doc("Monthly Attendance Sheet", name)
		self.assertTrue(doc.employees, "bảng mở ra phải có sẵn dữ liệu, không bắt bấm Lấy dữ liệu")

	def test_payroll_is_refused_before_the_sheet_is_closed(self):
		from hrms.hr.doctype.monthly_attendance_sheet.monthly_attendance_sheet import get_or_create_sheet

		doc = frappe.get_doc("Monthly Attendance Sheet", get_or_create_sheet("8", 2099, self.company))
		with self.assertRaises(frappe.exceptions.ValidationError):
			doc.create_salary_slips()

	def test_closing_then_running_payroll_creates_slips_for_the_sheet_employees(self):
		from hrms.hr.doctype.monthly_attendance_sheet.monthly_attendance_sheet import get_or_create_sheet

		doc = frappe.get_doc("Monthly Attendance Sheet", get_or_create_sheet("8", 2099, self.company))
		doc.submit()

		result = doc.create_salary_slips()
		self.assertEqual(
			len(result["created"]) + len(result["failed"]),
			len(doc.employees),
			"mỗi nhân viên trong bảng phải được xử lý đúng một lần",
		)

	def test_running_payroll_twice_refreshes_drafts_instead_of_duplicating(self):
		from hrms.hr.doctype.monthly_attendance_sheet.monthly_attendance_sheet import get_or_create_sheet

		doc = frappe.get_doc("Monthly Attendance Sheet", get_or_create_sheet("8", 2099, self.company))
		doc.submit()
		first = doc.create_salary_slips()
		if not first["created"]:
			self.skipTest("site không lập được phiếu lương cho kỳ này (thiếu cấu trúc lương)")

		second = doc.create_salary_slips()
		self.assertEqual(second["created"], [], "lần hai không được tạo thêm phiếu")
		self.assertEqual(
			len(second["refreshed"]), len(first["created"]), "phiếu nháp phải được lấy lại số công"
		)
