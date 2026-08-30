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
from datetime import date, datetime, time, timedelta

import frappe
from frappe import _
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


class WorkScheduleNotConfigured(frappe.ValidationError):
	"""Không suy được lịch tuần. Nổ thay vì đoán — đoán sai là sai mẫu số lương cả tháng."""


def weekday_rows(parent: str, parenttype: str, parentfield: str) -> frozenset[int]:
	"""Đọc THẲNG bảng con `Assignment Rule Day`, không đi qua meta của doctype cha.

	Nhờ vậy hàm chạy được cả khi site chưa `bench migrate` custom field, và không phải nạp cả
	một Document chỉ để lấy vài tên thứ.
	"""
	rows = frappe.get_all(
		"Assignment Rule Day",
		filters={"parent": parent, "parenttype": parenttype, "parentfield": parentfield},
		pluck="day",
	)
	return weekday_set(rows)


def shift_weekdays(shift: str | None) -> frozenset[int] | None:
	"""Lịch tuần của một ca, hoặc `None` nếu ca chưa khai (để tầng trên rơi tiếp)."""
	if not shift:
		return None
	return weekday_rows(shift, "Shift Type", "custom_working_days") or None


def company_default_weekdays() -> frozenset[int] | None:
	"""Lịch tuần mặc định của công ty — lưới an toàn cho nhân viên chưa phân ca."""
	return weekday_rows("Work Calendar Settings", "Work Calendar Settings", "default_working_days") or None


def employee_shift(employee: str, date) -> str | None:
	"""Ca của nhân viên vào ngày đó: Shift Assignment phủ ngày → `Employee.default_shift`.

	Cố ý KHÔNG dùng `get_employee_shift`: hàm đó phân giải theo KHUNG GIỜ (mốc nào rơi vào ca nào),
	nên hỏi bằng mốc 00:00 thì ca hành chính 8h-17h không khớp và nó tụt về `default_shift` — ca gán
	theo tháng bị bỏ qua trong im lặng. Ở đây câu hỏi là "ngày này thuộc ca nào", nên lọc theo ngày.

	`get_shifts_for_date` nới ±1 ngày để bắt ca qua đêm, vì vậy phải siết lại về phủ ĐÚNG ngày.
	"""
	from hrms.hr.doctype.shift_assignment.shift_assignment import get_shifts_for_date

	on = getdate(date)
	for row in get_shifts_for_date(employee, datetime.combine(on, time.min)):
		starts_before = getdate(row.start_date) <= on
		ends_after = not row.end_date or getdate(row.end_date) >= on
		if starts_before and ends_after:
			return row.shift_type

	return frappe.get_cached_value("Employee", employee, "default_shift")


def employee_weekdays(employee: str, date) -> frozenset[int]:
	"""Shift Assignment của ngày đó → `Employee.default_shift` → mặc định công ty → LỖI.

	Tầng cuối nổ lỗi là CHỦ Ý: thà dừng lại còn hơn âm thầm coi mọi ngày là ngày làm việc, chấm
	`V` cả tháng và thổi mẫu số lương từ 23 lên 31.
	"""
	days = shift_weekdays(employee_shift(employee, date)) or company_default_weekdays()
	if days is None:
		frappe.throw(
			_(
				"Chưa khai ngày làm việc trong tuần cho nhân viên {0} (trên ca hoặc trong Cấu hình lịch làm việc)."
			).format(employee),
			exc=WorkScheduleNotConfigured,
		)
	return days


def holiday_list_for(employee: str, date) -> str | None:
	"""Holiday List phủ ĐÚNG ngày được hỏi.

	`get_holiday_list_for_employee` của ERPNext mù ngày tháng — trả về đúng một list bất kể hỏi về
	ngày nào. Với mô hình mỗi năm một list, đứng ở 2027 mà xem lại tháng 12/2026 sẽ tra nhầm lịch
	2027 và mất sạch ký hiệu NL.

	Ưu tiên list mà ERPNext phân giải NẾU nó phủ ngày đó (tôn trọng link chỉ định trên Employee /
	Department), rồi mới tới list của năm đó theo quy ước đặt tên của generator. Cố ý KHÔNG quét
	"list nào phủ ngày này" một cách tuỳ ý: site đang có `Salary Slip Test Holiday List` phủ trùng
	y hệt khoảng của lịch thật, quét bừa là bốc trúng danh sách rác của test.
	"""
	from erpnext.setup.doctype.employee.employee import get_holiday_list_for_employee

	from hrms.setup_vn_holiday import vn_holiday_list_name

	date = getdate(date)
	resolved = get_holiday_list_for_employee(employee, raise_exception=False)
	if resolved and holiday_list_covers(resolved, date):
		return resolved

	company = frappe.get_cached_value("Employee", employee, "company")
	by_convention = vn_holiday_list_name(company, date.year)
	if frappe.db.exists("Holiday List", by_convention):
		return by_convention

	return resolved


def holiday_list_covers(holiday_list: str, date) -> bool:
	period = frappe.get_cached_value("Holiday List", holiday_list, ["from_date", "to_date"])
	if not period:
		return False
	from_date, to_date = period
	return bool(from_date and to_date and getdate(from_date) <= getdate(date) <= getdate(to_date))


def is_scheduled_day(employee: str, date) -> bool:
	"""Nằm trong lịch tuần. KHÔNG xét ngày lễ."""
	return getdate(date).weekday() in employee_weekdays(employee, date)


def is_rest_day(employee: str, date) -> bool:
	"""Ngoài lịch tuần (T7/CN) → bảng công hiện `-`, không ai có công."""
	return not is_scheduled_day(employee, date)


def is_public_holiday(employee: str, date) -> bool:
	"""Ngày nghỉ lễ → bảng công hiện `NL`, hưởng nguyên lương.

	Giao thêm với lịch tuần như một lớp phòng thủ: dòng lễ rơi ngoài lịch tuần KHÔNG được tính,
	nếu không một dòng nhập nhầm vào Chủ nhật sẽ cộng khống một ngày công vào lương.

	`weekly_off: 0` là bắc cầu cho giai đoạn chuyển tiếp — trước khi di trú, Holiday List vẫn còn
	các dòng nghỉ cuối tuần và chúng không được lẫn vào ngày lễ. Sau di trú điều kiện này vô hại.
	"""
	if not is_scheduled_day(employee, date):
		return False
	holiday_list = holiday_list_for(employee, date)
	if not holiday_list:
		return False
	return bool(
		frappe.db.exists(
			"Holiday",
			{"parent": holiday_list, "holiday_date": getdate(date), "weekly_off": 0},
		)
	)


def is_working_day(employee: str, date) -> bool:
	"""PHẢI ĐI LÀM = nằm trong lịch tuần VÀ không phải ngày lễ."""
	return is_scheduled_day(employee, date) and not is_public_holiday(employee, date)
