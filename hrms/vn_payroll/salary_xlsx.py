# Copyright (c) 2026, Miyano Việt Nam.
"""Xuất bảng lương tháng ra Excel theo ĐÚNG mẫu `docs/Salary_template_clean.xlsx` (09/2026).

Nút Export mặc định của query report đi qua `frappe.desk.query_report.export_query`: nó đổ thẳng
`columns` + `result` qua `make_xlsx()`, ra một lưới trần không tiêu đề công ty, không dòng tổng in
đậm, không chỗ ký. Bảng lương thì phải KÝ được — đó là chứng từ trình giám đốc, không phải bản kết
xuất dữ liệu. Module này là đường xuất riêng của báo cáo `MVL Salary Register`, dựng workbook bằng
openpyxl nên kiểm soát được từng ô.

Bố cục bám mẫu tới từng ô: tab `Salary MM.YYYY`; dòng 1-3 pháp nhân (gộp A:U); dòng 5 tên bảng,
dòng 6 `Từ ngày … Đến ngày …` (gộp A:Z); dòng 7 công chuẩn (E7:G7 → H7) + hằng số giảm trừ người
phụ thuộc (Q7) và ba tỷ lệ BH công ty / BH NLĐ / KPCĐ (V7/W7/X7); dòng 8 tiêu đề A-Z; dữ liệu từ
dòng 9; dòng TỔNG CỘNG là SỐ đã cộng (không `=SUM()` — xem `write_total_row`); khối ký người lập ở I:J, người duyệt ở R:T. Times New
Roman 13, viền mảnh đen, định dạng kế toán. Thêm tab `Ăn trưa MM.YYYY` như mẫu.

Khác mẫu CÓ CHỦ Ý — ô số của từng nhân viên là GIÁ TRỊ lấy từ phiếu lương, không phải công thức.
Công thức của mẫu chỉ đúng cho nhân viên chính thức/thử việc trọn tháng; bán thời gian (10%/20%),
chuyên gia, khoán, chuyển thử việc giữa kỳ đều tính khác, viết công thức thì tờ giấy trình ký sẽ ra
số khác số thật đã trả. Phiếu lương là chứng từ gốc, file chỉ chép lại.

Hai đường ra:

- `build_workbook(columns, data, filters, signatures, config)` — thuần hàm, không đụng HTTP, để test soi ô.
- `download(...)` — endpoint cho nút Export trên report.

CHỈ ĐỌC: không đụng Salary Slip, không tính lại đồng nào. Lương bất biến theo định nghĩa.
"""

from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

import frappe
from frappe import _
from frappe.utils import cint, get_first_day, get_last_day, getdate

from hrms.miyano_xlsx import (
	SIGN_APPROVED_LABEL,
	SIGN_PREPARED_LABEL,
	company_lines,
	signature_date_line,
	signature_names,
)
from hrms.payroll.report.mvl_salary_register.mvl_salary_register import TOTAL_LABEL, execute
from hrms.vn_payroll.mvl import MVLConfig, default_config

SHEET_TITLE = "BẢNG LƯƠNG"  # mẫu 09/2026 ô A5

# Mẫu: tiêu đề bảng ở dòng 8, dữ liệu từ dòng 9. Neo bằng hằng số chứ không đếm theo số dòng pháp
# nhân thực ghi: thiếu MST hay địa chỉ thì khối trên ngắn lại, bảng vẫn phải bắt đầu đúng chỗ.
TITLE_ROW = 5
PERIOD_ROW = 6
CONSTANTS_ROW = 7
HEADER_ROW = 8
FIRST_DATA_ROW = HEADER_ROW + 1

# Cột STT thay cột "Mã NV" của báo cáo: bản in cần số thứ tự, mã hệ thống (HR-EMP-00001) chỉ tốn
# chỗ. Không đổi `columns` của report vì trên màn hình cột Mã NV là liên kết bấm sang hồ sơ.
STT_COLUMN = {"fieldname": "stt", "label": "STT", "fieldtype": "Int", "width": 44}

