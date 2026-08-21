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
from frappe.utils import cint, flt, getdate, nowdate

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

# Chữ "Chú thích" nằm ở cột Nhân viên, không phải cột STT: cột STT hẹp, chữ tràn ra ngoài trông
# như dữ liệu lạc dòng.
LEGEND_LABEL_COLUMN = 2

# Bề rộng (tính bằng ký tự) dành cho phần nghĩa của ký hiệu — đủ cho nhãn dài nhất trong
# `Attendance Code` ("Ngày nghỉ / ngoài thời gian làm việc").
LEGEND_MEANING_CHARS = 34

# Hai cột đầu (STT, Nhân viên) mang dữ liệu văn bản; khối chú thích bắt đầu từ cột ngày thứ nhất
# vì cột ngày hẹp, vừa đúng một ô ký hiệu.
FIRST_DAY_COLUMN = 3

# Bảng bắt đầu sau khối tiêu đề thư (6 dòng chữ + 1 dòng trống). Tiêu đề bảng chiếm hai dòng
# (số ngày, rồi thứ), nên dữ liệu bắt đầu ngay dưới.
HEADER_ROW = 8
WEEKDAY_ROW = HEADER_ROW + 1
FIRST_DATA_ROW = WEEKDAY_ROW + 1

# Cột STT thay cột "Mã NV" của báo cáo: bản in cần số thứ tự, mã hệ thống (HR-EMP-00001) chỉ tốn
# chỗ. Không đổi `columns` của report vì trên màn hình cột Mã NV là liên kết bấm sang hồ sơ.
STT_COLUMN = {"fieldname": "stt", "label": "STT", "fieldtype": "Int", "width": 44}

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

PLAIN_FONT = Font()
# Cột số nào cần khác thường: Tổng công là cột chủ đạo nên in đậm; STT chỉ để đánh dòng nên làm mờ
# đi, không tranh mắt với số liệu.
NUMBER_FONTS = {"tong_cong": Font(bold=True), "stt": Font(color="FF6B7280")}

# Bề rộng tối thiểu của cột không phải cột ngày, để nhãn xuống dòng chứ không bị cắt cụt.
MIN_TEXT_WIDTH = 11.0

# Bề rộng cột ngày: vừa đủ mã dài nhất (`1/2P`), giữ cả tháng lọt một trang ngang khi in.
DAY_WIDTH = 5.0

# Tiêu đề thư của Miyano. Deployment này chỉ có MỘT pháp nhân (xem CLAUDE.md), và không dòng nào
# trong ba dòng dưới đây có sẵn trong master data: `Company.company_name` là tên gọi tắt "Miyano",
# `tax_id` để trống, site chưa có Address nào. Để đây thay vì sửa `company_name` vì đổi tên đó là
# đổi tên công ty trên MỌI chứng từ ERPNext, không chỉ bảng chấm công. `company_lines()` vẫn ưu
# tiên master data khi có, nên điền `tax_id` / tạo Address là hết dùng tới mặc định này.
MIYANO_LETTERHEAD = {
	"name": "CÔNG TY TNHH MIYANO VIỆT NAM",
	"tax_id": "0109529507",
	"address": ("số 20, Khu C17, ngõ 264/63, đường Ngọc Thụy, Phường Bồ Đề, Thành phố Hà Nội, Việt Nam"),
	# địa danh mở đầu dòng ngày tháng của khối trình ký ("Hà Nội, ngày 02 tháng 7 năm 2026")
	"city": "Hà Nội",
}

# Khối trình ký cuối bảng — bản Excel gốc của Miyano (`docs/2. Bang_Cham_Cong_06-2026_final.xlsx`)
# xếp cả hai chữ ký ở NỬA PHẢI: người duyệt sát mép phải, người lập lùi vào giữa.
SIGN_PREPARED_LABEL = "Người lập"
SIGN_APPROVED_LABEL = "Người duyệt"

# Bề ngang mỗi khối ký, tính bằng cột ngày (bản gốc gộp 10 cột: AF..AO). Bảng hẹp thì co lại.
SIGN_BLOCK_WIDTH = 10

# Số dòng từ chức danh xuống dòng tên — chỗ trống để ký tay (bản gốc: dòng 28 → dòng 34).
SIGN_NAME_GAP = 6


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


