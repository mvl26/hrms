# Copyright (c) 2026, Miyano Việt Nam.
"""Miyano — số buổi ăn trưa ghi nhận per-Attendance (nguồn duy nhất).

Cờ `custom_lunch` tính từ checkin (đúng luật cũ), report/Bảng Công Tháng/phiếu lương đều đếm từ cờ.
Chạy qua harness rollback. Test cờ bằng thuộc tính in-memory (KHÔNG insert Custom Field — bẫy DDL).
"""

import json
import os
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from hrms.tests.isolation import PerTestRollback
from hrms.tests.vn_test_utils import test_employee

_CF = os.path.join(frappe.get_app_path("hrms"), "fixtures", "custom_field.json")


def _custom_fields():
	with open(_CF, encoding="utf-8") as f:
		return {c["name"]: c for c in json.load(f)}


class TestLunchFlagFixture(PerTestRollback, FrappeTestCase):
	"""L1 — field cờ ăn trưa trên Attendance."""

	def test_custom_lunch_field_defined(self):
		cf = _custom_fields().get("Attendance-custom_lunch")
		self.assertIsNotNone(cf, "thiếu Custom Field Attendance-custom_lunch")
		self.assertEqual(cf["dt"], "Attendance")
		self.assertEqual(cf["fieldtype"], "Check")

	def test_custom_lunch_in_hooks_filter(self):
		import hrms.hooks as hooks

		names = set()
		for entry in hooks.fixtures:
			if isinstance(entry, dict) and entry.get("dt") == "Custom Field":
				nf = (entry.get("filters") or {}).get("name")
				if isinstance(nf, list | tuple) and nf and nf[0] == "in":
					names |= set(nf[1])
		self.assertIn("Attendance-custom_lunch", names)


class TestLunchRule(PerTestRollback, FrappeTestCase):
	"""L2 — luật per-ngày ``is_lunch_day`` (thuần, không DB)."""

	def _dt(self, *hhmm):
		from frappe.utils import get_datetime

		return [get_datetime(f"2098-12-01 {h}") for h in hhmm]

	def test_present_covering_window_is_lunch(self):
		from hrms.vn_payroll.lunch import is_lunch_day

		# vào 08:00 (<12:00), ra 17:30 (≥13:30), ca None → mặc định 12:00-13:30
		self.assertTrue(is_lunch_day("Present", None, self._dt("08:00:00", "17:30:00")))

	def test_half_day_covering_is_lunch(self):
		from hrms.vn_payroll.lunch import is_lunch_day

		self.assertTrue(is_lunch_day("Half Day", None, self._dt("08:00:00", "17:30:00")))

	def test_not_covering_is_not_lunch(self):
		from hrms.vn_payroll.lunch import is_lunch_day

		# chỉ chấm chiều (vào 14:00) → không phủ giờ trưa
		self.assertFalse(is_lunch_day("Present", None, self._dt("14:00:00", "17:30:00")))

	def test_leave_status_is_not_lunch(self):
		from hrms.vn_payroll.lunch import is_lunch_day

		self.assertFalse(is_lunch_day("On Leave", None, self._dt("08:00:00", "17:30:00")))

	def test_no_checkin_is_not_lunch(self):
		from hrms.vn_payroll.lunch import is_lunch_day

		self.assertFalse(is_lunch_day("Present", None, []))


