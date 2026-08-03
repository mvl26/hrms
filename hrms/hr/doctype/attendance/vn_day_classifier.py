# Copyright (c) 2026, Miyano Việt Nam.
"""Luật chấm công một ngày của Miyano: **ca trượt theo giờ vào** + **đủ giờ mới đủ công**.

Tách khỏi `attendance.py` và giữ THUẦN (không chạm DB, không biết Document là gì) để luật này
test được đầy đủ mà không cần site/custom field. `Attendance.apply_vn_half_day_classifier` chỉ
làm phần đọc cấu hình Shift Type rồi gọi vào đây.

Luật (spec/flex-shift-and-timekeeping-pipeline.md §4.2):

1. **Ca trượt** — khung ca dịch theo giờ check-in, tối đa ±`band_minutes` (mặc định 180). Vào muộn
   hơn biên thì kẹp ở biên: đi muộn quá mức vẫn phải bù đủ giờ tính từ mốc kẹp.
2. **Nghỉ trưa CỐ ĐỊNH theo đồng hồ** (12:00-13:30), không trượt theo ca — cả công ty ăn trưa cùng giờ.
3. **Giờ net** = phần thời gian có mặt nằm trong khung ca, trừ phần trùng giờ trưa. Làm ngoài khung
   ca không được cộng (làm thêm giờ tính theo kênh riêng).
4. `net ≥ min_work_hours` → `X` (đủ công) · `0 < net < min_work_hours` → `1/2X` (nửa công, có đi
   làm nhưng thiếu giờ) · `net = 0` → `V` (vắng).

Với biên ±3h và ca 08:00-17:30, khung trượt luôn bắt đầu ≤ 11:00 và kết thúc ≥ 14:30, nên giờ trưa
luôn nằm trọn trong khung → luôn trừ đủ 1,5h và mỗi phía của giờ trưa luôn còn ≥ 1h.
"""

from datetime import datetime, timedelta
from typing import NamedTuple

CODE_FULL_DAY = "X"  # đủ giờ → đủ công
CODE_SHORT_HOURS = "1/2X"  # có đi làm nhưng thiếu giờ → nửa công
CODE_ABSENT = "V"  # không có mặt phút nào trong khung ca → vắng

# nghỉ trưa mặc định khi ca không cấu hình được khung hợp lệ
DEFAULT_LUNCH_START = timedelta(hours=12)
DEFAULT_LUNCH_END = timedelta(hours=13, minutes=30)


def resolve_lunch_window(start, end) -> tuple[timedelta, timedelta]:
	"""Khung nghỉ trưa dùng được, hoặc mặc định 12:00-13:30 nếu cấu hình ca vô nghĩa.

	Không chỉ bắt giá trị trống: Shift Type tạo mới mà không nhập giờ nghỉ trưa bị Frappe điền
	GIỜ HIỆN TẠI vào cả hai field, thành khung rộng 0 giây (ví dụ 11:25:08 → 11:25:08). Khung đó
	tồn tại nên `... or DEFAULT` không bắt được, mà lại làm cả ngày không bị trừ phút nghỉ trưa
	nào → ca cấu hình sai tính DƯ 1,5h công mỗi ngày.
	"""
	if start and end and end > start:
		return start, end
	return DEFAULT_LUNCH_START, DEFAULT_LUNCH_END


def overlap_hours(a_start: datetime, a_end: datetime, b_start: datetime, b_end: datetime) -> float:
	"""Số giờ giao nhau của hai khoảng thời gian (0 nếu không giao hoặc khoảng rỗng/âm)."""
	start, end = max(a_start, b_start), min(a_end, b_end)
	return max(0.0, (end - start).total_seconds() / 3600.0)


def shift_window(
	in_time: datetime,
	day: datetime,
	start_time: timedelta,
	end_time: timedelta,
	flexible: bool,
	band_minutes: int,
) -> tuple[datetime, datetime]:
	"""Khung ca áp dụng cho ngày đó, đã trượt theo giờ check-in nếu ca bật giờ linh hoạt.

	`band_minutes = 0` ⇒ không trượt (dùng để tắt tính năng mà không phải sờ vào cờ)."""
	w_start, w_end = day + start_time, day + end_time
	if not (flexible and band_minutes):
		return w_start, w_end

	band = timedelta(minutes=band_minutes)
	offset = max(-band, min(band, in_time - w_start))
	return w_start + offset, w_end + offset


class DayResult(NamedTuple):
	"""Kết quả chấm một ngày. HAI con số giờ, đừng lẫn:

	- `hours` — **giờ làm thực tế**: ra - vào, trừ phần trùng nghỉ trưa. Đây là số giờ người ta đã
	  thực sự làm, hiện trên bảng công và báo cáo giờ làm việc. Không bị khung ca cắt.
	- `counted` — **giờ tính công**: phần nằm trong khung ca. Chỉ dùng để quyết định đủ công hay
	  thiếu giờ, để việc ở lại muộn không tự biến thành công thêm.
	"""

	hours: float
	counted: float
	code: str


def classify_day(
	in_time: datetime,
	out_time: datetime,
	*,
	day: datetime,
	start_time: timedelta,
	end_time: timedelta,
	lunch_start: timedelta,
	lunch_end: timedelta,
	flexible: bool = False,
	band_minutes: int = 0,
	min_work_hours: float = 8.0,
) -> DayResult:
	"""Chấm một ngày có giờ vào/ra → `DayResult(hours, counted, code)`.

	`day` là nửa đêm của ngày chấm công; `start_time`/`end_time`/`lunch_*` là timedelta tính từ
	nửa đêm (đúng kiểu Frappe trả về cho field Time).

	Trước đây hàm này chỉ trả MỘT số giờ — phần lọt vào khung ca — và ghi thẳng vào `working_hours`.
	Hệ quả: làm 08:23-18:55 (9h02 thật) bị ghi thành 8h vì khung ca trượt kết thúc 17:53. Khung ca
	có việc của nó là chặn làm thêm biến thành công, nhưng **không được bóp méo số giờ đã làm**.
	"""
	w_start, w_end = shift_window(in_time, day, start_time, end_time, flexible, band_minutes)
	l_start, l_end = day + lunch_start, day + lunch_end

	# giờ làm THỰC TẾ: toàn bộ thời gian có mặt, chỉ trừ phần trùng nghỉ trưa
	actual = overlap_hours(in_time, out_time, in_time, out_time) - overlap_hours(
		in_time, out_time, l_start, l_end
	)
	hours = round(max(actual, 0.0), 2)

	# giờ TÍNH CÔNG: chỉ phần nằm trong khung ca, trừ phần giờ trưa thực sự nằm trong khung đó
	# (khung trượt xa có thể không chứa trọn giờ trưa)
	in_window = overlap_hours(in_time, out_time, w_start, w_end)
	lunch_in_window = overlap_hours(in_time, out_time, max(w_start, l_start), min(w_end, l_end))
	counted = round(max(in_window - lunch_in_window, 0.0), 2)

	if counted >= min_work_hours:
		return DayResult(hours, counted, CODE_FULL_DAY)
	if counted > 0:
		return DayResult(hours, counted, CODE_SHORT_HOURS)
	return DayResult(hours, counted, CODE_ABSENT)
