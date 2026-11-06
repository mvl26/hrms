# Copyright (c) 2026, Miyano Việt Nam.
"""Test xuất Excel bảng lương — soi từng ô của workbook dựng trong bộ nhớ, đối chiếu mẫu
`docs/Salary_template_clean.xlsx` (09/2026).

`build_workbook` là hàm thuần (nhận đúng `columns`/`data` mà `execute()` trả về) nên test không cần
phiếu lương thật: dữ liệu giả đủ để kiểm bố cục, dòng tổng, định dạng số và khối trình ký. Phần số
liệu đã có `test_mvl_salary_register.py` (báo cáo) và `tests/test_mvl.py` (engine) canh.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from hrms.miyano_xlsx import MIYANO_LETTERHEAD, SIGN_APPROVED_LABEL, SIGN_PREPARED_LABEL, signature_date_line
from hrms.payroll.report.mvl_salary_register.mvl_salary_register import get_columns
from hrms.tests.isolation import PerTestRollback
from hrms.vn_payroll.mvl import default_config
from hrms.vn_payroll.salary_xlsx import (
	FIRST_DATA_ROW,
	FONT_NAME,
	HEADER_ROW,
	MONEY_FORMAT,
	SHEET_TITLE,
	TAX_FORMAT,
	TOTAL_LABEL,
	build_workbook,
)

FILTERS = {"company": None, "month": 7, "year": 2026}
FIELDS = [c["fieldname"] for c in get_columns()]


def col(fieldname: str) -> int:
	"""Số cột (1-based) của một fieldname trên file — cột 1 (Mã NV) đã thành STT, thứ tự giữ nguyên."""
	return FIELDS.index(fieldname) + 1


def sample_rows():
	"""Hai nhân viên + dòng TỔNG CỘNG — đúng hình dạng `execute()` của báo cáo trả về."""
	a = frappe._dict(
		employee="HR-EMP-00001",
		employee_name="Trần Thị Bình",
		work_type="Toàn thời gian",
		pay_mode="NET",
		coefficient=1.0,
		base_f=30_000_000.0,
		bhxh_g=30_000_000.0,
		worked_days=19.5,
		work_i=25_434_783.0,
		lunch_j=560_000.0,
		gross_k=25_994_783.0,
		personal_l=15_500_000.0,
		dependents=2,
		deduction_n=27_900_000.0,
		converted_o=0.0,
		taxable_p=0.0,
		tax_q=0.0,
		ins_company_r=6_450_000.0,
		ins_employee_s=3_150_000.0,
		union_fee=600_000.0,
		net_t=25_994_783.0,
		declared_u=28_584_783.0,
		standard_days=22,
		lunch_days=16,
	)
	b = frappe._dict(
		a, employee="HR-EMP-00002", employee_name="Lê Văn Cường", work_type="Bán thời gian", lunch_j=0.0
	)
	b.lunch_days = 17  # bán thời gian: có ăn ở công ty nhưng không được phụ cấp ăn (J = 0)
	total = frappe._dict(employee_name=TOTAL_LABEL)
	for key in a:
		if key not in ("employee", "employee_name", "work_type", "pay_mode", "lunch_days"):
			total[key] = (a[key] or 0) + (b[key] or 0)
	total.pop("standard_days")  # dòng tổng không có công chuẩn
	return [a, b, total]


def workbook(signatures=None, filters=None):
	return build_workbook(get_columns(), sample_rows(), filters or FILTERS, signatures)


def build(signatures=None):
	return workbook(signatures).worksheets[0]


def find(ws, value):
	return next(((c.row, c.column) for row in ws.iter_rows() for c in row if c.value == value), None)


TOTAL_ROW = FIRST_DATA_ROW + 2


class TestSalaryXlsxLayout(PerTestRollback, FrappeTestCase):
	"""Khung tờ giấy — dòng 1-8 của mẫu."""

	def test_sheet_is_named_like_the_template(self):
		# mẫu: tab "Salary 09.2026"
		self.assertEqual(build().title, "Salary 07.2026")

	def test_letterhead_sits_above_the_grid(self):
		ws = build()
		self.assertEqual(ws["A1"].value, MIYANO_LETTERHEAD["name"])
		self.assertTrue(ws["A1"].font.bold)
		self.assertIn(MIYANO_LETTERHEAD["tax_id"], ws["A2"].value)
		self.assertIn("Địa chỉ", ws["A3"].value)
		self.assertIn("Thành phố Hà Nội", ws["A3"].value)  # địa chỉ công ty giữ ĐẦY ĐỦ (HR 2026-11-04)
		self.assertEqual(ws["A1"].alignment.horizontal, "left")
		merged = {str(r) for r in ws.merged_cells.ranges}
		# mẫu gộp tiêu đề thư tới cột U, tên bảng + kỳ tới cột Z
		self.assertTrue({"A1:U1", "A2:U2", "A3:U3", "A5:Z5", "A6:Z6"} <= merged, merged)

	def test_signature_line_says_ha_noi_but_letterhead_keeps_full_address(self):
		# HR 2026-11-04: dòng ngày ký "Hà Nội, ngày …" cho gọn, kể cả khi Address ghi city
		# "Thành phố Hà Nội"; dòng Địa chỉ của công ty thì giữ nguyên đầy đủ.
		from unittest.mock import patch

		from hrms.miyano_xlsx import company_lines

		full = "Số 20, Phường Bồ Đề, Thành phố Hà Nội, Việt Nam"
		with (
			patch("hrms.miyano_xlsx.company_city", return_value="Thành phố Hà Nội"),
			patch("hrms.miyano_xlsx.company_address", return_value=full),
		):
			self.assertTrue(signature_date_line(None).startswith("Hà Nội, ngày "))
			self.assertEqual(company_lines(None)[-1], f"Địa chỉ: {full}")

	def test_title_is_bang_luong(self):
		ws = build()
		self.assertEqual(ws["A5"].value, SHEET_TITLE)
		self.assertEqual(ws["A5"].value, "BẢNG LƯƠNG")
		self.assertTrue(ws["A5"].font.bold)
		self.assertEqual(ws["A5"].font.sz, 16)
		self.assertEqual(ws["A5"].alignment.horizontal, "center")

	def test_period_line_is_a_date_range(self):
		# mẫu A6: "Từ ngày: dd/mm/202y             Đến ngày: dd/mm/202y"
		value = build()["A6"].value
		self.assertTrue(value.startswith("Từ ngày: 01/07/2026"), value)
		self.assertIn("Đến ngày: 31/07/2026", value)

	def test_row7_carries_standard_days_and_rates(self):
		"""Mẫu dòng 7: công chuẩn ở H, giảm trừ người phụ thuộc trên cột Số NPT, ba tỷ lệ trên V/W/X."""
		ws, cfg = build(), default_config()
		self.assertEqual(ws["E7"].value, "Số công làm việc chuẩn:")
		self.assertEqual(ws["E7"].alignment.horizontal, "right")
		self.assertIn("E7:G7", {str(r) for r in ws.merged_cells.ranges})
		self.assertEqual(ws["H7"].value, 22)
		self.assertEqual(ws.cell(7, col("dependents")).value, cfg.dependent_deduction)
		self.assertEqual(ws.cell(7, col("dependents")).number_format, MONEY_FORMAT)
		for key, rate in (
			("ins_company_r", cfg.ins_company),
			("ins_employee_s", cfg.ins_employee),
			("union_fee", cfg.union_fee_rate),
		):
			cell = ws.cell(7, col(key))
			self.assertEqual(cell.value, rate, key)
			self.assertEqual(cell.number_format, "0.0%", key)
			self.assertTrue(cell.font.bold, key)

	def test_header_row_matches_the_template(self):
		ws = build()
		self.assertEqual(ws.cell(HEADER_ROW, 1).value, "STT")
		labels = [ws.cell(HEADER_ROW, i).value for i in range(2, len(FIELDS) + 1)]
		expected = [c["label"] for c in get_columns()][1:]
		# riêng V8 mẫu ghi hai dòng
		expected[col("ins_company_r") - 2] = "Bảo hiểm công ty trả\nEmployer"
		self.assertEqual(labels, expected)

		head = ws.cell(HEADER_ROW, col("gross_k"))
		self.assertEqual((head.font.name, head.font.sz, head.font.bold), (FONT_NAME, 13, True))
		self.assertEqual((head.alignment.horizontal, head.alignment.vertical), ("center", "center"))
		self.assertTrue(head.alignment.wrap_text)
		self.assertEqual(head.border.left.style, "thin")
		self.assertEqual(ws.row_dimensions[HEADER_ROW].height, 66.75)

	def test_column_letters_match_the_template(self):
		# A STT … Z Thu nhập chịu thuế: 26 cột, đúng chữ cột của mẫu
		ws = build()
		self.assertEqual(ws["H8"].value, "Số công làm việc")
		self.assertEqual(ws["O8"].value, "Lương thực lĩnh chưa trừ thuế TNCN, BHXH")
		self.assertEqual(ws["X8"].value, "KPCĐ")
		self.assertEqual(ws["Z8"].value, "Thu nhập chịu thuế")
		self.assertIsNone(ws["AA8"].value)

	def test_freeze_panes_and_zoom_like_the_template(self):
		ws = build()
		self.assertEqual(ws.freeze_panes, f"D{FIRST_DATA_ROW}")
		self.assertEqual(ws.sheet_view.zoomScale, 70)

	def test_print_setup(self):
		ws = build()
		self.assertEqual(ws.page_setup.orientation, "landscape")
		self.assertEqual(int(ws.page_setup.paperSize), 9)  # A4
		self.assertEqual(ws.page_setup.fitToWidth, 1)
		self.assertEqual(ws.page_margins.left, 0.25)
		self.assertEqual(ws.print_title_rows, f"${HEADER_ROW}:${HEADER_ROW}")


class TestSalaryXlsxRows(PerTestRollback, FrappeTestCase):
	def test_rows_numbered_with_names_in_order(self):
		ws = build()
		self.assertEqual(ws.cell(FIRST_DATA_ROW, 1).value, 1)
		self.assertEqual(ws.cell(FIRST_DATA_ROW + 1, 1).value, 2)
		self.assertEqual(ws.cell(FIRST_DATA_ROW, 2).value, "Trần Thị Bình")
		self.assertEqual(ws.cell(FIRST_DATA_ROW + 1, 2).value, "Lê Văn Cường")
		texts = [c.value for row in ws.iter_rows() for c in row if isinstance(c.value, str)]
		self.assertFalse([t for t in texts if t.startswith("HR-EMP")])

	def test_data_cells_use_template_font_border_and_height(self):
		ws = build()
		cell = ws.cell(FIRST_DATA_ROW, col("work_i"))
		self.assertEqual((cell.font.name, cell.font.sz, cell.font.bold), (FONT_NAME, 13, False))
		self.assertEqual(cell.border.bottom.style, "thin")
		self.assertEqual(cell.alignment.vertical, "center")
		self.assertEqual(ws.row_dimensions[FIRST_DATA_ROW].height, 24.75)

	def test_money_columns_use_the_template_accounting_format(self):
		ws = build()
		for key in ("base_f", "work_i", "gross_k", "net_t", "union_fee", "declared_u"):
			self.assertEqual(ws.cell(FIRST_DATA_ROW, col(key)).number_format, MONEY_FORMAT, key)
		# mẫu: cột thuế U dùng định dạng kế toán có ký hiệu ₫
		self.assertEqual(ws.cell(FIRST_DATA_ROW, col("tax_q")).number_format, TAX_FORMAT)

	def test_values_come_from_the_payslip_not_recomputed(self):
		"""Ô dữ liệu là số trên phiếu lương đã chốt — không phải công thức Excel tự tính lại."""
		ws = build()
		self.assertEqual(ws.cell(FIRST_DATA_ROW, col("work_i")).value, 25_434_783.0)
		self.assertEqual(ws.cell(FIRST_DATA_ROW, col("union_fee")).value, 600_000.0)
		self.assertEqual(ws.cell(FIRST_DATA_ROW, col("worked_days")).value, 19.5)

	def test_total_row_holds_the_summed_numbers_not_formulas(self):
		# Công thức `=SUM()` do openpyxl ghi KHÔNG có giá trị tính sẵn → Protected View / xem trước /
		# Excel điện thoại hiện dòng tổng TRỐNG, in ra cũng trống (HR báo 2026-11-04). Ghi số.
		ws = build()
		self.assertEqual(ws.cell(TOTAL_ROW, 1).value, TOTAL_LABEL)  # mẫu: "TỔNG CỘNG" ở cột A
		self.assertTrue(ws.cell(TOTAL_ROW, 1).font.bold)
		for letter in ("F", "H", "I", "N", "O", "U", "X", "Y", "Z"):
			cell = ws[f"{letter}{TOTAL_ROW}"]
			expected = sum(ws[f"{letter}{r}"].value or 0 for r in range(FIRST_DATA_ROW, TOTAL_ROW))
			self.assertNotIsInstance(cell.value, str, letter)
			self.assertEqual(cell.value, expected, letter)
			self.assertTrue(cell.font.bold)
		self.assertEqual(ws[f"F{TOTAL_ROW}"].value, sum(r.base_f for r in sample_rows() if r.get("employee")))
		self.assertIsNone(ws[f"E{TOTAL_ROW}"].value)  # hệ số không cộng
		self.assertEqual(ws.row_dimensions[TOTAL_ROW].height, 30)


class TestSalaryXlsxSignatures(PerTestRollback, FrappeTestCase):
	def test_signature_block_sits_where_the_template_puts_it(self):
		# mẫu: tổng ở dòng 15 → ngày ở R18:T18, chức danh ở dòng 19 (I19:J19 / R19:T19), tên dòng 25,
		# chức vụ dòng 26
		ws = build(
			{
				"prepared_by": "Phan Thị Thu Lan",
				"prepared_title": "Kế toán",
				"approved_by": "Đoàn Ngọc Anh",
				"approved_title": "Giám đốc vận hành",
			}
		)
		date_row, title_row = TOTAL_ROW + 3, TOTAL_ROW + 4
		self.assertEqual(ws[f"R{date_row}"].value, signature_date_line(None))
		self.assertTrue(ws[f"R{date_row}"].font.italic)
		self.assertEqual(ws[f"I{title_row}"].value, SIGN_PREPARED_LABEL)
		self.assertEqual(ws[f"R{title_row}"].value, SIGN_APPROVED_LABEL)
		self.assertEqual(ws[f"I{title_row + 6}"].value, "Phan Thị Thu Lan")
		self.assertEqual(ws[f"R{title_row + 6}"].value, "Đoàn Ngọc Anh")
		self.assertEqual(ws[f"I{title_row + 7}"].value, "Kế toán")
		self.assertEqual(ws[f"R{title_row + 7}"].value, "Giám đốc vận hành")
		merged = {str(r) for r in ws.merged_cells.ranges}
		self.assertTrue(
			{f"R{date_row}:T{date_row}", f"I{title_row}:J{title_row}", f"R{title_row}:T{title_row}"} <= merged
		)

	def test_blank_signatures_leave_room_to_sign_by_hand(self):
		ws = build()
		self.assertIsNotNone(find(ws, SIGN_PREPARED_LABEL))
		self.assertIsNotNone(find(ws, SIGN_APPROVED_LABEL))


class TestLunchSheet(PerTestRollback, FrappeTestCase):
	"""Sheet thứ hai của mẫu: "Ăn trưa 09.2026" — số buổi x đơn giá, giữ lại, nộp quỹ canteen."""

	def test_lunch_sheet_lists_only_people_with_lunch(self):
		ws = workbook().worksheets[1]
		self.assertEqual(ws.title, "Ăn trưa 07.2026")
		self.assertEqual(ws["A1"].value, "Ăn trưa tháng 7.2026")
		self.assertEqual(ws["D1"].value, default_config().lunch_rate)
		self.assertEqual(
			[ws.cell(3, c).value for c in range(3, 7)],
			["Số buổi ăn trưa", "Thành tiền", "Giữ lại", "Nộp quỹ canteen"],
		)
		self.assertEqual([ws["A4"].value, ws["B4"].value, ws["C4"].value], [1, "Trần Thị Bình", 16])
		self.assertEqual(ws["D4"].value, 560_000.0)  # đúng số trên phiếu lương (cột J)
		self.assertEqual(ws["E4"].value, 0)
		self.assertEqual(ws["F4"].value, 560_000.0)  # nộp quỹ = thành tiền - giữ lại, ghi SỐ
		# Lê Văn Cường (bán thời gian) có buổi ăn nhưng không được phụ cấp → không có dòng; kế là Tổng
		self.assertEqual(ws["B5"].value, "Tổng")
		self.assertEqual(ws["D5"].value, 560_000.0)
		self.assertEqual(ws["F5"].value, 560_000.0)

	def test_kept_lunches_fill_the_kept_column_and_cut_the_canteen_fund(self):
		rows = sample_rows()
		rows[0].lunch_kept_days = 2
		ws = build_workbook(get_columns(), rows, FILTERS).worksheets[1]
		self.assertEqual(ws["D4"].value, 560_000.0, "thành tiền = phụ cấp trên phiếu, giữ nguyên")
		self.assertEqual(ws["E4"].value, 70_000, "2 buổi x 35.000 (đơn giá phiếu đã áp)")
		self.assertEqual(ws["F4"].value, 490_000.0)
		self.assertEqual(ws["F5"].value, 490_000.0, "dòng Tổng nộp quỹ cũng là số")

	def test_unit_price_is_the_rate_the_slips_used_not_todays_setting(self):
		# HR đổi Settings 35.000 → 50.000 SAU khi phiếu đã tính: D1 vẫn phải là 35.000 — đơn giá đã
		# nhân ra cột Thành tiền. In 50.000 thì tờ giấy ghi "16 buổi x 50.000 = 560.000".
		from dataclasses import replace

		cfg = replace(default_config(), lunch_rate=50_000)
		ws = build_workbook(get_columns(), sample_rows(), FILTERS, None, cfg).worksheets[1]
		self.assertEqual(ws["D1"].value, 35_000)  # 560.000 / 16 buổi

	def test_unit_price_falls_back_to_settings_when_nobody_had_lunch(self):
		from dataclasses import replace

		rows = [frappe._dict(r, lunch_j=0, lunch_days=0) for r in sample_rows()]
		cfg = replace(default_config(), lunch_rate=50_000)
		ws = build_workbook(get_columns(), rows, FILTERS, None, cfg).worksheets[1]
		self.assertEqual(ws["D1"].value, 50_000)


class TestSalaryXlsxEdges(PerTestRollback, FrappeTestCase):
	def test_empty_period_still_produces_a_signable_form(self):
		ws = build_workbook(get_columns(), [], FILTERS).worksheets[0]
		self.assertEqual(ws["A5"].value, SHEET_TITLE)
		self.assertEqual(ws.cell(HEADER_ROW, 1).value, "STT")
		self.assertIsNotNone(find(ws, SIGN_APPROVED_LABEL))

	def test_including_drafts_stamps_the_period_line(self):
		from hrms.vn_payroll.salary_xlsx import DRAFT_WARNING

		clean = build()["A6"].value
		self.assertNotIn(DRAFT_WARNING, clean)
		ws = workbook(filters=dict(FILTERS, include_drafts=1)).worksheets[0]
		self.assertIn(DRAFT_WARNING, ws["A6"].value)
		self.assertIn("Từ ngày: 01/07/2026", ws["A6"].value)

	def test_download_rejects_a_call_from_another_report(self):
		"""Bị gọi nhầm từ báo cáo khác thì nói rõ, đừng ném lỗi khó hiểu của `execute()`."""
		from hrms.vn_payroll.salary_xlsx import download

		with self.assertRaises(frappe.ValidationError) as cm:
			download(filters=frappe.as_json({"company": "X"}))
		self.assertIn("Bảng lương", str(cm.exception))