class TestLunchFlagForAttendance(PerTestRollback, FrappeTestCase):
	"""L2 — ``lunch_flag_for_attendance`` đọc checkin thật của ngày rồi áp luật."""

	def setUp(self):
		self.emp = test_employee()

	def _checkin(self, dt):
		frappe.get_doc({"doctype": "Employee Checkin", "employee": self.emp, "time": dt}).insert(
			ignore_permissions=True
		)

	def test_covering_checkins_true(self):
		from hrms.vn_payroll.lunch import lunch_flag_for_attendance

		self._checkin("2098-12-02 08:00:00")
		self._checkin("2098-12-02 17:30:00")
		self.assertTrue(lunch_flag_for_attendance(self.emp, "2098-12-02", "Present", None, "X"))

	def test_no_checkins_now_counts_for_a_full_work_day(self):
		"""ĐẢO quyết định §2 của spec cũ (2026-08-27).

		Bản 2026-07-25 chốt "không checkin phủ giờ trưa → không tính ăn". Vận hành cho thấy luật đó
		phạt nhầm chấm công tạo tay và ngày sửa qua soát công — đều không có checkin nhưng HR đã
		xác nhận là ngày công đủ. Nay ngày công đủ không đủ dấu chấm vẫn được tính ăn."""
		from hrms.vn_payroll.lunch import lunch_flag_for_attendance

		self.assertTrue(lunch_flag_for_attendance(self.emp, "2098-12-03", "Present", None, "X"))

	def test_a_day_without_an_attendance_code_earns_no_lunch(self):
		"""Không mã thì không ăn trưa — hệ quả cố ý của danh sách CHO PHÉP (2026-09-11).

		Thực tế không bao giờ xảy ra: cầu nối mã công tự gán `X`/`1/2X` khi HR bỏ trống (đã soát
		dữ liệu thật: 0 ngày công nào thiếu mã). Giữ test này để nếu sau có đường ghi nào lách được
		cầu nối thì hỏng về phía AN TOÀN chứ không phát nhầm suất ăn."""
		from hrms.vn_payroll.lunch import lunch_flag_for_attendance

		self._checkin("2098-12-08 08:00:00")
		self._checkin("2098-12-08 17:30:00")
		self.assertFalse(lunch_flag_for_attendance(self.emp, "2098-12-08", "Present", None, None))

	def test_no_checkins_half_day_still_does_not_count(self):
		"""Nửa ngày thì giữ nguyên: không có dấu thì không chứng minh được là ở lại qua trưa."""
		from hrms.vn_payroll.lunch import lunch_flag_for_attendance

		self.assertFalse(lunch_flag_for_attendance(self.emp, "2098-12-03", "Half Day", None))

	def test_business_trip_code_never_counts(self):
		from hrms.vn_payroll.lunch import lunch_flag_for_attendance

		self._checkin("2098-12-05 08:00:00")
		self._checkin("2098-12-05 17:30:00")
		self.assertFalse(lunch_flag_for_attendance(self.emp, "2098-12-05", "Present", None, "CT"))

	def test_manual_override_wins_both_ways(self):
		"""Người chọn thì máy không đè — kể cả khi dấu chấm nói ngược lại."""
		from hrms.vn_payroll.lunch import lunch_flag_for_attendance

		self._checkin("2098-12-06 08:00:00")
		self._checkin("2098-12-06 17:30:00")
		self.assertFalse(lunch_flag_for_attendance(self.emp, "2098-12-06", "Present", None, "X", "Không"))
		self.assertTrue(lunch_flag_for_attendance(self.emp, "2098-12-07", "On Leave", None, "P", "Có"))

	def test_leave_short_circuits_false(self):
		from hrms.vn_payroll.lunch import lunch_flag_for_attendance

		self._checkin("2098-12-04 08:00:00")
		self._checkin("2098-12-04 17:30:00")
		self.assertFalse(lunch_flag_for_attendance(self.emp, "2098-12-04", "On Leave", None))