# Nhãn trên file khác nhãn màn hình — mẫu V8 ghi hai dòng; xuống dòng trong nhãn lưới thì xấu.
EXCEL_LABELS = {"ins_company_r": "Bảo hiểm công ty trả\nEmployer"}

# ---- kiểu chữ & định dạng số của mẫu
FONT_NAME = "Times New Roman"
FONT_SIZE = 13
# định dạng kế toán của mẫu (cột F…Z): số 0 hiện "-", số âm trong ngoặc
MONEY_FORMAT = "_(* #,##0_);_(* \\(#,##0\\);_(* \\-??_);_(@_)"
# riêng cột thuế U (và tiền ăn trên tab Ăn trưa) mẫu dùng định dạng kế toán có ký hiệu ₫
TAX_FORMAT = "_-* #,##0\\ _₫_-;\\-* #,##0\\ _₫_-;_-* \\-??\\ _₫_-;_-@_-"
INTEGER_FORMAT = "#,##0_);\\(#,##0\\)"  # dòng tổng + số buổi ăn
RATE_FORMAT = "0.0%"
# Số công / hệ số để General: mẫu dùng `#,##0` cho cột H vì toàn ngày chẵn, nhưng phiếu thật có
# nửa ngày — `#,##0` sẽ in 19.5 thành "20". Hệ số 0.85 mẫu cũng để General.
GENERAL = "General"

# Dấu cảnh báo trên dòng kỳ khi bảng có lẫn phiếu chưa chốt. Không có nó thì tờ giấy trình ký
# trông y hệt bản chính thức — người duyệt ký lên những con số còn có thể đổi mà không biết.
DRAFT_WARNING = "GỒM CẢ PHIẾU NHÁP — CHƯA CHỐT"

THIN = Side(style="thin")  # mẫu: viền mảnh màu tự động (đen)
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
UNDERLINE = Border(bottom=THIN)
WHITE = PatternFill("solid", start_color="FFFFFFFF")  # mẫu tô nền trắng tiêu đề + dòng tổng

# ---- kích thước của mẫu
LETTERHEAD_LAST_COL = 21  # mẫu gộp dòng 1-3 tới cột U
ROW_HEIGHT = 16.15
TITLE_HEIGHT = 19.7
HEADER_HEIGHT = 66.75
DATA_HEIGHT = 24.75
TOTAL_HEIGHT = 30
# Bề rộng từng cột A…Z của mẫu. N và Z mẫu bỏ trống (bề rộng mặc định quá hẹp cho số tiền) →
# lấy theo cột tiền cạnh nó.
WIDTHS = {
	"A": 3.86, "B": 22.0, "C": 15.72, "D": 10.0, "E": 7.43, "F": 15.86, "G": 14.29, "H": 8.57,
	"I": 15.72, "J": 12.14, "K": 10.29, "L": 12.0, "M": 13.0, "N": 13.0, "O": 15.86, "P": 14.43,
	"Q": 12.0, "R": 15.57, "S": 13.57, "T": 14.14, "U": 13.71, "V": 14.29, "W": 13.71, "X": 12.43,
	"Y": 15.72, "Z": 15.72,
}  # fmt: skip

# Căn ngang trong ô dữ liệu theo mẫu: chữ (B, C) và nhóm cột giảm trừ/quy đổi (Q…T) để General,
# còn lại căn giữa. Dọc luôn giữa; từ cột Số công trở đi xuống dòng trong ô.
GENERAL_ALIGNED = {"employee_name", "work_type", "dependents", "deduction_n", "converted_o", "taxable_p"}
NO_WRAP = {"stt", "employee_name", "work_type", "pay_mode", "coefficient", "base_f", "bhxh_g"}
# cột không cộng ở dòng tổng (mẫu để trống E15)
NOT_SUMMED = {"coefficient"}

