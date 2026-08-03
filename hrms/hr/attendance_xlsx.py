# Copyright (c) 2026, Miyano Việt Nam.
"""Xuất bảng chấm công tháng ra Excel **có màu** — file trông như bảng trên màn hình.

Nút Export mặc định của query report đi qua `frappe.desk.query_report.export_query`, dựng file bằng
`make_xlsx()` từ `columns` + `result`. Đường đó không có chỗ móc để tô màu: mọi ô ra file đều trắng
trơn. Module này là đường xuất riêng của báo cáo `Monthly Attendance Report`, dựng workbook bằng
openpyxl nên kiểm soát được từng ô.

Hai đường ra:

- `build_workbook(columns, data, filters)` — thuần hàm, không đụng HTTP, để test soi từng ô.
- `download(filters, visible_idx)` — endpoint cho nút Export trên report.

Màu **không định nghĩa lại ở đây**: lấy nguyên `STATE_STYLE` của `monthly_attendance_report`, dùng
cặp màu nền sáng (`bg`/`fg`) — bản nền tối chỉ có nghĩa trong Desk. State của từng ô cũng không tính
lại: `execute()` đã gắn sẵn `_state_<day>` lên mỗi dòng, y như formatter JS đọc.

CHỈ ĐỌC: không ghi Attendance, không đụng `status`/`leave_type`/`half_day_status` → lương bất biến.
"""

from io import BytesIO
from math import ceil

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

import frappe
from frappe import _
from frappe.utils import cint, flt

from hrms.hr.attendance_legend import legend_pairs
from hrms.hr.report.monthly_attendance_report.monthly_attendance_report import (
	STATE_STYLE,
	day_state,
	execute,
	get_code_map,
	weekday_label,
)

# Chú thích tối đa 10 dòng; quá thì tràn sang cụm cột kế bên, không kéo dài xuống dưới.
MAX_LEGEND_ROWS = 10

# Chữ "Chú thích" — hằng số thuần, KHÔNG bọc `_()`: đây là site tiếng Việt, chuỗi nguồn đã là bản
# hiển thị, và bọc `_()` ở module level sẽ đóng băng bản dịch ngay lúc import.
LEGEND_LABEL = "Chú thích"

# Bề rộng (tính bằng ký tự) dành cho phần nghĩa của ký hiệu — đủ cho nhãn dài nhất trong
# `Attendance Code` ("Ngày nghỉ / ngoài thời gian làm việc").
LEGEND_MEANING_CHARS = 34

# Hai cột đầu (Mã NV, Nhân viên) rộng và mang dữ liệu văn bản; khối chú thích bắt đầu từ cột ngày
# thứ nhất vì cột ngày hẹp, vừa đúng một ô ký hiệu.
FIRST_DAY_COLUMN = 3

HEADER_BG = "E9EDF2"
HEADER_FG = "1F272E"
GRID_LINE = "D1D8DD"

THIN = Side(style="thin", color=GRID_LINE)
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
CENTER = Alignment(horizontal="center", vertical="center")
LEFT = Alignment(horizontal="left", vertical="center")
# Nhãn cột tổng hợp dài hơn ô chứa nó ("Tai nạn lao động", "Số buổi ăn trưa"). Xuống dòng trong ô
# thay vì nới cột: nới ra thì cả bảng bị co nhỏ khi in vừa một trang ngang.
HEADER_ALIGN = Alignment(horizontal="center", vertical="center", wrap_text=True)
HEADER_HEIGHT = 34  # đủ hai dòng chữ ở cỡ mặc định

# Bề rộng tối thiểu của cột không phải cột ngày, để nhãn xuống dòng chứ không bị cắt cụt.
MIN_TEXT_WIDTH = 11.0

# Bề rộng cột ngày: vừa đủ mã dài nhất (`1/2P`), giữ cả tháng lọt một trang ngang khi in.
DAY_WIDTH = 5.0


def legend_layout(count: int, max_rows: int = MAX_LEGEND_ROWS) -> tuple[int, int]:
	"""(số cụm cột, số dòng) để xếp `count` ký hiệu mà không vượt `max_rows` dòng.

	Chia đều cho các cụm chứ không nhồi đầy cụm đầu rồi bỏ cụm cuối lơ thơ: 21 mã ra 3 cụm x 7
	dòng, không phải 10 + 10 + 1."""
	if count <= 0:
		return 0, 0
	groups = ceil(count / max_rows)
	return groups, ceil(count / groups)


def excel_width(px, minimum: float = 4.0) -> float:
	"""Đổi bề rộng cột của datatable (px) sang đơn vị ký tự của Excel."""
	return max(minimum, round(cint(px or 100) / 8.0, 1))


def fill_for(state: str) -> tuple[PatternFill, Font] | tuple[None, None]:
	"""(nền, chữ) của một state màu — dùng chung cặp màu nền sáng với report và bản in."""
	style = STATE_STYLE.get(state or "")
	if not style:
		return None, None
	return (
		PatternFill("solid", start_color="FF" + style["bg"].lstrip("#").upper()),
		Font(bold=True, color="FF" + style["fg"].lstrip("#").upper()),
	)