class TestLunchPayrollInvariance(PerTestRollback, FrappeTestCase):
	"""L3 — Σ cờ per-Attendance == ``count_lunch_days`` cũ, **với dữ liệu đủ dấu chấm**.

	Từ 2026-08-27 đây KHÔNG còn là bất biến phổ quát: luật mới tính ăn cho ngày công không đủ dấu
	chấm, còn ``count_lunch_days`` chỉ quét checkin nên không thấy những ngày đó. Hai đường chỉ còn
	trùng nhau khi mọi ngày công có ≥2 dấu — đúng bộ dữ liệu dưới đây. Xem
	``test_manual_day_is_where_the_two_paths_diverge`` cho chỗ chúng cố ý lệch."""

	def setUp(self):
		self.emp = test_employee()
		self.company = frappe.db.get_value("Employee", self.emp, "company")

	def _checkin(self, dt):
		frappe.get_doc({"doctype": "Employee Checkin", "employee": self.emp, "time": dt}).insert(
			ignore_permissions=True
		)

	def _att(self, date, status):
		att = frappe.get_doc(
			{
				"doctype": "Attendance",
				"employee": self.emp,
				"attendance_date": date,
				"company": self.company,
				"status": status,
			}
		)
		att.insert(ignore_permissions=True)
		att.submit()
		return att

	def test_sum_of_flags_equals_count_lunch_days(self):
		from hrms.vn_payroll.lunch import count_lunch_days, lunch_flag_for_attendance

		plan = {
			"2099-01-05": ("Present", ["08:00:00", "17:30:00"]),  # ăn
			"2099-01-06": ("Present", ["08:00:00", "17:30:00"]),  # ăn
			"2099-01-07": ("Present", ["14:00:00", "17:30:00"]),  # chỉ chiều → không ăn
			"2099-01-08": ("Absent", []),  # nghỉ → không ăn
		}
		atts = []
		for day, (status, times) in plan.items():
			for t in times:
				self._checkin(f"{day} {t}")
			atts.append(self._att(day, status))

		old = count_lunch_days(self.emp, "2099-01-01", "2099-01-31")
		summed = sum(
			1
			for a in atts
			if lunch_flag_for_attendance(
				self.emp, a.attendance_date, a.status, a.shift, a.custom_attendance_code
			)
		)
		self.assertEqual(summed, old, "Σ cờ per-Attendance phải bằng count_lunch_days cũ")
		self.assertEqual(old, 2)  # đúng 2 ngày ăn

	def test_manual_day_is_where_the_two_paths_diverge(self):
		"""Ghi rõ chỗ hai đường CỐ Ý lệch nhau, để không ai tưởng L3 còn là bất biến phổ quát."""
		from hrms.vn_payroll.lunch import count_lunch_days, lunch_flag_for_attendance

		a = self._att("2099-01-20", "Present")  # chấm tay, không một dấu chấm nào
		self.assertTrue(
			lunch_flag_for_attendance(
				self.emp, a.attendance_date, a.status, a.shift, a.custom_attendance_code
			),
			"luật mới: ngày công đủ chấm tay vẫn được tính ăn",
		)
		self.assertEqual(
			count_lunch_days(self.emp, "2099-01-20", "2099-01-20"),
			0,
			"count_lunch_days chỉ quét checkin nên không thấy ngày chấm tay",
		)

	def test_period_source_matches_old_before_migrate(self):
		# field custom_lunch chưa có trên site → lunch_days_for_period fallback = count_lunch_days
		# (payroll không vỡ trước khi migrate; sau migrate + backfill sẽ đếm từ cờ, cùng số).
		from hrms.vn_payroll.lunch import count_lunch_days, lunch_days_for_period

		for t in ("08:00:00", "17:30:00"):
			self._checkin(f"2099-02-10 {t}")
		self._att("2099-02-10", "Present")
		self.assertEqual(
			lunch_days_for_period(self.emp, "2099-02-01", "2099-02-28"),
			count_lunch_days(self.emp, "2099-02-01", "2099-02-28"),
		)


