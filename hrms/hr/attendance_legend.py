# Copyright (c) 2026, Miyano Việt Nam.
"""Chú thích ký hiệu mã công — nguồn dùng chung cho mọi báo cáo chấm công.

Bản in Bảng Công Tháng vẫn luôn có chú thích ở cuối tờ. Đây là bản dùng chung cho báo cáo trên
màn hình, để không phải chép lại danh sách mã ở từng nơi — thêm/bớt mã trong `Attendance Code`
là mọi báo cáo tự cập nhật.

Mỗi ký hiệu hiện dưới dạng chip **tô đúng màu mà ô đó mang trong lưới** (cùng `STATE_STYLE` với
formatter của report và bản in), nên nhìn chú thích là tra được màu luôn — không phải đoán ô vàng
nghĩa là gì.

- `legend_pairs()` → [(ký hiệu, nghĩa)] theo thứ tự hiển thị; file Excel dựng khối lưới từ đây.
- `legend_html()` → `message` của query report: khối chip màu nằm TRÊN bảng, chỉ có trên màn hình.

Từng có thêm `legend_row()`: ĐÚNG MỘT dòng cuối bảng, dồn cả danh sách mã vào một ô văn bản, chỉ
để chú thích theo được vào file Excel (`message` không đi vào file). Bỏ 2026-08-03 — đường xuất
Excel của Miyano (`hrms/hr/attendance_xlsx.py`) đã tự dựng khối chú thích dạng lưới có màu, nên
dòng văn bản dài đó chỉ còn làm bẩn cuối bảng.
"""

import frappe
from frappe import _
from frappe.utils import escape_html, flt

from hrms.hr.attendance_category import CATEGORIES

# Hai ký hiệu suy từ lịch chứ không phải Attendance Code, nhưng vẫn hiện trong lưới nên phải chú thích
CALENDAR_MARKERS = [("-", "Ngày nghỉ / ngoài thời gian làm việc"), ("NL", "Nghỉ lễ hưởng lương")]

# đi làm trước → nghỉ có lương → không lương → vắng: đọc từ trái sang là đi từ "trả đủ" tới "không
# trả". Nguồn duy nhất là `attendance_category.CATEGORIES` — chú thích KHÔNG giữ bản chép riêng,
# nếu không thêm nhóm mới là mã tụt xuống cuối chú thích mà không ai biết.
CATEGORY_ORDER = list(CATEGORIES)


def legend_pairs() -> list[tuple[str, str]]:
	"""[(ký hiệu, nghĩa)] theo thứ tự hiển thị — nguồn là Attendance Code, không viết cứng."""
	codes = frappe.get_all("Attendance Code", fields=["name", "code_name", "category", "work_fraction"])

	def key(c):
		rank = CATEGORY_ORDER.index(c.category) if c.category in CATEGORY_ORDER else len(CATEGORY_ORDER)
		is_half = 0 < flt(c.work_fraction) < 1  # mã cả ngày trước, nửa ngày ngay sau
		return (rank, is_half, c.name != "X", c.name)  # X là ký hiệu gốc của bảng công → đứng đầu

	return [(c.name, c.code_name or c.name) for c in sorted(codes, key=key)] + CALENDAR_MARKERS


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
