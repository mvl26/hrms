# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import getdate

from erpnext.setup.doctype.employee.test_employee import make_employee

from hrms.hr.report.monthly_attendance_report.monthly_attendance_report import execute


class TestBangChamCongThang(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.emp = frappe.db.get_value("Employee", {}, "name")
		cls.year, cls.month = 2099, 3  # far future to avoid colliding with any real/test data

	def _mk(self, day, **codes):
		att = frappe.get_doc(
			{
				"doctype": "Attendance",
				"employee": self.emp,
				"attendance_date": getdate(f"{self.year}-{self.month:02d}-{day:02d}"),
				**codes,
			}
		)
		att.insert()
		att.submit()  # only submitted Attendance is real timekeeping (matches payroll's docstatus==1)
		return att

	def _mk_draft(self, day, **codes):
		att = frappe.get_doc(
			{
				"doctype": "Attendance",
				"employee": self.emp,
				"attendance_date": getdate(f"{self.year}-{self.month:02d}-{day:02d}"),
				**codes,
			}
		)
		att.insert()  # left as a draft (docstatus 0)
		return att

	def _row(self, employee):
		_, data = execute({"month": self.month, "year": self.year})
		return next(r for r in data if r["employee"] == employee)

	def _cat_labels(self):
		columns, _ = execute({"month": self.month, "year": self.year})
		return {c["label"]: c["fieldname"] for c in columns if c["fieldname"].startswith("cat_")}

	def test_pivot_cells_and_category_totals(self):
		self._mk(5, custom_attendance_code="X")  # full work
		self._mk(6, custom_attendance_code="P")  # full annual leave
		self._mk(7, custom_morning_code="X", custom_afternoon_code="P")  # half work / half leave

		columns, data = execute({"month": self.month, "year": self.year})
		labels = {c["fieldname"]: c["label"] for c in columns}
		self.assertEqual(labels["cat_0"], "Công")
		self.assertEqual(labels["cat_1"], "Phép")

		row = next(r for r in data if r["employee"] == self.emp)
		self.assertEqual(row["day_5"], "X")
		self.assertEqual(row["day_6"], "P")
		self.assertEqual(row["day_7"], "X/P")
		# Công = X(1.0) + half X(0.5) = 1.5 ; Phép = P(1.0) + half P(0.5) = 1.5
		self.assertEqual(row["cat_0"], 1.5)
		self.assertEqual(row["cat_1"], 1.5)

	def test_get_sheet_rows_semantic_shape(self):
		# the shared derivation used by the Bảng Công Tháng DocType returns semantic rows
		from hrms.hr.report.monthly_attendance_report.monthly_attendance_report import get_sheet_rows

		self._mk(5, custom_attendance_code="X")
		self._mk(6, custom_attendance_code="P")
		rows = get_sheet_rows({"month": self.month, "year": self.year})
		row = next(r for r in rows if r["employee"] == self.emp)
		self.assertEqual(row["days"][5], "X")
		self.assertEqual(row["days"][6], "P")
		self.assertEqual(row["totals"]["Công"], 1.0)
		self.assertEqual(row["totals"]["Phép"], 1.0)

	def test_new_categories_present(self):
		# all seeded categories must have a totals column, including the new ones
		labels = self._cat_labels()
		for cat in ("Công", "Phép", "Việc riêng", "Ốm", "Thai sản", "Tai nạn LĐ", "Nghỉ bù", "Không lương"):
			self.assertIn(cat, labels, f"missing totals column for {cat}")

	def test_single_half_day_code_totals(self):
		labels = self._cat_labels()
		self._mk(10, custom_attendance_code="NN")  # worked half, paid
		self._mk(11, custom_attendance_code="1/2P")  # half work + half annual leave
		self._mk(12, custom_attendance_code="1/2K")  # half work + half unpaid

		row = self._row(self.emp)
		self.assertEqual(row["day_10"], "NN")
		self.assertEqual(row["day_11"], "1/2P")
		self.assertEqual(row["day_12"], "1/2K")
		# Công (worked) = NN 0.5 + 1/2P 0.5 + 1/2K 0.5 = 1.5
		self.assertEqual(row[labels["Công"]], 1.5)
		# Phép leave-half of 1/2P = 0.5 ; Không lương leave-half of 1/2K = 0.5
		self.assertEqual(row[labels["Phép"]], 0.5)
		self.assertEqual(row[labels["Không lương"]], 0.5)
		# NN chỉ nói "làm nửa ngày", không nói nửa kia nghỉ vì gì -> nửa kia là nghỉ không lý do
		self.assertEqual(row[labels["Vắng"]], 0.5)

	def test_a_half_day_code_still_accounts_for_the_whole_day(self):
		"""Mỗi ngày có chấm công phải quy ra đủ 1 công trên bảng — không được bốc hơi nửa nào.

		`NN` (làm nửa ngày) có work_fraction 0.5 nhưng category vẫn là "Công", nên nhánh cộng phần
		nghỉ (chỉ chạy khi category != "Công") bỏ sót nửa không làm: ngày đó chỉ vào sổ 0.5 công và
		dòng bảng công không cân về số ngày công của tháng.
		"""
		labels = self._cat_labels()
		for day, code in ((10, "NN"), (11, "1/2P"), (12, "1/2K")):
			self._mk(day, custom_attendance_code=code)

		row = self._row(self.emp)
		total = sum(row.get(field) or 0 for field in labels.values())
		self.assertEqual(total, 3.0, "3 ngày nửa công phải quy ra đúng 3 công")

	def test_calendar_markers_weekly_off_and_holiday(self):
		# HR convention: weekly-off (rest day) renders "-"; a paid public holiday stays "NL"
		hl = frappe.get_doc(
			{
				"doctype": "Holiday List",
				"holiday_list_name": "BCCT Test HL 2099-03",
				"from_date": f"{self.year}-{self.month:02d}-01",
				"to_date": f"{self.year}-{self.month:02d}-28",
				"holidays": [
					{
						"holiday_date": f"{self.year}-{self.month:02d}-01",
						"description": "CN",
						"weekly_off": 1,
					},
					{
						"holiday_date": f"{self.year}-{self.month:02d}-02",
						"description": "Lễ",
						"weekly_off": 0,
					},
				],
			}
		).insert()
		emp = make_employee("bcct_holidays@codes.com")
		frappe.db.set_value(
			"Employee", emp, {"holiday_list": hl.name, "relieving_date": None, "status": "Active"}
		)

		row = self._row(emp)
		self.assertEqual(row["day_1"], "-")  # weekly off → rest-day dash
		self.assertEqual(row["day_2"], "NL")  # public holiday → kept distinct (paid)

	def test_draft_attendance_excluded_from_snapshot(self):
		# a frozen sheet must count only submitted Attendance, like payroll (docstatus==1);
		# a still-draft day never becomes payroll reality, so it must not appear or count.
		labels = self._cat_labels()
		self._mk(20, custom_attendance_code="X")  # submitted
		self._mk_draft(21, custom_attendance_code="X")  # draft — must be excluded
		row = self._row(self.emp)
		self.assertEqual(row["day_20"], "X")
		self.assertNotEqual(row.get("day_21"), "X")
		self.assertEqual(row[labels["Công"]], 1.0)  # only the submitted day counts

	def test_public_holiday_counted_in_nghi_le_total(self):
		# a paid public holiday (NL) must count toward a "Nghỉ lễ" total (nghỉ lễ hưởng lương);
		# a weekly-off rest day (CN, "-") must NOT count.
		from hrms.hr.report.monthly_attendance_report.monthly_attendance_report import get_sheet_rows

		hl = frappe.get_doc(
			{
				"doctype": "Holiday List",
				"holiday_list_name": "BCCT NL Test 2099-03",
				"from_date": f"{self.year}-{self.month:02d}-01",
				"to_date": f"{self.year}-{self.month:02d}-28",
				"holidays": [
					{
						"holiday_date": f"{self.year}-{self.month:02d}-05",
						"description": "Lễ",
						"weekly_off": 0,
					},
					{
						"holiday_date": f"{self.year}-{self.month:02d}-06",
						"description": "Lễ",
						"weekly_off": 0,
					},
					{
						"holiday_date": f"{self.year}-{self.month:02d}-08",
						"description": "CN",
						"weekly_off": 1,
					},
				],
			}
		).insert()
		emp = make_employee("bcct_nghi_le@codes.com")
		frappe.db.set_value(
			"Employee", emp, {"holiday_list": hl.name, "relieving_date": None, "status": "Active"}
		)
		rows = get_sheet_rows({"month": self.month, "year": self.year})
		row = next(r for r in rows if r["employee"] == emp)
		self.assertEqual(row["days"][5], "NL")
		self.assertEqual(row["days"][8], "-")
		self.assertEqual(row["totals"].get("Nghỉ lễ"), 2.0)  # 2 paid holidays, weekly-off excluded

	def test_absent_day_renders_v(self):
		labels = self._cat_labels()
		self._mk(15, status="Absent")  # ngày vắng (auto-attendance / checkin thiếu giờ), no code
		row = self._row(self.emp)
		self.assertEqual(row["day_15"], "V")
		self.assertEqual(row[labels["Vắng"]], 1.0)

	def test_terminated_marker_after_relieving(self):
		emp = make_employee("bcct_terminated@codes.com")
		frappe.db.set_value(
			"Employee", emp, {"relieving_date": f"{self.year}-{self.month:02d}-15", "status": "Left"}
		)
		row = self._row(emp)
		self.assertEqual(row["day_16"], "-")  # day after relieving → rest-day dash
		self.assertEqual(row["day_31"], "-")
		self.assertNotEqual(row.get("day_10"), "-")  # still employed on day 10


class TestAttendanceColorState(FrappeTestCase):
	"""Mã màu hiển thị (thuần trình bày): day_state() phân loại mỗi ô bảng công về một state màu."""

	def _fake_code_map(self):
		# tách khỏi DB — chỉ cần category + work_fraction để phân loại
		def c(category, wf):
			return frappe._dict(category=category, work_fraction=wf)

		return {
			"X": c("Công", 1.0),
			"CT": c("Công", 1.0),
			"NN": c("Công", 0.5),
			"1/2P": c("Phép", 0.5),
			"1/2K": c("Không lương", 0.5),
			"P": c("Phép", 0.0),
			"Ô": c("Ốm", 0.0),
			"Cô": c("Ốm", 0.0),
			"TS": c("Thai sản", 0.0),
			"T": c("Tai nạn LĐ", 0.0),
			"NB": c("Nghỉ bù", 0.0),
			"K": c("Không lương", 0.0),
			"V": c("Vắng", 0.0),
			"N": c("Việc riêng", 0.0),
		}

	def test_day_state_maps_every_code_and_marker(self):
		from hrms.hr.report.monthly_attendance_report.monthly_attendance_report import day_state

		cm = self._fake_code_map()
		cases = {
			# đi làm đủ / công tác → work
			"X": "work",
			"CT": "work",
			# có nửa đi làm → half (bất kể category của mã)
			"NN": "half",
			"1/2P": "half",
			"1/2K": "half",
			# nghỉ cả ngày → theo category
			"P": "leave",
			"N": "leave",  # việc riêng (mặc định gộp phép/vàng)
			"Ô": "sick",
			"Cô": "sick",
			"TS": "sick",
			"T": "sick",
			"V": "absent",
			"K": "unpaid",
			"NB": "comp",
			# marker lịch (không phải Attendance Code)
			"-": "off",
			"NL": "holiday",
		}
		for symbol, expected in cases.items():
			self.assertEqual(day_state(symbol, cm), expected, f"{symbol} → {expected}")

		# ô trống → không tô
		self.assertIsNone(day_state("", cm))
		self.assertIsNone(day_state(None, cm))

	def test_day_state_split_cells(self):
		from hrms.hr.report.monthly_attendance_report.monthly_attendance_report import day_state

		cm = self._fake_code_map()
		# ô ghép sáng/chiều: có nửa đi làm → half (dù ở nửa nào)
		self.assertEqual(day_state("X/P", cm), "half")
		self.assertEqual(day_state("P/X", cm), "half")
		self.assertEqual(day_state("X/Ô", cm), "half")
		# không nửa nào đi làm → theo category nửa sáng
		self.assertEqual(day_state("Ô/P", cm), "sick")
		self.assertEqual(day_state("P/Ô", cm), "leave")

	def test_style_map_covers_every_state(self):
		from hrms.hr.report.monthly_attendance_report.monthly_attendance_report import (
			CATEGORY_STATE,
			STATE_STYLE,
		)

		# mọi state suy ra được đều có định nghĩa màu (nhãn + nền/chữ, cả sáng & tối)
		states = set(CATEGORY_STATE.values()) | {"work", "half", "off", "holiday"}
		for st in states:
			self.assertIn(st, STATE_STYLE, f"thiếu màu cho state {st}")
			style = STATE_STYLE[st]
			for key in ("label", "bg", "fg", "bg_dark", "fg_dark"):
				self.assertIn(key, style, f"state {st} thiếu {key}")

	def test_every_attendance_code_category_has_a_color(self):
		# HR thêm Attendance Code category mới mà quên gán màu → test này fail để nhắc bổ sung
		from hrms.hr.report.monthly_attendance_report.monthly_attendance_report import (
			CATEGORY_STATE,
			get_code_map,
		)

		cats = {c.category for c in get_code_map().values() if c.category}
		missing = cats - set(CATEGORY_STATE)
		self.assertEqual(missing, set(), f"category chưa gán màu: {missing}")