class TestLunchReport(PerTestRollback, FrappeTestCase):
	"""L4 — report Bảng chấm công có cột 'Số buổi ăn trưa'."""

	def setUp(self):
		self.emp = test_employee()
		self.company = frappe.db.get_value("Employee", self.emp, "company")

	def _checkin(self, dt):
		frappe.get_doc({"doctype": "Employee Checkin", "employee": self.emp, "time": dt}).insert(
			ignore_permissions=True
		)

	def _att(self, date):
		att = frappe.get_doc(
			{
				"doctype": "Attendance",
				"employee": self.emp,
				"attendance_date": date,
				"company": self.company,
				"status": "Present",
			}
		)
		att.insert(ignore_permissions=True)
		att.submit()

	def test_sheet_rows_carry_lunch_days(self):
		from hrms.hr.report.monthly_attendance_report.monthly_attendance_report import get_sheet_rows

		for day in ("2099-03-04", "2099-03-05"):  # 2 ngày ăn
			for t in ("08:00:00", "17:30:00"):
				self._checkin(f"{day} {t}")
			self._att(day)
		self._checkin("2099-03-06 14:00:00")  # chỉ chiều → không ăn
		self._att("2099-03-06")

		rows = get_sheet_rows({"year": 2099, "month": 3, "company": self.company})
		row = next(r for r in rows if r["employee"] == self.emp)
		self.assertEqual(row["lunch_days"], 2)


class TestSheetLunch(PerTestRollback, FrappeTestCase):
	"""L5 — Bảng Công Tháng (Monthly Attendance Sheet) mang tổng ăn trưa."""

	def setUp(self):
		self.emp = test_employee()
		self.company = frappe.db.get_value("Employee", self.emp, "company")

	def _checkin(self, dt):
		frappe.get_doc({"doctype": "Employee Checkin", "employee": self.emp, "time": dt}).insert(
			ignore_permissions=True
		)

	def _att(self, date):
		att = frappe.get_doc(
			{
				"doctype": "Attendance",
				"employee": self.emp,
				"attendance_date": date,
				"company": self.company,
				"status": "Present",
			}
		)
		att.insert(ignore_permissions=True)
		att.submit()

	def test_populate_sets_lunch_days(self):
		for day in ("2099-04-06", "2099-04-07"):
			for t in ("08:00:00", "17:30:00"):
				self._checkin(f"{day} {t}")
			self._att(day)

		sheet = frappe.new_doc("Monthly Attendance Sheet")
		sheet.company = self.company
		sheet.month = 4
		sheet.year = 2099
		sheet.populate_from_attendance()  # bản nháp trong bộ nhớ, không insert
		row = next(r for r in sheet.employees if r.employee == self.emp)
		self.assertEqual(row.get("lunch_days") or 0, 2)