def report_period(filters: dict) -> str:
	"""Dòng kỳ công dưới tên bảng: `Tháng 06 Năm 2026`."""
	return _("Tháng {0} Năm {1}").format(f"{cint(filters.get('month')):02d}", cint(filters.get("year")))


def company_lines(company: str | None) -> list[str]:
	"""Ba dòng tiêu đề thư: tên pháp nhân, MST, địa chỉ. Bỏ qua dòng nào không có dữ liệu.

	Master data thắng ở đâu có: `Company.tax_id` cho MST, Address chính liên kết với Company cho
	địa chỉ. Site hiện chưa có cả hai (2026-08-03: `tax_id` trống, không Address nào) và
	`Company.company_name` là tên gọi tắt "Miyano" chứ không phải tên pháp nhân trên giấy tờ, nên
	`MIYANO_LETTERHEAD` đứng làm mặc định — điền vào Company/Address là dữ liệu thắng ngay, không
	phải sửa code."""
	tax_id = frappe.db.get_value("Company", company, "tax_id") if company else None
	lines = [MIYANO_LETTERHEAD["name"]]
	if tax_id or MIYANO_LETTERHEAD["tax_id"]:
		lines.append(_("MST: {0}").format(tax_id or MIYANO_LETTERHEAD["tax_id"]))
	address = company_address(company) or MIYANO_LETTERHEAD["address"]
	if address:
		lines.append(_("Địa chỉ: {0}").format(address))
	return lines


def company_address_row(company: str | None) -> frappe._dict | None:
	"""Address chính liên kết với Company; None nếu chưa có Address nào."""
	if not company:
		return None
	names = frappe.get_all(
		"Dynamic Link",
		filters={"link_doctype": "Company", "link_name": company, "parenttype": "Address"},
		pluck="parent",
	)
	if not names:
		return None
	addresses = frappe.get_all(
		"Address",
		filters={"name": ["in", names]},
		fields=["address_line1", "address_line2", "city", "state", "country", "is_primary_address"],
		order_by="is_primary_address desc",
		limit=1,
	)
	return addresses[0] if addresses else None


def company_address(company: str | None) -> str | None:
	"""Địa chỉ chính của Company gộp thành một dòng; None nếu chưa có Address nào liên kết."""
	a = company_address_row(company)
	if not a:
		return None
	return ", ".join(p for p in (a.address_line1, a.address_line2, a.city, a.state, a.country) if p)


def company_city(company: str | None) -> str | None:
	"""Địa danh đứng đầu dòng ngày tháng — lấy `city` của Address chính khi có."""
	a = company_address_row(company)
	return (a.city or None) if a else None


def build_workbook(
	columns: list[dict],
	data: list[dict],
	filters: dict | None = None,
	signatures: dict | None = None,
) -> Workbook:
	"""Dựng workbook đã tô màu từ đúng `columns`/`data` mà `execute()` của report trả về.

	`signatures` là hai cái tên trên khối trình ký (`prepared_by` / `approved_by`) — người xuất
	file điền ở hộp thoại Export; để trống thì chỉ in chức danh, ký tên bằng tay."""
	filters = frappe._dict(filters or {})
	rows = [r for r in data if r and r.get("employee")]
	columns = excel_columns(columns)

	wb = Workbook()
	ws = wb.active
	ws.title = _("Chấm công")

	last_col = len(columns)
	write_titles(ws, filters, last_col)
	write_header(ws, columns, filters)
	end_row = write_rows(ws, columns, rows, FIRST_DATA_ROW)
	set_widths(ws, columns)

	# đóng băng dưới tiêu đề, bên phải cột tên: cuộn kiểu gì cũng còn biết đang xem ai, ngày nào
	ws.freeze_panes = f"{get_column_letter(FIRST_DAY_COLUMN)}{FIRST_DATA_ROW}"

	legend_end = write_legend(ws, columns, end_row + 2)
	write_signatures(ws, last_col, legend_end + 2, signatures, filters.get("company"))
	setup_print(ws, last_col)
	return wb


def excel_columns(columns: list[dict]) -> list[dict]:
	"""Cột của file: thay "Mã NV" bằng STT, giữ nguyên phần còn lại của báo cáo."""
	return [STT_COLUMN if c.get("fieldname") == "employee" else c for c in columns]


