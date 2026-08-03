# Copyright (c) 2026, Miyano Việt Nam.
"""File Excel xuất ra phải giống bảng trên màn hình: có màu, và chú thích là lưới chứ không phải
một dòng văn bản dài.

Test dựng workbook trong bộ nhớ (`build_workbook`) rồi soi từng ô — không đụng HTTP, không ghi
file, nên chạy được trong harness rollback."""

from io import BytesIO

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import getdate

from hrms.hr.attendance_legend import legend_pairs
from hrms.hr.attendance_xlsx import LEGEND_LABEL, MAX_LEGEND_ROWS, build_workbook, legend_layout
from hrms.hr.report.monthly_attendance_report.monthly_attendance_report import STATE_STYLE, execute
from hrms.tests.isolation import PerTestRollback
from hrms.tests.vn_test_utils import test_employee


def rgb(cell) -> str:
	"""Mã màu nền của ô, viết thường không có alpha — `FFD9EFDC` → `d9efdc`."""
	fill = cell.fill
	if not fill or fill.fill_type != "solid":
		return ""
	return str(fill.start_color.rgb or "")[-6:].lower()


class TestAttendanceXlsx(PerTestRollback, FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.emp = test_employee()
		cls.year, cls.month = 2099, 3  # xa tương lai để không đụng dữ liệu thật

	def mk(self, day, **codes):
		att = frappe.get_doc(
			{
				"doctype": "Attendance",
				"employee": self.emp,
				"attendance_date": getdate(f"{self.year}-{self.month:02d}-{day:02d}"),
				**codes,
			}
		)
		att.insert()
		att.submit()
		return att

	def sheet(self, **extra):
		filters = {"month": self.month, "year": self.year, **extra}
		columns, data, _msg = execute(filters)
		wb = build_workbook(columns, data, filters)
		return wb.active

	def find_row(self, ws, employee):
		for row in ws.iter_rows(min_col=1, max_col=1):
			if row[0].value == employee:
				return row[0].row
		raise AssertionError(f"không thấy dòng của {employee} trong sheet")

	def col_of(self, ws, header):
		"""Cột mang nhãn `header` trên dòng tiêu đề."""
		for row in ws.iter_rows():
			for cell in row:
				if cell.value == header:
					return cell.column
		raise AssertionError(f"không thấy cột {header}")

	# ── màu ô mã công ───────────────────────────────────────────────────────────────────────

	def test_day_cells_carry_state_colours(self):
		self.mk(5, custom_attendance_code="X")  # đi làm đủ  → work
		self.mk(6, custom_attendance_code="P")  # phép năm   → leave
		self.mk(7, custom_attendance_code="V")  # vắng       → absent

		ws = self.sheet()
		r = self.find_row(ws, self.emp)
		day_col = self.col_of(ws, "1") - 1  # cột ngày N = day_col + N

		self.assertEqual(rgb(ws.cell(r, day_col + 5)), STATE_STYLE["work"]["bg"].lstrip("#"))
		self.assertEqual(rgb(ws.cell(r, day_col + 6)), STATE_STYLE["leave"]["bg"].lstrip("#"))
		self.assertEqual(rgb(ws.cell(r, day_col + 7)), STATE_STYLE["absent"]["bg"].lstrip("#"))
		self.assertEqual(ws.cell(r, day_col + 5).value, "X")

	def test_half_day_cell_uses_half_colour(self):
		self.mk(11, custom_morning_code="X", custom_afternoon_code="P")

		ws = self.sheet()
		r = self.find_row(ws, self.emp)
		cell = ws.cell(r, self.col_of(ws, "1") - 1 + 11)
		self.assertEqual(cell.value, "X/P")
		self.assertEqual(rgb(cell), STATE_STYLE["half"]["bg"].lstrip("#"))

	def test_tong_cong_is_bold_and_matches_report(self):
		self.mk(5, custom_attendance_code="X")
		self.mk(6, custom_attendance_code="P")

		_cols, data, _msg = execute({"month": self.month, "year": self.year})
		expected = next(row["tong_cong"] for row in data if row.get("employee") == self.emp)

		ws = self.sheet()
		cell = ws.cell(self.find_row(ws, self.emp), self.col_of(ws, "Tổng công"))
		self.assertEqual(cell.value, expected)
		self.assertTrue(cell.font.bold, "cột Tổng công phải in đậm như trên màn hình")

	def test_header_is_frozen_and_titled(self):
		ws = self.sheet()
		self.assertEqual(ws.freeze_panes, "C4")
		self.assertIn(f"{self.month}/{self.year}", str(ws.cell(1, 1).value))

	# ── khối chú thích ──────────────────────────────────────────────────────────────────────

	def test_long_text_legend_row_is_dropped(self):
		"""Dòng chú thích văn bản dài của báo cáo không được lọt vào file — đã có khối lưới."""
		ws = self.sheet()
		for row in ws.iter_rows():
			for cell in row:
				if isinstance(cell.value, str):
					self.assertNotIn("X=", cell.value, "dòng chú thích dạng văn bản dài còn sót")

	def test_legend_grid_layout(self):
		ws = self.sheet()
		pairs = legend_pairs()

		label_cells = [c for row in ws.iter_rows() for c in row if c.value == LEGEND_LABEL and c.column == 1]
		self.assertEqual(len(label_cells), 1, "chữ 'Chú thích' phải nằm đúng MỘT ô")
		top = label_cells[0].row

		# mỗi ký hiệu một ô, nghĩa ở ô ngang hàng ngay bên phải
		seen = {}
		for row in ws.iter_rows(min_row=top):
			for cell in row:
				if cell.value in dict(pairs) and cell.column > 1:
					seen[cell.value] = (cell.row, cell.column)
		self.assertEqual(set(seen), {code for code, _name in pairs}, "thiếu ký hiệu trong chú thích")

		for code, name in pairs:
			r, c = seen[code]
			self.assertEqual(ws.cell(r, c + 1).value, name, f"nghĩa của {code} phải ngang hàng bên phải")

		rows_used = {r for r, _c in seen.values()}
		self.assertLessEqual(len(rows_used), MAX_LEGEND_ROWS, "chú thích không được quá 10 dòng")

	def test_legend_symbol_cells_are_coloured(self):
		ws = self.sheet()
		codes = {}
		for row in ws.iter_rows():
			for cell in row:
				if cell.value in ("X", "P", "V") and cell.column > 2 and rgb(cell):
					codes.setdefault(cell.value, []).append(rgb(cell))
		# ký hiệu trong chú thích mang đúng màu state của nó (giống hệt ô trong lưới)
		self.assertIn(STATE_STYLE["work"]["bg"].lstrip("#"), codes.get("X", []))
		self.assertIn(STATE_STYLE["leave"]["bg"].lstrip("#"), codes.get("P", []))
		self.assertIn(STATE_STYLE["absent"]["bg"].lstrip("#"), codes.get("V", []))

	# ── endpoint của nút Export ─────────────────────────────────────────────────────────────

	def test_download_returns_a_readable_xlsx(self):
		"""Đi hết đường thật: whitelisted method → `frappe.response` mang file mở lại được."""
		from openpyxl import load_workbook

		from hrms.hr.attendance_xlsx import download

		self.mk(5, custom_attendance_code="X")
		response = frappe.local.response
		try:
			download(filters=frappe.as_json({"month": self.month, "year": self.year}))
			self.assertEqual(frappe.response["type"], "binary")
			self.assertTrue(frappe.response["filename"].endswith(".xlsx"))
			ws = load_workbook(BytesIO(frappe.response["filecontent"])).active
			self.assertIn(f"{self.month}/{self.year}", str(ws.cell(1, 1).value))
		finally:
			frappe.local.response = response

	# ── luật chia cụm cột (thuần hàm, không cần dữ liệu) ─────────────────────────────────────

	def test_legend_splits_into_column_groups(self):
		self.assertEqual(legend_layout(8), (1, 8))  # vừa 10 dòng → một cụm
		self.assertEqual(legend_layout(10), (1, 10))  # đúng ngưỡng → vẫn một cụm
		self.assertEqual(legend_layout(16), (2, 8))  # 16 mã → 2 cụm, 8 dòng
		self.assertEqual(legend_layout(21), (3, 7))  # 21 mã → 3 cụm, 7 dòng
		for n in range(1, 60):
			groups, rows = legend_layout(n)
			self.assertLessEqual(rows, MAX_LEGEND_ROWS)
			self.assertGreaterEqual(groups * rows, n, "phải đủ chỗ cho mọi ký hiệu")