# Khối trình ký — mẫu: ngày ở R:T ba dòng dưới dòng tổng, chức danh dòng kế, chừa 5 dòng ký tay,
# rồi tên và chức vụ. Người lập ở I:J, người duyệt ở R:T.
PREPARED_COLS = (9, 10)  # I:J
APPROVED_COLS = (18, 20)  # R:T
SIGN_GAP_AFTER_TABLE = 3
SIGN_NAME_OFFSET = 6  # từ dòng chức danh xuống dòng tên (mẫu 19 → 25)

# ---- tab Ăn trưa
LUNCH_HEADER_ROW = 3
LUNCH_FONT_SIZE = 11
LUNCH_WIDTHS = {"A": 9.14, "B": 23.0, "C": 16.29, "D": 13.0, "E": 10.86, "F": 18.71}
LUNCH_LABELS = ("Số buổi ăn trưa", "Thành tiền", "Giữ lại", "Nộp quỹ canteen")


def font(bold: bool = False, italic: bool = False, size: int = FONT_SIZE) -> Font:
	return Font(name=FONT_NAME, size=size, bold=bold, italic=italic)


def build_workbook(
	columns: list[dict],
	data: list[dict],
	filters: dict | None = None,
	signatures: dict | None = None,
	config: MVLConfig | None = None,
) -> Workbook:
	"""Dựng workbook bảng lương từ đúng `columns`/`data` mà `execute()` của báo cáo trả về.

	`signatures`: `prepared_by` / `prepared_title` / `approved_by` / `approved_title` — người xuất
	file điền ở hộp thoại Export; để trống thì chừa chỗ ký tên tay. `config` cho các hằng số dòng 7
	và đơn giá ăn trưa (mặc định: tham số engine; `download` truyền tab Lương Miyano của Payroll Settings)."""
	filters = frappe._dict(filters or {})
	config = config or default_config()
	columns = excel_columns(columns)
	body, total = split_total_row(data)

	wb = Workbook()
	ws = wb.active
	ws.title = sheet_name(_("Salary"), filters)

	last_col = len(columns)
	write_letterhead(ws, filters, last_col)
	write_constants(ws, columns, body, config)
	write_header(ws, columns)
	end_row = write_rows(ws, columns, body, total)
	set_widths(ws, last_col)
	ws.freeze_panes = f"D{FIRST_DATA_ROW}"  # mẫu: giữ STT + Họ tên + Loại HĐ khi cuộn ngang
	ws.sheet_view.zoomScale = 70

	write_signatures(ws, end_row + SIGN_GAP_AFTER_TABLE, signatures, filters.get("company"))
	setup_print(ws, last_col)

	write_lunch_sheet(wb.create_sheet(sheet_name(_("Ăn trưa"), filters)), body, filters, config)
	return wb


# ------------------------------------------------------------------ khung


def sheet_name(prefix: str, filters: dict) -> str:
	"""Tên tab như mẫu: `Salary 09.2026`, `Ăn trưa 09.2026`."""
	return f"{prefix} {cint(filters.get('month')):02d}.{cint(filters.get('year'))}"


def period_bounds(filters: dict):
	start = get_first_day(getdate(f"{cint(filters.get('year'))}-{cint(filters.get('month')):02d}-01"))
	return start, get_last_day(start)


def period_line(filters: dict) -> str:
	"""Mẫu A6: `Từ ngày: 01/09/2026             Đến ngày: 30/09/2026`, kèm cảnh báo phiếu nháp."""
	start, end = period_bounds(filters)
	line = _("Từ ngày: {0}             Đến ngày: {1}").format(
		start.strftime("%d/%m/%Y"), end.strftime("%d/%m/%Y")
	)
	if cint(filters.get("include_drafts")):
		line = f"{line} — {_(DRAFT_WARNING)}"
	return line