class TestLunchRecompute(PerTestRollback, FrappeTestCase):
	"""L6 — tiện ích tính lại cờ ăn trưa (làm mới khi checkin về muộn)."""

	def setUp(self):
		self.emp = test_employee()
		self.company = frappe.db.get_value("Employee", self.emp, "company")

	def _checkin(self, dt):
		frappe.get_doc({"doctype": "Employee Checkin", "employee": self.emp, "time": dt}).insert(
			ignore_permissions=True
		)

	def _att(self, date):
		att = frappe.get_doc(
			{
				"doctype": "Attendance",
				"employee": self.emp,
				"attendance_date": date,
				"company": self.company,
				"status": "Present",
			}
		)
		att.insert(ignore_permissions=True)
		att.submit()
		return att

	def test_compute_flags_map(self):
		from hrms.vn_payroll.lunch import compute_lunch_flags_for_period

		for t in ("08:00:00", "17:30:00"):  # ăn
			self._checkin(f"2099-05-04 {t}")
		a1 = self._att("2099-05-04")
		self._checkin("2099-05-05 14:00:00")  # chỉ chiều → không ăn
		a2 = self._att("2099-05-05")

		flags = compute_lunch_flags_for_period(5, 2099, self.company)
		self.assertEqual(flags[a1.name], 1)
		self.assertEqual(flags[a2.name], 0)

	def test_recompute_noop_before_migrate(self):
		# field custom_lunch chưa lên site → recompute an toàn, trả 0 (không vỡ payroll).
		# Giả lập tình huống đó thay vì trông vào trạng thái site: mọi site đã migrate (kể cả
		# test_site của CI, nơi fixture sync sẵn custom field) đều có field, test sẽ không đo
		# đúng thứ nó định đo.
		from hrms.vn_payroll.lunch import recompute_lunch_flags

		with patch("frappe.get_meta") as get_meta:
			get_meta.return_value.has_field.return_value = False
			self.assertEqual(recompute_lunch_flags(5, 2099, self.company), 0)

	def test_lunch_days_map_matches_per_employee(self):
		# Round 3: truy vấn gộp cho báo cáo phải ra cùng số với hàm từng-NV.
		from hrms.vn_payroll.lunch import count_lunch_days, lunch_days_map

		for t in ("08:00:00", "17:30:00"):
			self._checkin(f"2099-07-06 {t}")
		self._att("2099-07-06")
		m = lunch_days_map([self.emp], "2099-07-01", "2099-07-31")
		self.assertEqual(m.get(self.emp), count_lunch_days(self.emp, "2099-07-01", "2099-07-31"))
		self.assertEqual(lunch_days_map([], "2099-07-01", "2099-07-31"), {})

	def test_backfill_dry_run_safe_before_migrate(self):
		# L7: backfill an toàn khi field chưa migrate — không ghi gì.
		# backfill_lunch_flags chỉ trả khoá "error" khi Attendance CHƯA có field custom_lunch;
		# site đã migrate thì nó chạy thật và test đỏ. Giả lập trạng thái chưa migrate.
		from hrms.vn_payroll.lunch import backfill_lunch_flags

		with patch("frappe.get_meta") as get_meta:
			get_meta.return_value.has_field.return_value = False
			r = backfill_lunch_flags(dry_run=1)
		self.assertIn("error", r)
		self.assertEqual(r["changed"], 0)


class TestShiftLunchWindow(PerTestRollback, FrappeTestCase):
	"""Fix: khung nghỉ trưa rác/để-trống trên Shift Type → tự về mặc định 12:00-13:30.

	Time field để trống có thể bị đặt = giờ hiện tại (không NULL) → khung ~23:xx làm số buổi ăn = 0.
	shift_lunch_window phải chỉ tin cấu hình khi là khung giữa ngày hợp lý (start < end)."""

	def _shift(self, name, ls, le):
		doc = frappe.get_doc(
			{"doctype": "Shift Type", "__newname": name, "start_time": "08:00:00", "end_time": "17:00:00"}
		)
		if ls is not None:
			doc.custom_lunch_start = ls
		if le is not None:
			doc.custom_lunch_end = le
		doc.insert(ignore_permissions=True)
		return name

	def test_valid_midday_window_used(self):
		from hrms.vn_payroll.lunch import shift_lunch_window

		s = self._shift("ZZ-LW Valid", "11:30:00", "13:00:00")
		self.assertEqual(shift_lunch_window(s), (11 * 60 + 30, 13 * 60))

	def test_equal_garbage_window_falls_back(self):
		from hrms.vn_payroll.lunch import shift_lunch_window

		# giả lập "giờ hiện tại" đặt cả hai bằng nhau (start !< end) → mặc định
		s = self._shift("ZZ-LW Equal", "23:26:00", "23:26:00")
		self.assertEqual(shift_lunch_window(s), (12 * 60, 13 * 60 + 30))

	def test_evening_garbage_window_falls_back(self):
		from hrms.vn_payroll.lunch import shift_lunch_window

		s = self._shift("ZZ-LW Evening", "23:00:00", "23:30:00")  # ngoài khung giữa ngày → mặc định
		self.assertEqual(shift_lunch_window(s), (12 * 60, 13 * 60 + 30))

	def test_no_shift_default(self):
		from hrms.vn_payroll.lunch import shift_lunch_window

		self.assertEqual(shift_lunch_window(None), (12 * 60, 13 * 60 + 30))

	def test_real_shift_window_unchanged(self):
		# ca thật đã cấu hình đúng 12:00-13:30 → KHÔNG đổi (payroll bất biến).
		from hrms.vn_payroll.lunch import shift_lunch_window

		if frappe.db.exists("Shift Type", "Ca Hành Chính"):
			self.assertEqual(shift_lunch_window("Ca Hành Chính"), (12 * 60, 13 * 60 + 30))