def report_title(filters: dict) -> str:
	month, year = cint(filters.get("month")), cint(filters.get("year"))
	return _("BẢNG CHẤM CÔNG THÁNG {0}/{1}").format(month, year)


def build_workbook(columns: list[dict], data: list[dict], filters: dict | None = None) -> Workbook:
	"""Dựng workbook đã tô màu từ đúng `columns`/`data` mà `execute()` của report trả về."""
	filters = frappe._dict(filters or {})
	rows = [r for r in data if r and r.get("employee")]

	wb = Workbook()
	ws = wb.active
	ws.title = _("Chấm công")

	last_col = len(columns)
	write_titles(ws, filters, last_col)
	header_row = 3
	first_data_row = write_header(ws, columns, header_row, filters)
	end_row = write_rows(ws, columns, rows, first_data_row)
	set_widths(ws, columns)

	# đóng băng dưới tiêu đề, bên phải cột tên: cuộn kiểu gì cũng còn biết đang xem ai, ngày nào
	ws.freeze_panes = f"{get_column_letter(FIRST_DAY_COLUMN)}{first_data_row}"

	write_legend(ws, columns, end_row + 2)
	setup_print(ws, header_row, first_data_row - 1, last_col)
	return wb


def write_titles(ws, filters: dict, last_col: int) -> None:
	ws.cell(1, 1, report_title(filters)).font = Font(bold=True, size=14)
	ws.cell(1, 1).alignment = CENTER
	ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=last_col)
	ws.row_dimensions[1].height = 24

	# dòng 2 luôn tồn tại (giữ tiêu đề ở dòng 3 cố định), chỉ điền khi có lọc công ty
	if filters.get("company"):
		ws.cell(2, 1, filters.company).font = Font(bold=True, size=11, color="FF6B7280")
		ws.cell(2, 1).alignment = CENTER
		ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=last_col)


def write_header(ws, columns: list[dict], row: int, filters: dict) -> int:
	"""Tiêu đề HAI dòng: dòng trên là ngày (cột ngày) hoặc nhãn cột, dòng dưới là thứ trong tuần.

	Trên màn hình datatable chỉ có một dòng tiêu đề nên ngày và thứ phải dồn chung một nhãn
	("1 T2"). Excel thì tách được, và tách ra mới đúng lối bảng chấm công VN: hàng số ngày, ngay
	dưới là hàng thứ. Cột không phải cột ngày gộp dọc qua cả hai dòng.

	Trả về dòng dữ liệu đầu tiên."""
	fill = PatternFill("solid", start_color="FF" + HEADER_BG)
	font = Font(bold=True, color="FF" + HEADER_FG)
	weekday_row = row + 1
	year, month = cint(filters.get("year")), cint(filters.get("month"))

	for i, col in enumerate(columns, start=1):
		fieldname = col.get("fieldname") or ""
		day = day_number(fieldname)
		top = ws.cell(row, i, day if day else (col.get("label") or fieldname))
		bottom = ws.cell(weekday_row, i, weekday_label(year, month, day) if day else None)

		for cell in (top, bottom):
			cell.fill, cell.font, cell.alignment, cell.border = fill, font, HEADER_ALIGN, BORDER
		if not day:  # nhãn cột thường: gộp dọc để chữ nằm giữa hai dòng tiêu đề
			ws.merge_cells(start_row=row, start_column=i, end_row=weekday_row, end_column=i)

	ws.row_dimensions[row].height = HEADER_HEIGHT
	ws.row_dimensions[weekday_row].height = 18
	return weekday_row + 1


def day_number(fieldname: str) -> int | None:
	"""Số ngày trong tháng của một cột `day_<N>`; None nếu không phải cột ngày."""
	return cint(fieldname[4:]) if fieldname.startswith("day_") else None


def write_rows(ws, columns: list[dict], rows: list[dict], start_row: int) -> int:
	"""Ghi dữ liệu, trả về dòng cuối đã ghi (hoặc dòng ngay trước đó nếu bảng rỗng)."""
	for offset, data_row in enumerate(rows):
		write_row(ws, columns, data_row, start_row + offset)
	return start_row + len(rows) - 1


def write_row(ws, columns: list[dict], data_row: dict, row: int) -> None:
	"""Một dòng nhân viên: ô ngày tô theo `_state_<day>`, cột Tổng công in đậm."""
	for i, col in enumerate(columns, start=1):
		fieldname = col.get("fieldname")
		cell = ws.cell(row, i, cell_value(data_row, col))
		cell.border = BORDER

		if fieldname.startswith("day_"):
			cell.alignment = CENTER
			fill, font = fill_for(data_row.get(f"_state_{fieldname[4:]}"))
			if fill:
				cell.fill, cell.font = fill, font
		elif col.get("fieldtype") in ("Float", "Int"):
			cell.alignment = CENTER
			# cột chủ đạo — in đậm y như trên màn hình
			cell.font = Font(bold=True) if fieldname == "tong_cong" else Font()
		else:
			cell.alignment = LEFT