def write_titles(ws, filters: dict, last_col: int) -> None:
	"""Tiêu đề thư: khối pháp nhân căn TRÁI, rồi tên bảng + kỳ công căn GIỮA.

	Mỗi dòng gộp hết bề ngang bảng để khi in không bị cắt ở mép cột."""
	for row, text in enumerate(company_lines(filters.get("company")), start=1):
		cell = ws.cell(row, 1, text)
		cell.font = Font(bold=(row == 1), size=11)
		cell.alignment = LEFT
		ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=last_col)

	# neo theo `HEADER_ROW` chứ không theo số dòng pháp nhân vừa ghi: thiếu MST hay địa chỉ thì
	# khối trên ngắn lại, nhưng bảng vẫn phải bắt đầu đúng chỗ mọi nơi khác trong module trông đợi.
	title_row = HEADER_ROW - 3  # tên bảng, kỳ công, rồi một dòng trống trước tiêu đề bảng
	for offset, (text, font) in enumerate(
		((_("BẢNG CHẤM CÔNG"), Font(bold=True, size=16)), (report_period(filters), Font(size=12)))
	):
		cell = ws.cell(title_row + offset, 1, text)
		cell.font, cell.alignment = font, CENTER
		ws.merge_cells(
			start_row=title_row + offset, start_column=1, end_row=title_row + offset, end_column=last_col
		)
	ws.row_dimensions[title_row].height = 26


def write_header(ws, columns: list[dict], filters: dict) -> None:
	"""Tiêu đề HAI dòng: dòng trên là ngày (cột ngày) hoặc nhãn cột, dòng dưới là thứ trong tuần.

	Trên màn hình datatable chỉ có một dòng tiêu đề nên ngày và thứ phải dồn chung một nhãn
	("1 T2"). Excel thì tách được, và tách ra mới đúng lối bảng chấm công VN: hàng số ngày, ngay
	dưới là hàng thứ. Cột không phải cột ngày gộp dọc qua cả hai dòng."""
	fill = PatternFill("solid", start_color="FF" + HEADER_BG)
	font = Font(bold=True, color="FF" + HEADER_FG)
	year, month = cint(filters.get("year")), cint(filters.get("month"))

	for i, col in enumerate(columns, start=1):
		fieldname = col.get("fieldname") or ""
		day = day_number(fieldname)
		top = ws.cell(HEADER_ROW, i, day if day else (col.get("label") or fieldname))
		bottom = ws.cell(WEEKDAY_ROW, i, weekday_label(year, month, day) if day else None)

		for cell in (top, bottom):
			cell.fill, cell.font, cell.alignment, cell.border = fill, font, HEADER_ALIGN, BORDER
		if not day:  # nhãn cột thường: gộp dọc để chữ nằm giữa hai dòng tiêu đề
			ws.merge_cells(start_row=HEADER_ROW, start_column=i, end_row=WEEKDAY_ROW, end_column=i)

	ws.row_dimensions[HEADER_ROW].height = HEADER_HEIGHT
	ws.row_dimensions[WEEKDAY_ROW].height = 18


def day_number(fieldname: str) -> int | None:
	"""Số ngày trong tháng của một cột `day_<N>`; None nếu không phải cột ngày."""
	return cint(fieldname[4:]) if fieldname.startswith("day_") else None


def write_rows(ws, columns: list[dict], rows: list[dict], start_row: int) -> int:
	"""Ghi dữ liệu, trả về dòng cuối đã ghi (hoặc dòng ngay trước đó nếu bảng rỗng)."""
	for offset, data_row in enumerate(rows):
		write_row(ws, columns, data_row, start_row + offset, stt=offset + 1)
	return start_row + len(rows) - 1


