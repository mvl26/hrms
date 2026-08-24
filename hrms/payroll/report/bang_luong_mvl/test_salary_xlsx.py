# Copyright (c) 2026, Miyano Việt Nam.
"""Test xuất Excel bảng lương — soi từng ô của workbook dựng trong bộ nhớ.

`build_workbook` là hàm thuần (nhận đúng `columns`/`data` mà `execute()` trả về) nên test không cần
phiếu lương thật: dữ liệu giả đủ để kiểm bố cục, dòng tổng, định dạng số và khối trình ký. Phần số
liệu đã có `test_bang_luong_mvl.py` (báo cáo) và `tests/test_mvl.py` (engine) canh.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from hrms.miyano_xlsx import (
	MIYANO_LETTERHEAD,
	SIGN_APPROVED_LABEL,
	SIGN_NAME_GAP,
	SIGN_PREPARED_LABEL,
	signature_date_line,
)
from hrms.payroll.report.bang_luong_mvl.bang_luong_mvl import get_columns
from hrms.tests.isolation import PerTestRollback
from hrms.vn_payroll.salary_xlsx import (
	FIRST_DATA_ROW,
	HEADER_ROW,
	MONEY_FORMAT,
	SHEET_TITLE,
	TOTAL_LABEL,
	build_workbook,
)

FILTERS = {"company": None, "month": 7, "year": 2026}


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
		net_t=25_994_783.0,
		declared_u=28_584_783.0,
	)
	b = frappe._dict(a, employee="HR-EMP-00002", employee_name="Lê Văn Cường", work_type="Thử việc")
	total = frappe._dict(employee_name=TOTAL_LABEL)
	for key in a:
		if key not in ("employee", "employee_name", "work_type", "pay_mode"):
			total[key] = (a[key] or 0) + (b[key] or 0)
	return [a, b, total]


def build(signatures=None):
	return build_workbook(get_columns(), sample_rows(), FILTERS, signatures).active


class TestSalaryXlsx(PerTestRollback, FrappeTestCase):
	def test_letterhead_sits_above_the_grid(self):
		"""Ba dòng pháp nhân căn trái, rồi tên biểu mẫu + kỳ căn giữa."""
		ws = build()
		self.assertEqual(ws.cell(1, 1).value, MIYANO_LETTERHEAD["name"])
		self.assertIn(MIYANO_LETTERHEAD["tax_id"], ws.cell(2, 1).value)
		self.assertIn("Địa chỉ", ws.cell(3, 1).value)
		self.assertEqual(ws.cell(1, 1).alignment.horizontal, "left")

		self.assertEqual(ws.cell(HEADER_ROW - 3, 1).value, SHEET_TITLE)
		self.assertEqual(ws.cell(HEADER_ROW - 2, 1).value, "Tháng 07 Năm 2026")
		self.assertEqual(ws.cell(HEADER_ROW - 3, 1).alignment.horizontal, "center")
		# dòng ngay trên tiêu đề bảng để trống
		self.assertIsNone(ws.cell(HEADER_ROW - 1, 1).value)

	def test_first_column_is_stt_not_employee_id(self):
		"""Bản in cần số thứ tự; `HR-EMP-00001` chỉ tốn chỗ."""
		ws = build()
		self.assertEqual(ws.cell(HEADER_ROW, 1).value, "STT")
		self.assertEqual(ws.cell(FIRST_DATA_ROW, 1).value, 1)
		self.assertEqual(ws.cell(FIRST_DATA_ROW + 1, 1).value, 2)

		texts = [c.value for row in ws.iter_rows() for c in row if isinstance(c.value, str)]
		self.assertFalse([t for t in texts if t.startswith("HR-EMP")])

	def test_header_labels_follow_the_report(self):
		"""Nhãn cột lấy thẳng từ `get_columns()` — file không được tự đặt tên khác màn hình."""
		ws = build()
		labels = [ws.cell(HEADER_ROW, i).value for i in range(2, len(get_columns()) + 1)]
		expected = [c["label"] for c in get_columns()][1:]  # cột 1 đã thành STT
		self.assertEqual(labels, expected)

	def test_employee_names_land_in_order(self):
		ws = build()
		self.assertEqual(ws.cell(FIRST_DATA_ROW, 2).value, "Trần Thị Bình")
		self.assertEqual(ws.cell(FIRST_DATA_ROW + 1, 2).value, "Lê Văn Cường")

	def test_total_row_is_bold_and_sums_the_money_columns(self):
		"""Dòng TỔNG CỘNG phải còn nguyên: nó không có `employee` nên rất dễ bị lọc mất."""
		ws = build()
		total_row = FIRST_DATA_ROW + 2
		self.assertEqual(ws.cell(total_row, 2).value, TOTAL_LABEL)
		self.assertTrue(ws.cell(total_row, 2).font.bold)
		# không đánh STT cho dòng tổng
		self.assertIsNone(ws.cell(total_row, 1).value)

		fields = [c["fieldname"] for c in get_columns()]
		col = fields.index("net_t") + 1
		self.assertEqual(ws.cell(total_row, col).value, 25_994_783.0 * 2)
		self.assertTrue(ws.cell(total_row, col).font.bold)

	def test_money_columns_are_thousand_separated(self):
		"""Không ai soát được bảng lương khi số hiện là `25994783`."""
		ws = build()
		fields = [c["fieldname"] for c in get_columns()]
		for key in ("work_i", "gross_k", "net_t", "tax_q"):
			cell = ws.cell(FIRST_DATA_ROW, fields.index(key) + 1)
			self.assertEqual(cell.number_format, MONEY_FORMAT, key)

	def test_freeze_panes_keeps_stt_and_name_visible(self):
		ws = build()
		self.assertEqual(ws.freeze_panes, f"C{FIRST_DATA_ROW}")

	def test_signature_block_sits_under_the_table(self):
		ws = build()
		rows = {}
		for row in ws.iter_rows():
			for c in row:
				if c.value in (SIGN_PREPARED_LABEL, SIGN_APPROVED_LABEL):
					rows[c.value] = (c.row, c.column)
		self.assertEqual(len(rows), 2, "thiếu khối ký")
		prepared_row, prepared_col = rows[SIGN_PREPARED_LABEL]
		approved_row, approved_col = rows[SIGN_APPROVED_LABEL]

		self.assertEqual(prepared_row, approved_row)
		self.assertGreater(prepared_row, FIRST_DATA_ROW + 2, "khối ký phải nằm DƯỚI bảng")
		self.assertLess(prepared_col, approved_col, "người duyệt đứng bên phải người lập")
		self.assertGreater(prepared_col, 2, "khối ký không được tràn sang cột STT/Họ tên")

		# dòng địa danh + ngày tháng ngay trên chức danh người duyệt
		self.assertEqual(ws.cell(approved_row - 1, approved_col).value, signature_date_line(None))

	def test_signature_names_land_under_their_titles(self):
		ws = build({"prepared_by": "Phan Thị Thu Lan", "approved_by": "Đoàn Ngọc Anh"})
		found = {}
		for row in ws.iter_rows():
			for c in row:
				if c.value in (SIGN_PREPARED_LABEL, SIGN_APPROVED_LABEL):
					found[c.value] = (c.row, c.column)
		for label, name in (
			(SIGN_PREPARED_LABEL, "Phan Thị Thu Lan"),
			(SIGN_APPROVED_LABEL, "Đoàn Ngọc Anh"),
		):
			row, col = found[label]
			self.assertEqual(ws.cell(row + SIGN_NAME_GAP, col).value, name)

	def test_print_setup_fits_one_page_wide(self):
		ws = build()
		self.assertEqual(ws.page_setup.orientation, "landscape")
		self.assertEqual(ws.page_setup.fitToWidth, 1)
		self.assertEqual(ws.print_title_rows, f"${HEADER_ROW}:${HEADER_ROW}")

	def test_empty_period_still_produces_a_signable_form(self):
		"""Kỳ chưa có phiếu nào: vẫn phải ra tờ giấy có tiêu đề + khối ký, không nổ."""
		ws = build_workbook(get_columns(), [], FILTERS).active
		self.assertEqual(ws.cell(HEADER_ROW - 3, 1).value, SHEET_TITLE)
		self.assertEqual(ws.cell(HEADER_ROW, 1).value, "STT")

	def test_download_rejects_a_call_from_another_report(self):
		"""Bị gọi nhầm từ báo cáo khác thì nói rõ, đừng ném lỗi khó hiểu của `execute()`."""
		from hrms.vn_payroll.salary_xlsx import download

		with self.assertRaises(frappe.ValidationError) as cm:
			download(filters=frappe.as_json({"company": "X"}))
		self.assertIn("Bảng lương", str(cm.exception))


class TestDraftWarning(PerTestRollback, FrappeTestCase):
	"""Bảng có lẫn phiếu chưa chốt thì tờ giấy phải nói ra — không thì người duyệt ký lên số còn đổi."""

	def test_clean_period_has_no_warning(self):
		ws = build()
		self.assertEqual(ws.cell(HEADER_ROW - 2, 1).value, "Tháng 07 Năm 2026")

	def test_including_drafts_stamps_the_title(self):
		from hrms.vn_payroll.salary_xlsx import DRAFT_WARNING

		ws = build_workbook(get_columns(), sample_rows(), dict(FILTERS, include_drafts=1)).active
		self.assertIn(DRAFT_WARNING, ws.cell(HEADER_ROW - 2, 1).value)
		self.assertIn("Tháng 07 Năm 2026", ws.cell(HEADER_ROW - 2, 1).value)
