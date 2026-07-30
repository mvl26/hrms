# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt
"""Chú thích ký hiệu mã công — MỘT DÒNG, dùng chung cho mọi báo cáo chấm công.

Bản in Bảng Công Tháng vẫn luôn có chú thích ở cuối tờ. Đây là bản dùng chung cho báo cáo trên
màn hình, để không phải chép lại danh sách mã ở từng nơi — thêm/bớt mã trong `Attendance Code`
là mọi báo cáo tự cập nhật.

Mỗi ký hiệu hiện dưới dạng chip **tô đúng màu mà ô đó mang trong lưới** (cùng `STATE_STYLE` với
formatter của report và bản in), nên nhìn chú thích là tra được màu luôn — không phải đoán ô vàng
nghĩa là gì.

Hai đường ra, cho hai nơi khác nhau:

- `legend_html()` → `message` của query report: khối chip màu nằm TRÊN bảng, chỉ có trên màn hình.
- `legend_row()` → ĐÚNG MỘT dòng cuối bảng, thuần văn bản, để chú thích có mặt trong file Excel.

Phải có dòng đó vì `message` không đi vào file: `_export_query` dựng file từ `columns` + `result`.
Và dòng đó phải nằm sẵn trong bảng chứ không thể chỉ thêm lúc xuất — `build_xlsx_data` lọc dòng
theo `visible_idx` client gửi lên, dòng nào màn hình không có sẽ bị loại khỏi file.
"""

import frappe
from frappe import _
from frappe.utils import escape_html, flt

# Hai ký hiệu suy từ lịch chứ không phải Attendance Code, nhưng vẫn hiện trong lưới nên phải chú thích
CALENDAR_MARKERS = [("-", "Ngày nghỉ / ngoài thời gian làm việc"), ("NL", "Nghỉ lễ hưởng lương")]

# đi làm trước → nghỉ có lương → không lương → vắng: đọc từ trái sang là đi từ "trả đủ" tới "không trả"
CATEGORY_ORDER = [
	"Công",
	"Phép",
	"Ốm",
	"Thai sản",
	"Tai nạn LĐ",
	"Nghỉ bù",
	"Việc riêng",
	"Không lương",
	"Vắng",
]


def legend_pairs() -> list[tuple[str, str]]:
	"""[(ký hiệu, nghĩa)] theo thứ tự hiển thị — nguồn là Attendance Code, không viết cứng."""
	codes = frappe.get_all("Attendance Code", fields=["name", "code_name", "category", "work_fraction"])

	def key(c):
		rank = CATEGORY_ORDER.index(c.category) if c.category in CATEGORY_ORDER else len(CATEGORY_ORDER)
		is_half = 0 < flt(c.work_fraction) < 1  # mã cả ngày trước, nửa ngày ngay sau
		return (rank, is_half, c.name != "X", c.name)  # X là ký hiệu gốc của bảng công → đứng đầu

	return [(c.name, c.code_name or c.name) for c in sorted(codes, key=key)] + CALENDAR_MARKERS


def legend_text() -> str:
	"""Một dòng thuần văn bản: `X=Đi làm đủ công; CT=Đi công tác; ...` (cho nơi không nhận HTML)."""
	return "; ".join(f"{code}={name}" for code, name in legend_pairs())


def legend_styles() -> str:
	"""CSS của khối chú thích: một lớp màu cho mỗi state, có cả bản nền tối của Desk.

	Desk đặt `data-theme` trên thẻ gốc nên cặp màu tối phải override theo thuộc tính đó, không thể
	chỉ dựa vào `prefers-color-scheme` (người dùng đổi theme trong Desk mà không đổi theme hệ điều
	hành thì màu sẽ lệch)."""
	from hrms.hr.report.monthly_attendance_report.monthly_attendance_report import STATE_STYLE

	light = "\n".join(
		f".vn-lg-{state} {{ background:{s['bg']}; color:{s['fg']}; }}" for state, s in STATE_STYLE.items()
	)
	dark = "\n".join(
		f'[data-theme="dark"] .vn-lg-{state} {{ background:{s["bg_dark"]}; color:{s["fg_dark"]}; }}'
		for state, s in STATE_STYLE.items()
	)
	return f"""<style>
.vn-legend {{
	display:flex; flex-wrap:wrap; align-items:center; gap:4px 14px;
	margin:0 0 10px; padding:10px 12px;
	border:1px solid var(--border-color); border-radius:var(--border-radius-md, 6px);
	background:var(--fg-color, #fff); font-size:12px; line-height:1.6;
}}
.vn-legend-title {{
	font-weight:600; color:var(--text-color); margin-right:2px;
	padding-right:12px; border-right:1px solid var(--border-color); align-self:stretch;
	display:flex; align-items:center; white-space:nowrap;
}}
.vn-legend-item {{ display:inline-flex; align-items:center; gap:5px; white-space:nowrap; }}
.vn-legend-code {{
	display:inline-flex; align-items:center; justify-content:center;
	min-width:34px; height:20px; padding:0 6px;
	border-radius:4px; font-weight:600; font-size:11px; letter-spacing:.2px;
}}
.vn-legend-name {{ color:var(--text-muted); }}
.vn-lg-none {{ background:var(--bg-color, #f4f5f6); color:var(--text-muted); }}
{light}
{dark}
</style>"""


def legend_html() -> str:
	"""Khối chú thích một dòng (tự xuống dòng khi hẹp) để gắn vào `message` của query report."""
	from hrms.hr.report.monthly_attendance_report.monthly_attendance_report import (
		day_state,
		get_code_map,
	)

	code_map = get_code_map()
	items = []
	for code, name in legend_pairs():
		state = day_state(code, code_map) or "none"
		items.append(
			f'<span class="vn-legend-item">'
			f'<span class="vn-legend-code vn-lg-{escape_html(state)}">{escape_html(code)}</span>'
			f'<span class="vn-legend-name">{escape_html(name)}</span>'
			f"</span>"
		)

	return (
		f"{legend_styles()}"
		f'<div class="vn-legend">'
		f'<span class="vn-legend-title">{escape_html(_("Chú thích"))}</span>'
		f"{''.join(items)}"
		f"</div>"
	)


# Cột đặt dòng chú thích trong bảng: rộng nhất trong các cột văn bản, và là cột người đọc quét mắt
# xuống đầu tiên. Không đặt vào cột `employee` (Link) để nó không bị render thành liên kết gãy.
LEGEND_ROW_FIELD = "employee_name"


def legend_row() -> dict:
	"""ĐÚNG MỘT dòng chú thích, gắn cuối bảng để đi được vào file Excel xuất ra."""
	return {LEGEND_ROW_FIELD: f"{_('Chú thích')}: {legend_text()}"}


def is_legend_row(row: dict) -> bool:
	"""Dòng chú thích, không phải dòng nhân viên — dùng để bỏ qua khi thống kê."""
	return (
		bool(row)
		and not row.get("employee")
		and str(row.get(LEGEND_ROW_FIELD, "")).startswith(f"{_('Chú thích')}:")
	)