def write_row(ws, columns: list[dict], data_row: dict, row: int, stt: int) -> None:
	"""Một dòng nhân viên: ô ngày tô theo `_state_<day>`, cột Tổng công in đậm."""
	for i, col in enumerate(columns, start=1):
		fieldname = col.get("fieldname")
		cell = ws.cell(row, i, stt if fieldname == "stt" else cell_value(data_row, col))
		cell.border = BORDER

		if fieldname.startswith("day_"):
			cell.alignment = CENTER
			fill, font = fill_for(data_row.get(f"_state_{fieldname[4:]}"))
			if fill:
				cell.fill, cell.font = fill, font
		elif col.get("fieldtype") in ("Float", "Int") or col.get("align") == "center":
			# `align` để cột chữ nhưng đọc như số (TB giờ/ngày dạng hh:mm) không bị dạt trái
			cell.alignment = CENTER
			cell.font = NUMBER_FONTS.get(fieldname, PLAIN_FONT)
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
			# sàn chỉ nới tới mức nhãn cần: "STT" không việc gì phải rộng bằng "Ốm / chăm con ốm"
			label = str(col.get("label") or "")
			width = max(excel_width(col.get("width")), min(len(label) + 2, MIN_TEXT_WIDTH))
		ws.column_dimensions[get_column_letter(i)].width = width


def legend_span(ws, total_cols: int, groups: int) -> int:
	"""Số cột ngày gộp lại cho ô nghĩa: đủ rộng để đọc, nhưng vẫn để mọi cụm nằm trong bảng."""
	day_width = ws.column_dimensions[get_column_letter(FIRST_DAY_COLUMN)].width or 5.0
	desired = max(3, ceil(LEGEND_MEANING_CHARS / day_width))
	room = (total_cols - FIRST_DAY_COLUMN + 1) // max(groups, 1) - 1
	return max(3, min(desired, room))


def write_legend(ws, columns: list[dict], top: int) -> int:
	"""Khối chú thích dạng lưới: `Chú thích` một ô, mỗi ký hiệu một ô (tô đúng màu của nó), nghĩa
	ở ô ngang hàng ngay bên phải. Tối đa `MAX_LEGEND_ROWS` dòng — quá thì sang cụm cột kế tiếp.

	Trả về dòng cuối đã dùng (hoặc `top - 1` nếu không có ký hiệu nào) để khối trình ký biết
	đặt xuống đâu."""
	pairs = legend_pairs()
	if not pairs:
		return top - 1

	groups, rows = legend_layout(len(pairs))
	span = legend_span(ws, len(columns), groups)
	code_map = get_code_map()

	label = ws.cell(top, LEGEND_LABEL_COLUMN, LEGEND_LABEL)  # đúng MỘT ô, không gộp
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

	return top + rows - 1