def cell_value(row: dict, col: dict):
	value = row.get(col.get("fieldname"))
	fieldtype = col.get("fieldtype")
	if fieldtype == "Float":
		return flt(value)
	if fieldtype == "Int":
		return cint(value)
	return value or ""


def set_widths(ws, columns: list[dict]) -> None:
	"""Cột ngày hẹp cố định; cột còn lại theo lưới, có sàn để nhãn xuống dòng được.

	Không suy bề rộng cột ngày từ `width` của report: trên màn hình cột đó phải nới ra cho vừa
	nhãn gộp "1 T2", còn ở đây thứ đã nằm ở dòng tiêu đề riêng nên ô chỉ cần chứa mã công."""
	for i, col in enumerate(columns, start=1):
		if day_number(col.get("fieldname") or ""):
			width = DAY_WIDTH
		else:
			width = max(excel_width(col.get("width")), MIN_TEXT_WIDTH)
		ws.column_dimensions[get_column_letter(i)].width = width


def legend_span(ws, total_cols: int, groups: int) -> int:
	"""Số cột ngày gộp lại cho ô nghĩa: đủ rộng để đọc, nhưng vẫn để mọi cụm nằm trong bảng."""
	day_width = ws.column_dimensions[get_column_letter(FIRST_DAY_COLUMN)].width or 5.0
	desired = max(3, ceil(LEGEND_MEANING_CHARS / day_width))
	room = (total_cols - FIRST_DAY_COLUMN + 1) // max(groups, 1) - 1
	return max(3, min(desired, room))


def write_legend(ws, columns: list[dict], top: int) -> None:
	"""Khối chú thích dạng lưới: `Chú thích` một ô, mỗi ký hiệu một ô (tô đúng màu của nó), nghĩa
	ở ô ngang hàng ngay bên phải. Tối đa `MAX_LEGEND_ROWS` dòng — quá thì sang cụm cột kế tiếp."""
	pairs = legend_pairs()
	if not pairs:
		return

	groups, rows = legend_layout(len(pairs))
	span = legend_span(ws, len(columns), groups)
	code_map = get_code_map()

	label = ws.cell(top, 1, LEGEND_LABEL)  # đúng MỘT ô, không gộp
	label.font = Font(bold=True)
	label.alignment = LEFT

	for index, (code, name) in enumerate(pairs):
		group, offset = divmod(index, rows)  # điền theo cột: đầy cụm này mới sang cụm kế
		row = top + offset
		col = FIRST_DAY_COLUMN + group * (span + 1)

		symbol = ws.cell(row, col, code)
		symbol.alignment, symbol.border = CENTER, BORDER
		fill, font = fill_for(day_state(code, code_map))
		symbol.font = font or Font(bold=True)
		if fill:
			symbol.fill = fill

		meaning = ws.cell(row, col + 1, name)
		meaning.alignment = LEFT
		ws.merge_cells(start_row=row, start_column=col + 1, end_row=row, end_column=col + span)


def setup_print(ws, header_row: int, weekday_row: int, last_col: int) -> None:
	"""In ngang, co vừa một trang ngang, lặp cả hai dòng tiêu đề ở mọi trang."""
	ws.page_setup.orientation = "landscape"
	ws.page_setup.fitToWidth = 1
	ws.page_setup.fitToHeight = 0
	ws.sheet_properties.pageSetUpPr.fitToPage = True
	ws.print_title_rows = f"{header_row}:{weekday_row}"
	ws.print_area = f"A1:{get_column_letter(last_col)}{ws.max_row}"


@frappe.whitelist()
def download(filters=None, visible_idx=None):
	"""Endpoint của nút Export (Excel có màu) trên `Monthly Attendance Report`."""
	from frappe.desk.utils import provide_binary_file

	# đúng thứ `export_query` kiểm — `ref_doctype` của báo cáo là Attendance
	frappe.permissions.can_export("Attendance", raise_exception=True)

	filters = frappe.parse_json(filters) or {}
	columns, data, _message = execute(filters)

	# lọc theo dòng đang hiện trên màn hình TRƯỚC khi bỏ dòng chú thích cũ: chỉ số client gửi lên
	# đánh trên `data` gốc, bỏ dòng trước thì lệch hết.
	visible = frappe.parse_json(visible_idx) if visible_idx else None
	if visible:
		keep = set(visible)
		data = [row for i, row in enumerate(data) if i in keep]

	stream = BytesIO()
	build_workbook(columns, data, filters).save(stream)

	filters = frappe._dict(filters)
	name = f"Bang cham cong {cint(filters.month):02d}-{cint(filters.year)}"
	provide_binary_file(name, "xlsx", stream.getvalue())