def write_letterhead(ws, filters: dict, last_col: int) -> None:
	"""Dòng 1-3 pháp nhân căn trái (gộp A:U), dòng 5 tên bảng và dòng 6 kỳ căn giữa (gộp A:Z)."""
	head_end = min(LETTERHEAD_LAST_COL, last_col)
	for row, text in enumerate(company_lines(filters.get("company")), start=1):
		cell = ws.cell(row, 1, text)
		cell.font, cell.alignment = font(bold=(row == 1)), Alignment(horizontal="left", vertical="center")
		ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=head_end)
		ws.row_dimensions[row].height = ROW_HEIGHT

	for row, text, f, height in (
		(TITLE_ROW, _(SHEET_TITLE), font(bold=True, size=16), TITLE_HEIGHT),
		(PERIOD_ROW, period_line(filters), font(), ROW_HEIGHT),
	):
		cell = ws.cell(row, 1, text)
		cell.font, cell.alignment = f, Alignment(horizontal="center", vertical="center")
		ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=last_col)
		ws.row_dimensions[row].height = height


def write_constants(ws, columns: list[dict], body: list[dict], config: MVLConfig) -> None:
	"""Dòng 7 của mẫu: "Số công làm việc chuẩn:" (E7:G7) → số công chuẩn (H7); giảm trừ mỗi người
	phụ thuộc trên cột Số NPT (Q7); tỷ lệ BH công ty / BH NLĐ / KPCĐ trên đúng cột của nó (V7/W7/X7).

	Vị trí tìm theo fieldname. Công chuẩn của mọi phiếu trong kỳ là một (đặt từ lịch tuần cả kỳ);
	vẫn lấy max để không phụ thuộc thứ tự dòng. Kỳ không có phiếu thì bỏ trống ô công chuẩn."""
	fields = [c.get("fieldname") for c in columns]
	row = CONSTANTS_ROW
	ws.row_dimensions[row].height = ROW_HEIGHT

	if "coefficient" in fields and "worked_days" in fields:
		label_col, days_col = fields.index("coefficient") + 1, fields.index("worked_days") + 1
		for c in range(label_col, days_col):
			ws.cell(row, c).border = UNDERLINE
		label = ws.cell(row, label_col, _("Số công làm việc chuẩn:"))
		label.font, label.alignment = font(), Alignment(horizontal="right", vertical="center")
		if days_col - 1 > label_col:
			ws.merge_cells(start_row=row, start_column=label_col, end_row=row, end_column=days_col - 1)
		days = [r.get("standard_days") for r in body if r.get("standard_days")]
		cell = ws.cell(row, days_col, max(days) if days else None)
		cell.font, cell.number_format = font(), GENERAL
		cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

	constants = (
		("dependents", config.dependent_deduction, MONEY_FORMAT, "center", UNDERLINE),
		("ins_company_r", config.ins_company, RATE_FORMAT, None, None),
		("ins_employee_s", config.ins_employee, RATE_FORMAT, None, None),
		("union_fee", config.union_fee_rate, RATE_FORMAT, None, None),
	)
	for fieldname, value, fmt, horizontal, border in constants:
		if fieldname not in fields:
			continue
		cell = ws.cell(row, fields.index(fieldname) + 1, value)
		cell.font, cell.number_format = font(bold=True, size=12), fmt
		cell.alignment = Alignment(horizontal=horizontal, vertical="center", wrap_text=True)
		if border:
			cell.border = border


def excel_columns(columns: list[dict]) -> list[dict]:
	"""Cột của file: thay "Mã NV" bằng STT, đổi nhãn theo mẫu ở chỗ mẫu khác màn hình."""
	out = []
	for c in columns:
		if c.get("fieldname") == "employee":
			out.append(STT_COLUMN)
		elif c.get("fieldname") in EXCEL_LABELS:
			out.append(dict(c, label=EXCEL_LABELS[c["fieldname"]]))
		else:
			out.append(c)
	return out


