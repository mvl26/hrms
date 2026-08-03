# Copyright (c) 2026, Miyano Việt Nam.
"""Unit tests for the VN attendance-code <-> native-status bridge (Attendance.before_validate).
Codes are exercised in isolation (before_validate, no insert) so native validation such as
check_leave_record does not mask the bridge's own output."""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import getdate

from hrms.tests.isolation import PerTestRollback
from hrms.tests.vn_test_utils import ensure_short_hours_code, test_employee


class TestAttendanceCodeBridge(PerTestRollback, FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.emp = test_employee()

	def _bridge(self, **codes):
		doc = frappe.get_doc(
			{"doctype": "Attendance", "employee": self.emp, "attendance_date": getdate(), **codes}
		)
		doc.before_validate()
		return doc

	def test_forward_full_workday(self):
		d = self._bridge(custom_attendance_code="X")
		self.assertEqual(d.status, "Present")
		self.assertIn(d.leave_type, (None, ""))
		self.assertEqual(d.custom_work_credit, 1.0)

	def test_forward_full_annual_leave(self):
		d = self._bridge(custom_attendance_code="P")
		self.assertEqual(d.status, "On Leave")
		self.assertEqual(d.leave_type, "Nghỉ phép năm")
		self.assertEqual(d.custom_work_credit, 1.0)  # nghỉ phép năm: công ty trả đủ ngày

	def test_forward_full_unpaid_leave(self):
		d = self._bridge(custom_attendance_code="K")
		self.assertEqual(d.status, "On Leave")
		self.assertEqual(d.leave_type, "Nghỉ không lương")
		self.assertEqual(d.custom_work_credit, 0)

	def test_forward_half_work_half_leave(self):
		# sáng=X + chiều=P -> Half Day, half_day_status Present, leave_type phép năm, công 1.0
		# (nửa đi làm + nửa phép có lương đều do công ty trả)
		d = self._bridge(custom_morning_code="X", custom_afternoon_code="P")
		self.assertEqual(d.status, "Half Day")
		self.assertEqual(d.leave_type, "Nghỉ phép năm")
		self.assertEqual(d.half_day_status, "Present")
		self.assertEqual(d.custom_work_credit, 1.0)

	def test_forward_single_half_day_worked_paid(self):
		# 1/2X = đi làm thiếu giờ hưởng lương: Half Day, worked half present, no leave, công 0.5
		d = self._bridge(custom_attendance_code="1/2X")
		self.assertEqual(d.status, "Half Day")
		self.assertEqual(d.half_day_status, "Present")
		self.assertIn(d.leave_type, (None, ""))
		self.assertEqual(d.custom_work_credit, 0.5)

	def test_forward_single_half_day_annual_leave(self):
		# 1/2P = nửa làm + nửa phép năm: Half Day, worked half present, công = 1.0 (cả hai nửa đều được trả)
		d = self._bridge(custom_attendance_code="1/2P")
		self.assertEqual(d.status, "Half Day")
		self.assertEqual(d.half_day_status, "Present")
		self.assertEqual(d.leave_type, "Nghỉ phép năm")
		self.assertEqual(d.custom_work_credit, 1.0)

	def test_forward_single_half_day_unpaid(self):
		# 1/2K = nửa ngày không lương: Half Day, worked half present, unpaid-leave half, công 0.5
		d = self._bridge(custom_attendance_code="1/2K")
		self.assertEqual(d.status, "Half Day")
		self.assertEqual(d.half_day_status, "Present")
		self.assertEqual(d.leave_type, "Nghỉ không lương")
		self.assertEqual(d.custom_work_credit, 0.5)

	def test_forward_work_accident_leave(self):
		d = self._bridge(custom_attendance_code="T")
		self.assertEqual(d.status, "On Leave")
		self.assertEqual(d.leave_type, "Nghỉ tai nạn lao động")
		self.assertEqual(d.custom_work_credit, 1.0)  # Đ.38.3 ATVSLĐ: công ty trả đủ lương

	def test_forward_child_sick_leave(self):
		# Cô = nghỉ chăm con ốm -> On Leave; BHXH chi trả nên công doanh nghiệp = 0
		d = self._bridge(custom_attendance_code="Cô")
		self.assertEqual(d.status, "On Leave")
		self.assertEqual(d.leave_type, "Nghỉ chăm con ốm")
		self.assertEqual(d.custom_work_credit, 0)

	def test_forward_maternity_leave(self):
		# TS = nghỉ thai sản -> On Leave; BHXH chi trả nên công doanh nghiệp = 0
		d = self._bridge(custom_attendance_code="TS")
		self.assertEqual(d.status, "On Leave")
		self.assertEqual(d.leave_type, "Nghỉ thai sản")
		self.assertEqual(d.custom_work_credit, 0)

	def test_forward_comp_off_leave(self):
		# NB = nghỉ bù -> On Leave; công ty trả (nghỉ bù cho ngày đã làm) nên công = 1.0
		d = self._bridge(custom_attendance_code="NB")
		self.assertEqual(d.status, "On Leave")
		self.assertEqual(d.leave_type, "Nghỉ bù")
		self.assertEqual(d.custom_work_credit, 1.0)

	def test_forward_unexplained_absence(self):
		# V = vắng không lý do -> native Absent, no leave, không công
		d = self._bridge(custom_attendance_code="V")
		self.assertEqual(d.status, "Absent")
		self.assertIn(d.leave_type, (None, ""))
		self.assertEqual(d.custom_work_credit, 0)

	def test_forward_non_half_day_clears_stale_half_day_status(self):
		# auto-attendance may pre-set half_day_status="Absent" (threshold=Half Day) before the
		# classifier/bridge reclassify the day; a code resolving to a non-Half-Day status must clear
		# it, otherwise a Present record carries a stale, contradictory half_day_status.
		present = self._bridge(custom_attendance_code="X", half_day_status="Absent")
		self.assertEqual(present.status, "Present")
		self.assertIsNone(present.half_day_status)
		on_leave = self._bridge(custom_attendance_code="P", half_day_status="Absent")
		self.assertEqual(on_leave.status, "On Leave")
		self.assertIsNone(on_leave.half_day_status)

	def test_reverse_derives_absent_code(self):
		# an auto-attendance Absent record (checkin thiếu giờ / vắng) -> display code V
		d = self._bridge(status="Absent")
		self.assertEqual(d.custom_attendance_code, "V")
		self.assertEqual(d.custom_work_credit, 0)

	def test_reverse_derives_half_day_leave_code(self):
		# native half-day annual leave (no code) -> derive display code 1/2P; công 1.0 (cả hai nửa được trả)
		d = self._bridge(status="Half Day", leave_type="Nghỉ phép năm")
		self.assertEqual(d.custom_attendance_code, "1/2P")
		self.assertEqual(d.custom_work_credit, 1.0)

	def test_reverse_derives_code_from_native_status(self):
		# a record with a native status but no code (auto-attendance / leave) -> derive display code
		d = self._bridge(status="Present")
		self.assertEqual(d.custom_attendance_code, "X")
		self.assertEqual(d.custom_work_credit, 1.0)

	def test_reverse_derives_leave_code(self):
		d = self._bridge(status="On Leave", leave_type="Nghỉ ốm")
		self.assertEqual(d.custom_attendance_code, "Ô")
		self.assertEqual(d.custom_work_credit, 0)

	def test_reverse_pick_is_deterministic_for_shared_status(self):
		# nhiều mã cùng maps_to_status → reverse chọn mã chính (X cho Present, CT cho Work From Home)
		# thay vì phụ thuộc thứ tự DB. Đảm bảo an toàn khi W (làm nhà) cùng "Work From Home" với CT.
		from hrms.hr.doctype.attendance.attendance import _pick_reverse_code

		self.assertEqual(_pick_reverse_code("Present", ["X"]), "X")
		self.assertEqual(_pick_reverse_code("Present", ["CV", "X"]), "X")
		self.assertEqual(_pick_reverse_code("Work From Home", ["CT", "W"]), "CT")
		self.assertEqual(_pick_reverse_code("Work From Home", ["W", "CT"]), "CT")
		self.assertEqual(_pick_reverse_code("Absent", ["V"]), "V")
		self.assertIsNone(_pick_reverse_code("Present", []))

	def test_leave_backed_half_day_ignores_stale_work_code(self):
		# nghỉ phép NỬA NGÀY (có leave_application) còn sót mã X từ lần chấm Present → KHÔNG được lật về
		# Present; phải quy về 1/2P (nghỉ phép nửa ngày), công 0.5.
		d = self._bridge(
			status="Half Day",
			leave_type="Nghỉ phép năm",
			leave_application="HR-LAP-TEST",
			custom_attendance_code="X",
		)
		self.assertEqual(d.status, "Half Day")
		self.assertEqual(d.custom_attendance_code, "1/2P")
		self.assertEqual(d.custom_work_credit, 1.0)

	def test_leave_backed_full_day_ignores_stale_work_code(self):
		# nghỉ phép CẢ NGÀY còn sót mã X → quy về P (nghỉ phép năm), công 0.
		d = self._bridge(
			status="On Leave",
			leave_type="Nghỉ phép năm",
			leave_application="HR-LAP-TEST",
			custom_attendance_code="X",
		)
		self.assertEqual(d.status, "On Leave")
		self.assertEqual(d.custom_attendance_code, "P")
		self.assertEqual(d.custom_work_credit, 1.0)

	def test_leave_half_day_split_preserved(self):
		# tách đúng buổi (morning là mã nghỉ P, afternoon X) trên ngày có đơn nghỉ → GIỮ nguyên, không xoá.
		d = self._bridge(
			status="Half Day",
			leave_type="Nghỉ phép năm",
			leave_application="HR-LAP-TEST",
			custom_morning_code="P",
			custom_afternoon_code="X",
		)
		self.assertEqual(d.status, "Half Day")
		self.assertEqual(d.custom_morning_code, "P")
		self.assertEqual(d.custom_afternoon_code, "X")
		self.assertEqual(d.custom_work_credit, 1.0)

	def test_forward_personal_leave(self):
		# KH = nghỉ kết hôn -> On Leave; công ty trả nguyên lương nên công = 1.0
		d = self._bridge(custom_attendance_code="KH")
		self.assertEqual(d.status, "On Leave")
		self.assertEqual(d.leave_type, "Nghỉ kết hôn")
		self.assertEqual(d.custom_work_credit, 1.0)

	def test_reverse_personal_leave(self):
		# native On-Leave record of that leave type (no code) -> derive display code KH
		d = self._bridge(status="On Leave", leave_type="Nghỉ kết hôn")
		self.assertEqual(d.custom_attendance_code, "KH")
		self.assertEqual(d.custom_work_credit, 1.0)


class TestHalfDayLeaveCodeFullValidation(PerTestRollback, FrappeTestCase):
	"""Half-day *leave* codes (1/2P, 1/2K, worked+leave splits) must survive FULL validation.

	The bridge sets half_day_status="Present" (worked half present, other half = leave_type).
	But check_leave_record runs later in validate() and, finding no matching Leave Application
	(mã công entry never creates one), used to force half_day_status="Absent" — which under
	payroll_based_on="Attendance" over-deducts the paid half (1/2P) and double-deducts the
	unpaid half (1/2K). These tests insert the record so check_leave_record actually runs."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.emp = frappe.get_all("Employee", filters={"status": "Active"}, pluck="name", limit=1)[0]
		# a far-future date guarantees no duplicate attendance and no approved Leave Application,
		# so check_leave_record takes its "no leave record found" branch — the F-A path.
		cls.date = getdate("2099-06-15")

	def _insert(self, **codes):
		doc = frappe.get_doc(
			{"doctype": "Attendance", "employee": self.emp, "attendance_date": self.date, **codes}
		)
		doc.insert()
		doc.submit()  # the real mã-công flow submits; check_leave_record runs on submit too
		return doc

	def test_half_day_annual_leave_code_stays_present(self):
		# 1/2P: paid half-day leave. Worked half is present -> must NOT be marked Absent.
		d = self._insert(custom_attendance_code="1/2P")
		self.assertEqual(d.status, "Half Day")
		self.assertEqual(d.leave_type, "Nghỉ phép năm")
		self.assertEqual(d.half_day_status, "Present")

	def test_half_day_unpaid_leave_code_stays_present(self):
		# 1/2K: unpaid half-day leave. half_day_status Absent would double-count with the LWP leave_type.
		d = self._insert(custom_attendance_code="1/2K")
		self.assertEqual(d.status, "Half Day")
		self.assertEqual(d.leave_type, "Nghỉ không lương")
		self.assertEqual(d.half_day_status, "Present")

	def test_worked_plus_leave_split_stays_present(self):
		# sáng X + chiều P: worked morning + annual-leave afternoon.
		d = self._insert(custom_morning_code="X", custom_afternoon_code="P")
		self.assertEqual(d.status, "Half Day")
		self.assertEqual(d.leave_type, "Nghỉ phép năm")
		self.assertEqual(d.half_day_status, "Present")

	def test_plain_half_day_code_without_leave_still_absent(self):
		# NN: worked half + unexcused (no leave_type) half -> must stay Absent (docks 0.5, matches native).
		# Guards that the fix keys on leave_type and does not overpay NN.
		d = self._insert(custom_attendance_code="1/2X")
		self.assertEqual(d.status, "Half Day")
		self.assertIn(d.leave_type, (None, ""))
		self.assertEqual(d.half_day_status, "Absent")


class TestWorkCreditIsPaidCong(PerTestRollback, FrappeTestCase):
	"""Field "Công" trên ngày công = số công DOANH NGHIỆP TRẢ cho ngày đó.

	Trước đây nó mang `work_fraction` — công ĐI LÀM thực tế — nên nghỉ phép năm cả ngày hiện
	**Công = 0** dù công ty trả đủ lương ngày đó. Cùng một số 0 gộp ba nhóm khác hẳn nhau: nghỉ có
	lương công ty trả, nghỉ BHXH chi trả, và không ai trả. Nhìn form không phân biệt được.

	Nay khớp đúng cột "Tổng công" của bảng công: nhãn nói gì thì số phải là cái đó.
	"""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		ensure_short_hours_code()
		cls.emp = frappe.db.get_value("Employee", {"status": "Active"}, "name")

	def credit(self, code):
		doc = frappe.get_doc(
			{
				"doctype": "Attendance",
				"employee": self.emp,
				"attendance_date": "2099-04-06",
				"custom_attendance_code": code,
			}
		)
		doc.before_validate()
		return doc.custom_work_credit

	def test_company_paid_leave_counts_a_full_cong(self):
		for code in ("P", "KH", "R1", "R2", "NB", "T"):
			self.assertEqual(self.credit(code), 1.0, f"{code}: công ty trả đủ ngày này")

	def test_working_days_count_a_full_cong(self):
		for code in ("X", "CT", "W"):
			self.assertEqual(self.credit(code), 1.0, f"{code}: ngày đi làm")

	def test_leave_paid_by_social_insurance_counts_nothing(self):
		"""Ốm / chăm con ốm / thai sản do BHXH chi trả — doanh nghiệp không trả công ngày đó."""
		for code in ("Ô", "Cô", "TS"):
			self.assertEqual(self.credit(code), 0.0, f"{code}: BHXH trả, không phải công ty")

	def test_unpaid_and_absent_count_nothing(self):
		for code in ("K", "V"):
			self.assertEqual(self.credit(code), 0.0)

	def test_half_days_split_correctly(self):
		self.assertEqual(self.credit("1/2P"), 1.0, "nửa làm + nửa phép có lương = trả đủ ngày")
		self.assertEqual(self.credit("1/2K"), 0.5, "nửa làm + nửa không lương")
		self.assertEqual(self.credit("1/2X"), 0.5, "nửa làm + nửa thiếu giờ không phép")

	def test_it_matches_the_sheet_total_for_the_same_day(self):
		"""Số trên form và cột Tổng công của bảng công phải là một — hai nguồn lệch nhau là bẫy."""
		from hrms.hr.report.monthly_attendance_report.monthly_attendance_report import get_sheet_rows

		frappe.get_doc(
			{
				"doctype": "Attendance",
				"employee": self.emp,
				"attendance_date": "2099-04-06",
				"custom_attendance_code": "P",
			}
		).insert().submit()

		row = next(r for r in get_sheet_rows({"month": 4, "year": 2099}) if r["employee"] == self.emp)
		self.assertEqual(row["totals"].get("Tổng công", 0), self.credit("P"))
