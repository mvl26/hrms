# Copyright (c) 2026, Miyano Việt Nam.
"""Nguồn duy nhất trả lời "ngày này có phải ngày làm việc không".

Trước module này, cuối tuần và ngày nghỉ lễ là cùng một thứ trong dữ liệu (đều là dòng Holiday,
phân biệt bằng cờ `weekly_off`), nên không nơi nào hỏi được lịch tuần mà không đi vòng qua bảng
ngày nghỉ lễ, và khái niệm "trong ca / ngoài ca" — nền của OT — không tồn tại.

QUY ƯỚC ĐẶT TÊN, đọc kỹ trước khi dùng:

    scheduled_* = theo LỊCH TUẦN, KỂ CẢ ngày lễ  ->  đây là MẪU SỐ LƯƠNG
    working_*   = PHẢI ĐI LÀM, tức đã trừ ngày lễ

Ngày lễ hưởng nguyên lương (Đ.112 BLLĐ; HR chốt 2026-08-04: ngày công chuẩn = ngày đi làm + nghỉ lễ
+ nghỉ có lương) nên nó nằm TRONG mẫu số. Dùng nhầm `working_*` cho mẫu số sẽ hụt đúng bằng số ngày
lễ của tháng — lỗi im lặng, chỉ lộ ở tháng có lễ.

Spec: `docs/spec/work-schedule-and-holiday-separation.md`.
"""

from collections.abc import Iterable, Iterator
from datetime import date, timedelta

from frappe.utils import getdate

# date.weekday(): 0 = thứ Hai … 6 = Chủ nhật. Tên thứ khớp child doctype `Assignment Rule Day`.
WEEKDAY_INDEX = {
	"Monday": 0,
	"Tuesday": 1,
	"Wednesday": 2,
	"Thursday": 3,
	"Friday": 4,
	"Saturday": 5,
	"Sunday": 6,
}


def weekday_set(day_names: Iterable[str] | None) -> frozenset[int]:
	"""Tên thứ → chỉ số `date.weekday()`.

	Bỏ qua tên không nhận ra thay vì nổ: một dòng cấu hình hỏng không được phép làm chết cả kỳ
	lương. Cấu hình rỗng hoàn toàn thì để chuỗi phân giải ở tầng trên xử lý — ở đó việc "không suy
	được lịch" mới đủ nghiêm trọng để dừng lại.
	"""
	return frozenset(WEEKDAY_INDEX[d] for d in (day_names or []) if d in WEEKDAY_INDEX)


def dates_in_range(start, end) -> Iterator[date]:
	"""Mọi ngày từ `start` tới `end`, bao gồm cả hai đầu."""
	current, last = getdate(start), getdate(end)
	while current <= last:
		yield current
		current += timedelta(days=1)


def scheduled_dates(weekdays: frozenset[int], start, end) -> set[date]:
	"""Ngày nằm trong lịch tuần. KHÔNG xét ngày lễ — thuần luật, không chạm DB."""
	return {d for d in dates_in_range(start, end) if d.weekday() in weekdays}