class TestWFHCodeOnSheet(PerTestRollback, FrappeTestCase):
	"""Round 2 — làm tại nhà (W) hiển thị + tính Công đúng trên bảng chấm công (integration).

	W là Attendance Code (DML) chưa migrate lên site; tạo trong test (savepoint rollback) để kiểm
	chuỗi: Attendance mã W → report hiện 'W' + cộng vào Công, không lẫn CT."""

	def setUp(self):
		self.emp = test_employee()
		self.company = frappe.db.get_value("Employee", self.emp, "company")
		if not frappe.db.exists("Attendance Code", "W"):
			frappe.get_doc(
				{
					"doctype": "Attendance Code",
					"code": "W",
					"code_name": "Làm tại nhà (Work From Home)",
					"category": "Công",
					"maps_to_status": "Work From Home",
					"work_fraction": 1.0,
					"is_paid": 1,
				}
			).insert(ignore_permissions=True)

	def test_wfh_day_shows_W_and_counts_cong(self):
		from hrms.hr.report.monthly_attendance_report.monthly_attendance_report import get_sheet_rows

		att = frappe.get_doc(
			{
				"doctype": "Attendance",
				"employee": self.emp,
				"attendance_date": "2099-06-03",
				"company": self.company,
				"status": "Work From Home",
				"custom_attendance_code": "W",
			}
		)
		att.insert(ignore_permissions=True)
		att.submit()

		rows = get_sheet_rows({"year": 2099, "month": 6, "company": self.company})
		row = next(r for r in rows if r["employee"] == self.emp)
		self.assertEqual(row["days"][3], "W")  # hiện mã W
		self.assertGreaterEqual(row["totals"].get("Công", 0), 1.0)  # tính vào Công

	def test_codeless_wfh_reverse_defaults_to_CT(self):
		# bản ghi status Work From Home KHÔNG mã (dù W tồn tại) → reverse quy về CT (định danh).
		att = frappe.get_doc(
			{
				"doctype": "Attendance",
				"employee": self.emp,
				"attendance_date": "2099-06-04",
				"company": self.company,
				"status": "Work From Home",
			}
		)
		att.insert(ignore_permissions=True)
		self.assertEqual(att.custom_attendance_code, "CT")  # không phải W


class TestLunchFlagOnSave(PerTestRollback, FrappeTestCase):
	"""L8 — cờ được đặt khi LƯU Attendance, và lựa chọn tay sống sót qua nhiều lần lưu."""

	def setUp(self):
		self.emp = test_employee()

	def attendance(self, date, status="Present", code="X", override=None):
		doc = frappe.get_doc(
			{
				"doctype": "Attendance",
				"employee": self.emp,
				"attendance_date": date,
				"status": status,
				"custom_attendance_code": code,
				"company": frappe.db.get_value("Employee", self.emp, "company"),
			}
		)
		if override:
			doc.custom_lunch_override = override
		doc.insert(ignore_permissions=True)
		return doc

	def test_manual_full_day_without_checkin_gets_lunch(self):
		"""Đúng thứ user phản ánh: chấm tay không làm tăng số buổi ăn trưa."""
		doc = self.attendance("2098-11-02")
		self.assertEqual(doc.custom_lunch, 1)

	def test_override_no_survives_repeated_saves(self):
		"""Regression: trước đây before_validate tính đè mỗi lần lưu nên không sửa tay được."""
		doc = self.attendance("2098-11-03", override="Không")
		self.assertEqual(doc.custom_lunch, 0)
		for _ in range(2):
			doc.save(ignore_permissions=True)
			self.assertEqual(doc.custom_lunch, 0)

	def test_override_yes_survives_repeated_saves(self):
		doc = self.attendance("2098-11-04", status="On Leave", code="P", override="Có")
		self.assertEqual(doc.custom_lunch, 1)
		doc.save(ignore_permissions=True)
		self.assertEqual(doc.custom_lunch, 1)

	def test_business_trip_day_gets_no_lunch(self):
		doc = self.attendance("2098-11-05", code="CT")
		self.assertEqual(doc.custom_lunch, 0)


