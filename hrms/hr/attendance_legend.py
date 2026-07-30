# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt
"""Chú thích ký hiệu mã công — MỘT DÒNG, dùng chung cho mọi báo cáo chấm công.

Bản in Bảng Công Tháng vẫn luôn có chú thích một dòng ở cuối tờ. Đây là bản dùng chung cho báo
cáo trên màn hình, để không phải chép lại danh sách mã ở từng nơi — và để thêm/bớt mã trong
`Attendance Code` là mọi báo cáo tự cập nhật.

Trả về dạng `message` của query report (HTML nằm TRÊN bảng), cố ý không nhét thành dòng dữ liệu:
nhét vào bảng thì báo cáo dài ra và lẫn với dữ liệu thật. Đánh đổi: `message` KHÔNG đi vào file
Excel xuất ra — `frappe.desk.query_report._export_query` dựng file từ `columns` + `result` mà thôi.
"""

import frappe
from frappe import _

# Hai ký hiệu suy từ lịch chứ không phải Attendance Code, nhưng vẫn hiện trong lưới nên phải chú thích
CALENDAR_MARKERS = [("-", "Ngày nghỉ / ngoài thời gian làm việc"), ("NL", "Nghỉ lễ hưởng lương")]


def legend_pairs() -> list[tuple[str, str]]:
	"""[(ký hiệu, nghĩa)] theo thứ tự hiển thị — nguồn là Attendance Code, không viết cứng."""
	codes = frappe.get_all(
		"Attendance Code",
		fields=["name", "code_name", "category", "work_fraction"],
	)
	order = ["Công", "Phép", "Ốm", "Thai sản", "Tai nạn LĐ", "Nghỉ bù", "Việc riêng", "Không lương", "Vắng"]

	def key(c):
		rank = order.index(c.category) if c.category in order else len(order)
		is_half = 0 < frappe.utils.flt(c.work_fraction) < 1  # mã cả ngày trước, nửa ngày ngay sau
		return (rank, is_half, c.name != "X", c.name)  # X là ký hiệu gốc của bảng công → đứng đầu

	pairs = [(c.name, c.code_name or c.name) for c in sorted(codes, key=key)]
	return pairs + CALENDAR_MARKERS


def legend_text() -> str:
	"""Một dòng thuần văn bản: `X=Đi làm đủ công; CT=Đi công tác; ...`"""
	return "; ".join(f"{code}={name}" for code, name in legend_pairs())


def legend_html() -> str:
	"""Một dòng HTML để gắn vào `message` của bất kỳ query report nào có hiện mã công."""
	return (
		'<div style="font-size:11px;line-height:1.5;color:var(--text-muted)">'
		f"<b>{frappe.utils.escape_html(_('Chú thích'))}:</b> "
		f"{frappe.utils.escape_html(legend_text())}</div>"
	)