def split_total_row(data: list[dict]) -> tuple[list[dict], dict | None]:
	"""Tách dòng TỔNG CỘNG khỏi các dòng nhân viên.

	Nhận diện bằng CHỖ THIẾU `employee`, không so chuỗi nhãn: nhãn đi qua `_()` nên đổi theo ngôn
	ngữ, còn dòng tổng thì vĩnh viễn không có mã nhân viên."""
	body = [r for r in data if r and r.get("employee")]
	totals = [r for r in data if r and not r.get("employee") and r.get("employee_name")]
	return body, (totals[-1] if totals else None)


# ------------------------------------------------------------------ lưới


def write_header(ws, columns: list[dict]) -> None:
	"""Mẫu dòng 8: chữ đậm 13, căn giữa, xuống dòng trong ô, viền mảnh, nền trắng."""
	align = Alignment(horizontal="center", vertical="center", wrap_text=True)
	for i, c in enumerate(columns, start=1):
		cell = ws.cell(HEADER_ROW, i, c.get("label") or c.get("fieldname"))
		cell.font, cell.alignment, cell.border, cell.fill = font(bold=True), align, BORDER, WHITE
	ws.row_dimensions[HEADER_ROW].height = HEADER_HEIGHT


def write_rows(ws, columns: list[dict], body: list[dict], total: dict | None) -> int:
	"""Ghi các dòng nhân viên rồi dòng TỔNG CỘNG; trả về dòng cuối đã ghi."""
	row = FIRST_DATA_ROW - 1
	for offset, data_row in enumerate(body):
		row = FIRST_DATA_ROW + offset
		write_row(ws, columns, data_row, row, stt=offset + 1)
	if total is not None and body:
		row += 1
		write_total_row(ws, columns, row, FIRST_DATA_ROW, row - 1)
	return row


def write_row(ws, columns: list[dict], data_row: dict, row: int, stt: int) -> None:
	for i, c in enumerate(columns, start=1):
		fieldname = c.get("fieldname") or ""
		value = stt if fieldname == "stt" else data_row.get(fieldname)
		cell = ws.cell(row, i, value if value != "" else None)
		cell.font, cell.border = font(), BORDER
		cell.number_format = number_format(c)
		cell.alignment = alignment_for(c)
	ws.row_dimensions[row].height = DATA_HEIGHT


def write_total_row(ws, columns: list[dict], row: int, first: int, last: int) -> None:
	"""Mẫu dòng 15: "TỔNG CỘNG" ở cột A, mỗi cột số là TỔNG của khối dữ liệu, chữ đậm.

	Ghi SỐ đã cộng chứ không `=SUM()` như mẫu: openpyxl không lưu giá trị tính sẵn cho công thức, nên
	Excel ở Protected View (file tải về), bản xem trước, Excel điện thoại… hiện dòng tổng TRỐNG và in
	ra cũng trống (HR báo 2026-11-04). Đổi lại: sửa tay một ô thì tổng không tự theo. Cột chữ và cột
	hệ số để trống."""
	for i, c in enumerate(columns, start=1):
		fieldname = c.get("fieldname") or ""
		cell = ws.cell(row, i)
		cell.font, cell.border, cell.fill = font(bold=True), BORDER, WHITE
		cell.alignment = Alignment(horizontal="center" if i > 4 else None, vertical="center")
		if fieldname == "stt":
			cell.value = _(TOTAL_LABEL)
		elif is_numeric(c) and fieldname not in NOT_SUMMED:
			cell.value = column_sum(ws, i, first, last)
			cell.number_format = GENERAL if fieldname == "worked_days" else INTEGER_FORMAT
	ws.row_dimensions[row].height = TOTAL_HEIGHT


def column_sum(ws, col: int, first: int, last: int) -> float:
	"""Tổng các ô số đã ghi ở một cột, từ dòng `first` tới `last` (ô trống bỏ qua)."""
	return sum(v for r in range(first, last + 1) if isinstance(v := ws.cell(r, col).value, int | float))