class TestRecomputeRespectsOverride(PerTestRollback, FrappeTestCase):
	"""L9 — lượt tính lại trước khi chốt lương KHÔNG được xoá lựa chọn tay của HR (spec §5.5)."""

	def setUp(self):
		self.emp = test_employee()
		self.company = frappe.db.get_value("Employee", self.emp, "company")

	def att(self, date, status="Present", code="X", override=None):
		doc = frappe.get_doc(
			{
				"doctype": "Attendance",
				"employee": self.emp,
				"attendance_date": date,
				"company": self.company,
				"status": status,
				"custom_attendance_code": code,
			}
		)
		if override:
			doc.custom_lunch_override = override
		doc.insert(ignore_permissions=True)
		doc.submit()
		return doc

	def test_override_no_survives_recompute(self):
		from hrms.vn_payroll.lunch import compute_lunch_flags_for_period

		a = self.att("2099-07-06", override="Không")
		flags = compute_lunch_flags_for_period(7, 2099, self.company)
		self.assertEqual(flags[a.name], 0)

	def test_override_yes_survives_recompute_on_a_leave_day(self):
		from hrms.vn_payroll.lunch import compute_lunch_flags_for_period

		a = self.att("2099-07-07", status="On Leave", code="P", override="Có")
		flags = compute_lunch_flags_for_period(7, 2099, self.company)
		self.assertEqual(flags[a.name], 1)

	def test_business_trip_excluded_by_recompute(self):
		from hrms.vn_payroll.lunch import compute_lunch_flags_for_period

		a = self.att("2099-07-08", code="CT")
		flags = compute_lunch_flags_for_period(7, 2099, self.company)
		self.assertEqual(flags[a.name], 0)


class TestLunchDoesNotMovePayrollDays(PerTestRollback, FrappeTestCase):
	"""L10 — CỔNG: đổi ăn trưa KHÔNG được xê dịch số công.

	Ăn trưa vào phụ cấp J, còn số ngày được trả lương đọc `status`/`leave_type`/`half_day_status`.
	Hai thứ phải độc lập: bật/tắt ăn trưa mà số công đổi là hỏng payroll."""

	def setUp(self):
		self.emp = test_employee()
		self.company = frappe.db.get_value("Employee", self.emp, "company")

	def payroll_fields(self, name):
		return frappe.db.get_value(
			"Attendance",
			name,
			["status", "leave_type", "half_day_status", "custom_work_credit"],
			as_dict=True,
		)

	def test_toggling_lunch_leaves_every_payroll_field_untouched(self):
		doc = frappe.get_doc(
			{
				"doctype": "Attendance",
				"employee": self.emp,
				"attendance_date": "2099-08-03",
				"company": self.company,
				"status": "Present",
				"custom_attendance_code": "X",
			}
		).insert(ignore_permissions=True)
		before = self.payroll_fields(doc.name)

		for override in ("Có", "Không", "Tự động"):
			doc.custom_lunch_override = override
			doc.save(ignore_permissions=True)
			self.assertEqual(self.payroll_fields(doc.name), before, f"số công đổi khi chọn {override}")

		# và cờ ăn trưa thì đúng là có đổi — nếu không thì test trên vô nghĩa
		doc.custom_lunch_override = "Không"
		doc.save(ignore_permissions=True)
		self.assertEqual(doc.custom_lunch, 0)
		doc.custom_lunch_override = "Có"
		doc.save(ignore_permissions=True)
		self.assertEqual(doc.custom_lunch, 1)


