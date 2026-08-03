# Copyright (c) 2026, Miyano Việt Nam.
import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import getdate

from erpnext.setup.doctype.employee.test_employee import make_employee

from hrms.hr.report.monthly_attendance_report.monthly_attendance_report import execute
from hrms.tests.isolation import PerTestRollback
from hrms.tests.vn_test_utils import test_employee


class TestBangChamCongThang(PerTestRollback, FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.emp = test_employee()
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
		_, data, _msg = execute({"month": self.month, "year": self.year})
		return next(r for r in data if r["employee"] == employee)

	def _cat_labels(self):
		columns, _data, _msg = execute({"month": self.month, "year": self.year})
		return {c["label"]: c["fieldname"] for c in columns if c["fieldname"].startswith("cat_")}

	def test_pivot_cells_and_tong_cong(self):
		self._mk(5, custom_attendance_code="X")  # full work
		self._mk(6, custom_attendance_code="P")  # full annual leave (paid)
		self._mk(7, custom_morning_code="X", custom_afternoon_code="P")  # half work / half leave

		columns, data, _msg = execute({"month": self.month, "year": self.year})
		labels = {c["fieldname"]: c["label"] for c in columns}
		self.assertEqual(labels["tong_cong"], "Tổng công")
		self.assertEqual(labels["cat_0"], "Phép năm")

		row = next(r for r in data if r["employee"] == self.emp)
		self.assertEqual(row["day_5"], "X")
		self.assertEqual(row["day_6"], "P")
		self.assertEqual(row["day_7"], "X/P")
		# Tổng công (số ngày được trả lương) = X(1.0) + P(1.0, có lương) + X/P(0.5 làm + 0.5 phép) = 3.0
		self.assertEqual(row["tong_cong"], 3.0)
		# cột "Phép năm" = P(1.0) + nửa phép của X/P(0.5) = 1.5
		self.assertEqual(row["cat_0"], 1.5)

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

	def test_report_columns_are_the_configured_set(self):
		# Tổng công (đầu, in đậm) + các cột loại nghỉ. Từ 2026-07-30 Ốm và Thai sản có cột RIÊNG vì
		# chúng do BHXH chi trả nên không còn gộp vào Tổng công — không có cột thì số ngày đó biến
		# mất khỏi mọi tổng. Nghỉ bù (công ty trả) vẫn gộp Tổng công; Vắng/Nghỉ lễ chỉ còn ký hiệu.
		columns, _data, _msg = execute({"month": self.month, "year": self.year})
		summary = [
			c["label"] for c in columns if c["fieldname"] == "tong_cong" or c["fieldname"].startswith("cat_")
		]
		self.assertEqual(
			summary,
			[
				"Tổng công",
				"Phép năm",
				"Ốm / chăm con ốm",
				"Thai sản",
				"Tai nạn lao động",
				"Nghỉ riêng",
				"Không lương",
			],
		)

	def test_only_leave_the_company_pays_for_counts_in_tong_cong(self):
		"""Tổng công = ngày DOANH NGHIỆP trả lương.

		Ốm và thai sản do BHXH chi trả (Đ.25/28/39 Luật BHXH) nên không phải công của công ty; nghỉ
		không lương thì đương nhiên không. Ngược lại tai nạn lao động VẪN tính: Đ.38.3 Luật ATVSLĐ
		bắt công ty trả đủ lương trong thời gian điều trị."""
		self._mk(5, custom_attendance_code="Ô")
		self._mk(6, custom_attendance_code="TS")
		self._mk(7, custom_attendance_code="K")
		self._mk(8, custom_attendance_code="P")
		self._mk(9, custom_attendance_code="T")
		row = self._row(self.emp)
		self.assertEqual(row["tong_cong"], 2.0, "chỉ P (phép năm) + T (TNLĐ) là công ty trả")

	def test_single_half_day_code_totals(self):
		from hrms.hr.report.monthly_attendance_report.monthly_attendance_report import get_sheet_rows

		labels = self._cat_labels()
		self._mk(10, custom_attendance_code="1/2X")  # worked half, paid
		self._mk(11, custom_attendance_code="1/2P")  # half work + half annual leave
		self._mk(12, custom_attendance_code="1/2K")  # half work + half unpaid

		row = self._row(self.emp)
		self.assertEqual(row["day_10"], "1/2X")
		self.assertEqual(row["day_11"], "1/2P")
		self.assertEqual(row["day_12"], "1/2K")
		# Tổng công (được trả lương) = 1/2X 0.5 + 1/2P 1.0 (làm+phép) + 1/2K 0.5 (làm) = 2.0
		self.assertEqual(row["tong_cong"], 2.0)
		# Phép năm leave-half of 1/2P = 0.5 ; Không lương leave-half of 1/2K = 0.5
		self.assertEqual(row[labels["Phép năm"]], 0.5)
		self.assertEqual(row[labels["Không lương"]], 0.5)
		# 1/2X nửa kia là nghỉ không lý do → Vắng (không còn cột; kiểm qua totals)
		srow = next(
			r for r in get_sheet_rows({"month": self.month, "year": self.year}) if r["employee"] == self.emp
		)
		self.assertEqual(srow["totals"].get("Vắng"), 0.5)

	def test_a_half_day_code_still_accounts_for_the_whole_day(self):
		"""Mỗi ngày có chấm công phải quy ra đủ 1 công trên bảng — không được bốc hơi nửa nào.

		`1/2X` (đi làm thiếu giờ) có work_fraction 0.5 nhưng category vẫn là "Công", nên nhánh cộng phần
		nghỉ (chỉ chạy khi category != "Công") bỏ sót nửa không làm: ngày đó chỉ vào sổ 0.5 công và
		dòng bảng công không cân về số ngày công của tháng.
		"""
		from hrms.hr.report.monthly_attendance_report.monthly_attendance_report import (
			TOTAL_PAID,
			get_sheet_rows,
		)

		for day, code in ((10, "1/2X"), (11, "1/2P"), (12, "1/2K")):
			self._mk(day, custom_attendance_code=code)

		srow = next(
			r for r in get_sheet_rows({"month": self.month, "year": self.year}) if r["employee"] == self.emp
		)
		# Công thực + phần nghỉ mỗi loại (KHÔNG gồm Tổng công — một aggregate khác) phải cân về 3 công
		total = sum(v for k, v in srow["totals"].items() if k != TOTAL_PAID)
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
		self._mk(20, custom_attendance_code="X")  # submitted
		self._mk_draft(21, custom_attendance_code="X")  # draft — must be excluded
		row = self._row(self.emp)
		self.assertEqual(row["day_20"], "X")
		self.assertNotEqual(row.get("day_21"), "X")
		self.assertEqual(row["tong_cong"], 1.0)  # only the submitted day counts

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
		from hrms.hr.report.monthly_attendance_report.monthly_attendance_report import get_sheet_rows

		self._mk(15, status="Absent")  # ngày vắng (auto-attendance / checkin thiếu giờ), no code
		row = self._row(self.emp)
		self.assertEqual(row["day_15"], "V")
		self.assertEqual(row["tong_cong"], 0.0)  # vắng KHÔNG được trả lương → không vào Tổng công
		srow = next(
			r for r in get_sheet_rows({"month": self.month, "year": self.year}) if r["employee"] == self.emp
		)
		self.assertEqual(srow["totals"].get("Vắng"), 1.0)

	def test_terminated_marker_after_relieving(self):
		emp = make_employee("bcct_terminated@codes.com")
		frappe.db.set_value(
			"Employee", emp, {"relieving_date": f"{self.year}-{self.month:02d}-15", "status": "Left"}
		)
		row = self._row(emp)
		self.assertEqual(row["day_16"], "-")  # day after relieving → rest-day dash
		self.assertEqual(row["day_31"], "-")
		self.assertNotEqual(row.get("day_10"), "-")  # still employed on day 10

	def test_not_yet_joined_marker_before_joining(self):
		"""Ngày trước khi vào làm phải có dấu '-' như ngày sau khi nghỉ việc.

		Để trống thì mơ hồ — HR không phân biệt được 'chưa vào làm' với 'quên chấm công', mà
		payroll thì đã loại các ngày đó khỏi payment_days rồi (theo date_of_joining)."""
		emp = make_employee("bcct_newjoiner@codes.com")
		frappe.db.set_value("Employee", emp, {"date_of_joining": f"{self.year}-{self.month:02d}-10"})
		row = self._row(emp)
		self.assertEqual(row["day_1"], "-", "trước ngày vào làm")
		self.assertEqual(row["day_9"], "-", "ngày liền trước ngày vào làm")
		self.assertNotEqual(row.get("day_10"), "-", "đúng ngày vào làm thì đã đi làm")

	def test_execute_rows_carry_color_state(self):
		# report row mang sẵn "_state_<day>" cho formatter JS tô nền (logic phân loại ở Python)
		self._mk(5, custom_attendance_code="X")
		self._mk(6, custom_attendance_code="1/2P")
		self._mk(7, status="Absent")  # → V
		row = self._row(self.emp)
		self.assertEqual(row["_state_5"], "work")
		self.assertEqual(row["_state_6"], "half")
		self.assertEqual(row["_state_7"], "absent")

	def test_color_state_columns_not_rendered(self):
		# "_state_*" chỉ là metadata cho formatter — KHÔNG được thành cột hiển thị
		columns, _data, _msg = execute({"month": self.month, "year": self.year})
		fieldnames = {c["fieldname"] for c in columns}
		self.assertFalse(
			any(fn.startswith("_state_") for fn in fieldnames), "state màu không được lộ thành cột"
		)


class TestAttendanceColorState(PerTestRollback, FrappeTestCase):
	"""Mã màu hiển thị (thuần trình bày): day_state() phân loại mỗi ô bảng công về một state màu."""

	def _fake_code_map(self):
		# tách khỏi DB — chỉ cần category + work_fraction để phân loại
		def c(category, wf):
			return frappe._dict(category=category, work_fraction=wf)

		return {
			"X": c("Công", 1.0),
			"CT": c("Công", 1.0),
			"1/2X": c("Công", 0.5),
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
			"KH": c("Việc riêng", 0.0),
		}

	def test_day_state_maps_every_code_and_marker(self):
		from hrms.hr.report.monthly_attendance_report.monthly_attendance_report import day_state

		cm = self._fake_code_map()
		cases = {
			# đi làm đủ / công tác → work
			"X": "work",
			"CT": "work",
			# có nửa đi làm → half (bất kể category của mã)
			"1/2X": "half",
			"1/2P": "half",
			"1/2K": "half",
			# nghỉ cả ngày → theo category
			# Phép năm cùng màu tím với 1/2P: nghỉ phép là nghỉ phép, cả ngày hay nửa ngày.
			"P": "half",
			"KH": "leave",  # việc riêng / kết hôn — giữ vàng, KHÔNG theo phép năm
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
		# sáng phép → lấy màu phép (tím), nhất quán với mã P cả ngày
		self.assertEqual(day_state("P/Ô", cm), "half")

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

	def test_get_color_map_returns_full_palette(self):
		# endpoint cho formatter JS: mọi state có đủ nhãn + cặp màu sáng/tối
		from hrms.hr.report.monthly_attendance_report.monthly_attendance_report import get_color_map

		cmap = get_color_map()
		for st in ("work", "half", "leave", "sick", "absent", "unpaid", "comp", "holiday", "off"):
			self.assertIn(st, cmap)
			for key in ("label", "bg", "fg", "bg_dark", "fg_dark"):
				self.assertIn(key, cmap[st])

	def test_attendance_cell_style_for_print(self):
		# Jinja method cho bản in: trả style nền (bản sáng) theo mã; ô trống/không rõ → rỗng
		from hrms.hr.report.monthly_attendance_report.monthly_attendance_report import (
			STATE_STYLE,
			attendance_cell_style,
		)

		self.assertIn(STATE_STYLE["half"]["bg"], attendance_cell_style("1/2P"))
		self.assertIn(STATE_STYLE["work"]["bg"], attendance_cell_style("X"))
		self.assertIn(STATE_STYLE["off"]["bg"], attendance_cell_style("-"))
		self.assertIn(STATE_STYLE["holiday"]["bg"], attendance_cell_style("NL"))
		self.assertEqual(attendance_cell_style(""), "")
		self.assertEqual(attendance_cell_style("khong-phai-ma"), "")

	def test_attendance_state_styles_for_legend(self):
		# Jinja method cho chú giải màu trên bản in
		from hrms.hr.report.monthly_attendance_report.monthly_attendance_report import (
			STATE_STYLE,
			attendance_state_styles,
		)

		self.assertEqual(attendance_state_styles(), STATE_STYLE)


class TestWeekdayHeaders(PerTestRollback, FrappeTestCase):
	"""Nhãn cột ngày mang cả thứ trong tuần — nhìn bảng là biết ngày nào cuối tuần."""

	def labels(self, month, year):
		from hrms.hr.report.monthly_attendance_report.monthly_attendance_report import execute

		columns, _data, _msg = execute({"month": month, "year": year})
		return {c["fieldname"]: c["label"] for c in columns}

	def test_day_labels_carry_the_weekday(self):
		# 2026-08-01 là thứ Bảy → 1 T7, 2 CN, 3 T2
		labels = self.labels(8, 2026)
		self.assertEqual(labels["day_1"], "1 T7")
		self.assertEqual(labels["day_2"], "2 CN")
		self.assertEqual(labels["day_3"], "3 T2")

	def test_weekday_follows_the_month_being_shown(self):
		"""Thứ phải suy từ đúng tháng đang xem, không phải hằng số chép cứng."""
		self.assertEqual(self.labels(9, 2026)["day_1"], "1 T3")  # 2026-09-01 là thứ Ba

	def test_every_day_of_the_month_is_labelled(self):
		from hrms.hr.report.monthly_attendance_report.monthly_attendance_report import WEEKDAY_LABELS

		labels = self.labels(2, 2024)  # tháng nhuận: 29 ngày
		self.assertIn("day_29", labels)
		self.assertNotIn("day_30", labels)
		for day in range(1, 30):
			label = labels[f"day_{day}"]
			self.assertTrue(label.startswith(f"{day} "), f"nhãn ngày {day} phải mở đầu bằng số ngày")
			self.assertIn(label.split(" ")[1], WEEKDAY_LABELS)


class TestLegend(PerTestRollback, FrappeTestCase):
	"""Chú thích ký hiệu: MỘT DÒNG, dùng chung, nằm trên bảng — không làm báo cáo dài ra."""

	def test_the_grid_carries_employee_rows_only(self):
		"""Bỏ 2026-08-03: dòng chú thích văn bản dài ở cuối bảng chỉ làm bẩn lưới.

		Chú thích trên màn hình đi đường `message` (khối chip màu), còn file Excel dựng khối lưới
		riêng — không nơi nào cần dòng đó nữa."""
		from hrms.hr.report.monthly_attendance_report.monthly_attendance_report import execute

		_columns, data, message = execute({"month": 6, "year": 2099})
		self.assertTrue(message, "vẫn phải có khối chú thích màu trên bảng")
		self.assertTrue(all(r.get("employee") for r in data), "mọi dòng phải là dòng nhân viên")
		self.assertFalse(
			[r for r in data if any("=" in str(v) for v in r.values() if isinstance(v, str))],
			"không còn ô nào dồn cả danh sách mã kiểu 'X=Đi làm đủ công; ...'",
		)

	def test_every_attendance_code_is_explained(self):
		from hrms.hr.attendance_legend import legend_pairs

		codes = set(frappe.get_all("Attendance Code", pluck="name"))
		explained = {c for c, _n in legend_pairs()}
		self.assertTrue(codes <= explained, f"mã chưa có chú thích: {codes - explained}")

	def test_calendar_markers_are_explained_too(self):
		from hrms.hr.attendance_legend import legend_pairs

		explained = {c for c, _n in legend_pairs()}
		self.assertIn("-", explained)
		self.assertIn("NL", explained)

	def test_worked_codes_come_first_and_X_leads(self):
		from hrms.hr.attendance_legend import legend_pairs

		codes = [c for c, _n in legend_pairs()]
		self.assertEqual(codes[0], "X", "X là ký hiệu gốc của bảng công nên đứng đầu")
		self.assertLess(codes.index("X"), codes.index("V"), "đi làm phải xếp trước vắng")
		self.assertLess(codes.index("P"), codes.index("1/2P"), "mã cả ngày trước mã nửa ngày")

	def test_the_legend_is_shared_not_copied_per_report(self):
		"""Một nguồn duy nhất: report chỉ gọi helper, không tự dựng danh sách mã."""
		from hrms.hr.attendance_legend import legend_html
		from hrms.hr.report.monthly_attendance_report.monthly_attendance_report import execute

		_columns, _data, message = execute({"month": 6, "year": 2099})
		self.assertEqual(message, legend_html())

	def test_each_symbol_wears_the_same_colour_as_its_cell_in_the_grid(self):
		"""Chú thích phải là bảng màu luôn: chip lấy đúng state màu mà ô đó mang trong lưới."""
		from hrms.hr.attendance_legend import legend_html
		from hrms.hr.report.monthly_attendance_report.monthly_attendance_report import (
			day_state,
			get_code_map,
		)

		html = legend_html()
		code_map = get_code_map()
		for code in ("X", "1/2X", "P", "Ô", "K", "V"):
			state = day_state(code, code_map)
			self.assertIn(f"vn-lg-{state}", html, f"{code} phải mang lớp màu của state {state}")

	def test_the_colours_come_from_the_shared_palette_not_hardcoded(self):
		from hrms.hr.attendance_legend import legend_styles
		from hrms.hr.report.monthly_attendance_report.monthly_attendance_report import STATE_STYLE

		css = legend_styles()
		for state, style in STATE_STYLE.items():
			self.assertIn(f".vn-lg-{state}", css, f"thiếu lớp màu cho state {state}")
			self.assertIn(style["bg"], css, f"{state}: màu nền sáng phải khớp bảng màu chung")
			self.assertIn(style["bg_dark"], css, f"{state}: màu nền tối phải khớp bảng màu chung")

	def test_dark_theme_is_handled_by_attribute_not_only_media_query(self):
		"""Desk đổi theme bằng data-theme; chỉ dựa vào prefers-color-scheme là lệch màu."""
		from hrms.hr.attendance_legend import legend_styles

		self.assertIn('[data-theme="dark"]', legend_styles())


class TestOnlyEmployedPeopleAreOnTheSheet(PerTestRollback, FrappeTestCase):
	"""Bảng công / lương chỉ dựng cho người ĐANG làm việc trong kỳ.

	Nhưng "không Active" không đồng nghĩa "bỏ hẳn": người nghỉ việc giữa tháng vẫn phải được trả
	những ngày đã làm, nên họ phải còn trong bảng của chính tháng đó. Cái phải loại là người đã
	ngừng hoạt động mà không thuộc kỳ nào cả.
	"""

	def mk_employee(self, ten, status, relieving=None, joining="2098-01-01"):
		from erpnext.setup.doctype.employee.test_employee import make_employee

		from hrms.tests.vn_test_utils import default_company

		name = make_employee(f"{ten}@status.test", company=default_company(), date_of_joining=joining)
		frappe.db.set_value("Employee", name, {"status": status, "relieving_date": relieving})
		return name

	def roster(self, month=5, year=2098):
		from hrms.hr.report.monthly_attendance_report.monthly_attendance_report import get_sheet_rows

		return {r["employee"] for r in get_sheet_rows({"month": month, "year": year})}

	def test_an_active_employee_is_on_the_sheet(self):
		emp = self.mk_employee("active_emp", "Active")
		self.assertIn(emp, self.roster())

	def test_an_inactive_employee_is_dropped(self):
		emp = self.mk_employee("inactive_emp", "Inactive")
		self.assertNotIn(emp, self.roster(), "nhân viên Inactive không được vào bảng công")

	def test_a_suspended_employee_is_dropped(self):
		emp = self.mk_employee("suspended_emp", "Suspended")
		self.assertNotIn(emp, self.roster(), "nhân viên Suspended không được vào bảng công")

	def test_someone_who_left_long_ago_is_dropped(self):
		emp = self.mk_employee("left_old_emp", "Left", relieving="2098-02-28")
		self.assertNotIn(emp, self.roster(), "nghỉ việc từ tháng 2 thì không còn trong bảng tháng 5")

	def test_someone_who_left_mid_month_is_still_paid_for_that_month(self):
		"""Đây là chỗ dễ sai nhất: loại thẳng mọi người không Active là quỵt công đã làm."""
		emp = self.mk_employee("left_midmonth_emp", "Left", relieving="2098-05-15")
		self.assertIn(emp, self.roster(), "nghỉ việc giữa tháng vẫn phải có mặt trong bảng tháng đó")


class TestAvgOfficeHours(PerTestRollback, FrappeTestCase):
	"""TB giờ/ngày = tổng giờ có mặt / số ngày làm việc TẠI VĂN PHÒNG.

	Mẫu số là chỗ dễ sai: nghỉ phép, công tác, làm tại nhà, nghỉ lễ đều KHÔNG phải ngày ở văn
	phòng, tính vào là kéo trung bình xuống thành con số vô nghĩa."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.emp = test_employee()
		cls.year, cls.month = 2099, 5

	def mk(self, day, code="X", in_time=None, out_time=None):
		date = f"{self.year}-{self.month:02d}-{day:02d}"
		doc = {
			"doctype": "Attendance",
			"employee": self.emp,
			"attendance_date": getdate(date),
			"custom_attendance_code": code,
		}
		if in_time:
			doc["in_time"], doc["out_time"] = f"{date} {in_time}", f"{date} {out_time}"
		att = frappe.get_doc(doc)
		att.insert()
		att.submit()
		return att

	def avg(self):
		from hrms.hr.report.monthly_attendance_report.monthly_attendance_report import get_sheet_rows

		rows = get_sheet_rows({"month": self.month, "year": self.year})
		return next(r for r in rows if r["employee"] == self.emp)["avg_office_hours"]

	def test_average_is_total_presence_over_office_days(self):
		# nghỉ trưa mặc định 12:00-13:30 bị trừ: 9.5h-1.5 = 8, 10.5h-1.5 = 9 -> TB 8.5
		self.mk(4, in_time="08:00:00", out_time="17:30:00")
		self.mk(5, in_time="08:00:00", out_time="18:30:00")
		self.assertEqual(self.avg(), 8.5)

	def test_leave_days_do_not_dilute_the_average(self):
		self.mk(4, in_time="08:00:00", out_time="17:30:00")
		self.mk(6, code="P")  # nghỉ phép cả ngày
		self.assertEqual(self.avg(), 8.0, "ngày nghỉ phép không được vào mẫu số")

	def test_business_trip_and_wfh_are_not_office_days(self):
		"""CT và W đều mang status `Work From Home` — có punch cũng không phải ngày ở văn phòng."""
		self.mk(4, in_time="08:00:00", out_time="17:30:00")
		self.mk(7, code="CT", in_time="07:00:00", out_time="20:00:00")
		self.assertEqual(self.avg(), 8.0, "ngày công tác không được vào TB")

	def test_a_day_without_punches_is_not_an_office_day(self):
		self.mk(4, in_time="08:00:00", out_time="17:30:00")
		self.mk(8)  # chấm tay, không có giờ vào/ra
		self.assertEqual(self.avg(), 8.0, "ngày không có giờ vào/ra không xác định được thời gian")

	def test_no_office_day_at_all_gives_zero(self):
		self.mk(6, code="P")
		self.assertEqual(self.avg(), 0.0, "không có ngày nào ở văn phòng thì TB là 0, không phải lỗi")

	def test_the_column_reaches_the_report_grid(self):
		from hrms.hr.report.monthly_attendance_report.monthly_attendance_report import execute

		self.mk(4, in_time="08:00:00", out_time="17:30:00")
		columns, data, _msg = execute({"month": self.month, "year": self.year})

		labels = {c["fieldname"]: c["label"] for c in columns}
		self.assertEqual(labels["avg_office_hours"], "TB giờ/ngày")
		row = next(r for r in data if r["employee"] == self.emp)
		self.assertEqual(row["avg_office_hours"], 8.0)