def is_numeric(c: dict) -> bool:
	return c.get("fieldtype") in ("Currency", "Float", "Int") and c.get("fieldname") != "stt"


def number_format(c: dict) -> str:
	if c.get("fieldname") == "tax_q":
		return TAX_FORMAT
	if c.get("fieldtype") == "Currency" or c.get("fieldname") == "dependents":
		return MONEY_FORMAT
	return GENERAL


def alignment_for(c: dict) -> Alignment:
	fieldname = c.get("fieldname")
	return Alignment(
		horizontal=None if fieldname in GENERAL_ALIGNED else "center",
		vertical="center",
		wrap_text=fieldname not in NO_WRAP,
	)


def set_widths(ws, last_col: int) -> None:
	for i in range(1, last_col + 1):
		letter = get_column_letter(i)
		ws.column_dimensions[letter].width = WIDTHS.get(letter, 13.0)


def setup_print(ws, last_col: int) -> None:
	"""Mẫu: A4 ngang, co vừa một trang ngang, lề trái/phải 0,25". Lặp dòng tiêu đề ở mọi trang."""
	ws.page_setup.orientation = "landscape"
	ws.page_setup.paperSize = ws.PAPERSIZE_A4
	ws.page_setup.fitToWidth = 1
	ws.page_setup.fitToHeight = 0
	ws.sheet_properties.pageSetUpPr.fitToPage = True
	ws.page_margins.left = ws.page_margins.right = 0.25
	ws.print_title_rows = f"{HEADER_ROW}:{HEADER_ROW}"
	ws.print_area = f"A1:{get_column_letter(last_col)}{ws.max_row}"


# ------------------------------------------------------------- khối ký


def write_signatures(ws, top: int, signatures: dict | None, company: str | None) -> None:
	"""Mẫu dòng 18-26: ngày tháng (R:T, nghiêng) → chức danh (I:J "Người lập", R:T "Người duyệt")
	→ chừa chỗ ký → tên → chức vụ. Không kẻ khung: chỗ ký tay, kẻ ô chỉ vướng chữ ký."""
	signatures = frappe._dict(signatures or {})
	prepared_name, approved_name = signature_names(signatures)
	prepared_title = (signatures.prepared_title or "").strip() or session_signer_title()
	approved_title = (signatures.approved_title or "").strip()

	title_row = top + 1
	name_row = title_row + SIGN_NAME_OFFSET
	place(ws, top, APPROVED_COLS, signature_date_line(company), font(italic=True))
	for cols, label, name, job in (
		(PREPARED_COLS, SIGN_PREPARED_LABEL, prepared_name, prepared_title),
		(APPROVED_COLS, SIGN_APPROVED_LABEL, approved_name, approved_title),
	):
		place(ws, title_row, cols, _(label), font(bold=True))
		place(ws, name_row, cols, name or None, font(bold=True))
		place(ws, name_row + 1, cols, job or None, font(bold=True))
	for r in range(top, name_row + 2):
		ws.row_dimensions[r].height = ROW_HEIGHT


def place(ws, row: int, cols: tuple[int, int], value, f: Font) -> None:
	cell = ws.cell(row, cols[0], value)
	cell.font, cell.alignment = f, Alignment(horizontal="center", vertical="bottom")
	ws.merge_cells(start_row=row, start_column=cols[0], end_row=row, end_column=cols[1])


def session_signer_title() -> str:
	"""Chức vụ của người đang xuất file (Employee.designation) — dòng dưới tên người lập."""
	user = frappe.session.user
	if not user or user in ("Guest", "Administrator"):
		return ""
	return frappe.db.get_value("Employee", {"user_id": user, "status": "Active"}, "designation") or ""


# ------------------------------------------------------------- tab Ăn trưa