class TestLunchOverrideAfterSubmit(PerTestRollback, FrappeTestCase):
	"""L11 — ô "Ăn trưa" phải sửa được TRÊN BẢN GHI ĐÃ SUBMIT.

	Chấm công vận hành thực tế luôn ở trạng thái đã submit (346/346 bản ghi trên site, không có bản
	nháp nào). Một ô chỉnh tay không sửa được sau submit là ô vô dụng — đúng lỗi HR gặp:
	"Not allowed to change Ăn trưa after submission from Tự động to Có".

	Hai vế phải cùng đúng: (1) field cho phép sửa sau submit, (2) cờ kết quả được tính lại — vì
	`before_validate` KHÔNG chạy ở đường update-after-submit, chỉ `before_update_after_submit` chạy."""

	def setUp(self):
		self.emp = test_employee()
		self.company = frappe.db.get_value("Employee", self.emp, "company")

	def submitted(self, date, status="Present", code="X"):
		doc = frappe.get_doc(
			{
				"doctype": "Attendance",
				"employee": self.emp,
				"attendance_date": date,
				"company": self.company,
				"status": status,
				"custom_attendance_code": code,
			}
		).insert(ignore_permissions=True)
		doc.submit()
		return doc

	def test_both_lunch_fields_are_editable_after_submit(self):
		meta = frappe.get_meta("Attendance")
		self.assertTrue(
			meta.get_field("custom_lunch_override").allow_on_submit,
			"HR phải sửa được ô Ăn trưa trên ngày đã chốt",
		)
		self.assertTrue(
			meta.get_field("custom_lunch").allow_on_submit,
			"cờ kết quả phải ghi được sau submit, nếu không lựa chọn tay không có tác dụng",
		)

	def test_switching_to_co_after_submit_grants_lunch(self):
		doc = self.submitted("2099-12-01", status="On Leave", code="P")
		self.assertEqual(doc.custom_lunch, 0)

		doc.custom_lunch_override = "Có"
		doc.save(ignore_permissions=True)
		self.assertEqual(doc.custom_lunch, 1)
		self.assertEqual(frappe.db.get_value("Attendance", doc.name, "custom_lunch"), 1)

	def test_switching_to_khong_after_submit_removes_lunch(self):
		doc = self.submitted("2099-12-02")
		self.assertEqual(doc.custom_lunch, 1)

		doc.custom_lunch_override = "Không"
		doc.save(ignore_permissions=True)
		self.assertEqual(frappe.db.get_value("Attendance", doc.name, "custom_lunch"), 0)

	def test_switching_back_to_tu_dong_restores_the_computed_value(self):
		doc = self.submitted("2099-12-03")
		doc.custom_lunch_override = "Không"
		doc.save(ignore_permissions=True)
		self.assertEqual(frappe.db.get_value("Attendance", doc.name, "custom_lunch"), 0)

		doc.custom_lunch_override = "Tự động"
		doc.save(ignore_permissions=True)
		self.assertEqual(frappe.db.get_value("Attendance", doc.name, "custom_lunch"), 1)

	def test_editing_lunch_after_submit_does_not_move_payroll_fields(self):
		doc = self.submitted("2099-12-04")
		before = frappe.db.get_value(
			"Attendance",
			doc.name,
			["status", "leave_type", "half_day_status", "custom_work_credit"],
			as_dict=True,
		)
		doc.custom_lunch_override = "Không"
		doc.save(ignore_permissions=True)
		after = frappe.db.get_value(
			"Attendance",
			doc.name,
			["status", "leave_type", "half_day_status", "custom_work_credit"],
			as_dict=True,
		)
		self.assertEqual(dict(after), dict(before))