def sign_blocks(last_col: int) -> tuple[tuple[int, int], tuple[int, int]]:
	"""(cột đầu, cột cuối) của khối "Người lập" và khối "Người duyệt".

	Cả hai nằm ở nửa phải bảng như biểu mẫu gốc: người duyệt sát mép phải, người lập lùi vào giữa,
	giữa hai khối chừa một quãng trống. Bảng ít cột thì khối co lại chứ không tràn sang cột tên."""
	room = max(last_col - FIRST_DAY_COLUMN + 1, 2)
	# 2 khối + ít nhất 1 cột ngăn cách phải lọt trong `room`
	width = max(1, min(SIGN_BLOCK_WIDTH, (room - 1) // 2))
	approved = (last_col - width + 1, last_col)
	start = max(FIRST_DAY_COLUMN, approved[0] - width - max(1, width // 2))
	return (start, start + width - 1), approved


def signature_date_line(company: str | None) -> str:
	"""Dòng trên chữ ký người duyệt: `Hà Nội, ngày 02 tháng 7 năm 2026`.

	Ngày là ngày xuất file (ngày trình ký), địa danh lấy `city` của Address công ty khi có."""
	today = getdate(nowdate())
	city = company_city(company) or MIYANO_LETTERHEAD["city"]
	return _("{0}, ngày {1} tháng {2} năm {3}").format(city, f"{today.day:02d}", today.month, today.year)


def signature_names(signatures: dict | None) -> tuple[str, str]:
	"""Tên dưới hai chữ ký. Người lập bỏ trống thì lấy người đang xuất file; người duyệt thì không
	đoán — ai duyệt là việc của người trình ký, để trống cho ký tay."""
	signatures = frappe._dict(signatures or {})
	prepared = (signatures.prepared_by or "").strip() or session_signer_name()
	return prepared, (signatures.approved_by or "").strip()


def session_signer_name() -> str:
	"""Tên người đang đăng nhập, theo hồ sơ nhân viên rồi mới tới tên User.

	`Administrator` / `Guest` là tài khoản hệ thống — in mấy chữ đó lên bản trình ký thì vô nghĩa,
	thà để trống ô tên cho người ký điền tay."""
	user = frappe.session.user
	if not user or user in ("Guest", "Administrator"):
		return ""
	return (
		frappe.db.get_value("Employee", {"user_id": user, "status": "Active"}, "employee_name")
		or frappe.db.get_value("User", user, "full_name")
		or ""
	)


def write_signatures(ws, last_col: int, top: int, signatures: dict | None, company: str | None) -> None:
	"""Khối trình ký cuối bảng: dòng địa danh + ngày, hai chức danh, chừa chỗ ký rồi tới tên.

	Không kẻ khung: đây là chỗ ký tay trên bản in, kẻ ô vào chỉ vướng chữ ký."""
	prepared_block, approved_block = sign_blocks(last_col)
	prepared_name, approved_name = signature_names(signatures)

	date_cell = ws.cell(top, approved_block[0], signature_date_line(company))
	date_cell.font, date_cell.alignment = Font(italic=True), CENTER
	merge_across(ws, top, approved_block)

	name_row = top + 1 + SIGN_NAME_GAP
	for block, label, name in (
		(prepared_block, SIGN_PREPARED_LABEL, prepared_name),
		(approved_block, SIGN_APPROVED_LABEL, approved_name),
	):
		title = ws.cell(top + 1, block[0], label)
		title.font, title.alignment = Font(bold=True), CENTER
		merge_across(ws, top + 1, block)

		signer = ws.cell(name_row, block[0], name or None)
		signer.alignment = CENTER
		merge_across(ws, name_row, block)


def merge_across(ws, row: int, block: tuple[int, int]) -> None:
	"""Gộp một dòng qua cả khối cột — bỏ qua khối rộng đúng một cột (openpyxl không nhận)."""
	if block[1] > block[0]:
		ws.merge_cells(start_row=row, start_column=block[0], end_row=row, end_column=block[1])


def setup_print(ws, last_col: int) -> None:
	"""In ngang, co vừa một trang ngang, lặp cả hai dòng tiêu đề bảng ở mọi trang."""
	ws.page_setup.orientation = "landscape"
	ws.page_setup.fitToWidth = 1
	ws.page_setup.fitToHeight = 0
	ws.sheet_properties.pageSetUpPr.fitToPage = True
	ws.print_title_rows = f"{HEADER_ROW}:{WEEKDAY_ROW}"
	ws.print_area = f"A1:{get_column_letter(last_col)}{ws.max_row}"


@frappe.whitelist()
def download(filters=None, visible_idx=None, prepared_by=None, approved_by=None):
	"""Endpoint của nút Export (Excel có màu) trên `Monthly Attendance Report`."""
	from frappe.desk.utils import provide_binary_file

	# đúng thứ `export_query` kiểm — `ref_doctype` của báo cáo là Attendance
	frappe.permissions.can_export("Attendance", raise_exception=True)

	filters = frappe.parse_json(filters) or {}
	# Endpoint này chỉ phục vụ Bảng chấm công tháng. Nói thẳng ra khi bị gọi nhầm: `execute()` sẽ
	# ném "Please select month and year", đọc một mình không lần ra được là nút Export của báo cáo
	# NÀO gọi sai (đã mất công lần một lần, 2026-08-03).
	if not (cint(filters.get("month")) and cint(filters.get("year"))):
		frappe.throw(_("Thiếu tháng/năm: đường xuất Excel này chỉ dùng cho báo cáo Bảng chấm công tháng."))
	columns, data, _message = execute(filters)

	# lọc theo dòng đang hiện trên màn hình TRƯỚC khi bỏ dòng chú thích cũ: chỉ số client gửi lên
	# đánh trên `data` gốc, bỏ dòng trước thì lệch hết.
	visible = frappe.parse_json(visible_idx) if visible_idx else None
	if visible:
		keep = set(visible)
		data = [row for i, row in enumerate(data) if i in keep]

	stream = BytesIO()
	signatures = {"prepared_by": prepared_by, "approved_by": approved_by}
	build_workbook(columns, data, filters, signatures).save(stream)

	filters = frappe._dict(filters)
	name = f"Bang cham cong {cint(filters.month):02d}-{cint(filters.year)}"
	provide_binary_file(name, "xlsx", stream.getvalue())