def write_lunch_sheet(ws, body: list[dict], filters: dict, config: MVLConfig) -> None:
	"""Mẫu tab "Ăn trưa 09.2026": A1 tên + D1 đơn giá; dòng 3 tiêu đề; mỗi người có ăn trưa một
	dòng (STT, họ tên, số buổi, thành tiền, giữ lại, nộp quỹ canteen = thành tiền - giữ lại); cuối
	là dòng "Tổng".

	Thành tiền là GIÁ TRỊ trên phiếu (cột J tab Salary) chứ không phải `=C*$D$1`: phiếu đã chốt thì
	đổi đơn giá trong Settings không được làm tờ này lệch phiếu. Vì cùng lý do, đơn giá D1 là mức
	phiếu ĐÃ áp (thành tiền / số buổi), không phải mức đang đặt trong Settings. "Giữ lại" = số buổi
	đánh dấu "Giữ lại tiền ăn" trên chấm công x đơn giá đó. Nộp quỹ và dòng Tổng là SỐ, không công
	thức — cùng lý do với `write_total_row` (công thức không có giá trị tính sẵn → hiện/in trống)."""
	# Chỉ người thực nhận phụ cấp ăn (J > 0) — như mẫu, tab này nuôi cột J. Bán thời gian/khoán
	# vẫn có số buổi ăn trên phiếu nhưng không được phụ cấp; liệt kê ra thì dòng "21 buổi = 0đ" vô nghĩa.
	eaters = [r for r in body if (r.get("lunch_j") or 0) > 0]

	small = font(size=LUNCH_FONT_SIZE)
	ws.cell(1, 1, _("Ăn trưa tháng {0}.{1}").format(cint(filters.get("month")), cint(filters.get("year"))))
	ws.cell(1, 4, applied_lunch_rate(eaters, config)).number_format = TAX_FORMAT
	ws["A1"].font = ws["D1"].font = small

	for col in (1, 2):
		ws.cell(LUNCH_HEADER_ROW, col).border = BORDER
	for col, label in enumerate(LUNCH_LABELS, start=3):
		cell = ws.cell(LUNCH_HEADER_ROW, col, _(label))
		cell.font, cell.border = font(bold=True, size=LUNCH_FONT_SIZE), BORDER
		cell.alignment = Alignment(horizontal="center", vertical="bottom")

	row = LUNCH_HEADER_ROW
	for stt, r in enumerate(eaters, start=1):
		row = LUNCH_HEADER_ROW + stt
		write_lunch_row(ws, row, stt, r)

	total = row + 1
	ws.cell(total, 2, _("Tổng")).font = font()
	first = LUNCH_HEADER_ROW + 1
	for col, bold in ((4, False), (6, True)):
		cell = ws.cell(total, col, column_sum(ws, col, first, row) if eaters else 0)
		cell.font, cell.number_format = font(bold=bold, size=LUNCH_FONT_SIZE), TAX_FORMAT

	for r in range(1, total + 1):
		ws.row_dimensions[r].height = ROW_HEIGHT
	for letter, width in LUNCH_WIDTHS.items():
		ws.column_dimensions[letter].width = width
	ws.page_setup.orientation = "portrait"
	ws.page_setup.paperSize = ws.PAPERSIZE_A4


def applied_lunch_rate(eaters: list[dict], config: MVLConfig):
	"""Đơn giá một bữa mà các phiếu trong kỳ ĐÃ dùng (thành tiền / số buổi).

	Đơn giá không lưu trên phiếu và Settings không có ngày hiệu lực: HR đổi mức sau khi phiếu đã
	tính thì Settings không còn là mức của kỳ này. Không ai ăn → mức trong Settings. Các phiếu lệch
	mức nhau (một phần đã tính lại sau khi đổi) → ghi rõ thay vì chọn bừa một số."""
	rates = {
		round((r.get("lunch_j") or 0) / cint(r.get("lunch_days")))
		for r in eaters
		if cint(r.get("lunch_days"))
	}
	if not rates:
		return config.lunch_rate
	return rates.pop() if len(rates) == 1 else _("Nhiều mức - xem từng dòng")


def kept_amount(r: dict) -> int:
	"""Tiền "Giữ lại" = số buổi giữ lại x đơn giá phiếu ĐÃ áp (thành tiền / số buổi) — cùng lý do với
	`applied_lunch_rate`: đổi mức trong Settings sau khi phiếu đã tính không được làm lệch tờ này."""
	days, kept = cint(r.get("lunch_days")), cint(r.get("lunch_kept_days"))
	if not (days and kept):
		return 0
	return round((r.get("lunch_j") or 0) / days * min(kept, days))


def write_lunch_row(ws, row: int, stt: int, r: dict) -> None:
	"""STT · họ tên · số buổi (chữ 13 như mẫu) · thành tiền · giữ lại · nộp quỹ (chữ 11, như mẫu)."""
	small = font(size=LUNCH_FONT_SIZE)
	middle = Alignment(horizontal="center", vertical="center", wrap_text=True)
	cells = (
		(stt, font(), middle, GENERAL),
		(r.get("employee_name"), font(), Alignment(vertical="center"), GENERAL),
		(cint(r.get("lunch_days")), font(), middle, INTEGER_FORMAT),
		(r.get("lunch_j") or 0, small, None, TAX_FORMAT),
		(kept_amount(r), small, None, TAX_FORMAT),
		((r.get("lunch_j") or 0) - kept_amount(r), font(bold=True, size=LUNCH_FONT_SIZE), None, TAX_FORMAT),
	)
	for col, (value, f, align, fmt) in enumerate(cells, start=1):
		cell = ws.cell(row, col, value)
		cell.font, cell.border, cell.number_format = f, BORDER, fmt
		if align:
			cell.alignment = align


# ------------------------------------------------------------- endpoint


@frappe.whitelist()
def download(
	filters: str | dict | None = None,
	visible_idx: str | list | None = None,
	prepared_by: str | None = None,
	approved_by: str | None = None,
	prepared_title: str | None = None,
	approved_title: str | None = None,
):
	"""Endpoint của nút Export (Excel theo mẫu, có khối ký) trên `MVL Salary Register`."""
	from frappe.desk.utils import provide_binary_file

	from hrms.vn_payroll.settings import config_from_settings

	# đúng thứ `export_query` kiểm — `ref_doctype` của báo cáo là Salary Slip
	frappe.permissions.can_export("Salary Slip", raise_exception=True)

	filters = frappe.parse_json(filters) or {}
	# Endpoint này chỉ phục vụ bảng lương. `frappe.query_report` là MỘT instance dùng chung cho mọi
	# query report nên nút Export của báo cáo khác rất dễ gọi nhầm vào đây — nói thẳng ra thay vì
	# trả một file rỗng khó hiểu (đúng bẫy đã dính với bảng chấm công, 2026-08-03).
	if not (cint(filters.get("month")) and cint(filters.get("year"))):
		frappe.throw(_("Thiếu tháng/năm: đường xuất Excel này chỉ dùng cho báo cáo Bảng lương MVL."))

	columns, data = execute(filters)

	visible = frappe.parse_json(visible_idx) if visible_idx else None
	if visible:
		keep = set(visible)
		data = [row for i, row in enumerate(data) if i in keep]

	stream = BytesIO()
	signatures = {
		"prepared_by": prepared_by,
		"prepared_title": prepared_title,
		"approved_by": approved_by,
		"approved_title": approved_title,
	}
	build_workbook(columns, data, filters, signatures, config_from_settings()).save(stream)

	filters = frappe._dict(filters)
	name = f"Bang luong {cint(filters.month):02d}-{cint(filters.year)}"
	provide_binary_file(name, "xlsx", stream.getvalue())
