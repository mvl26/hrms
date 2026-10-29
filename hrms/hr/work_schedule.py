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
# Loại ngày đặc biệt (khớp `Work Calendar Day.day_type`) — chỉ "Làm bù" đổi được lịch tuần.
MAKE_UP_DAY = "Làm bù"

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


def calendar_exceptions(year: int) -> dict:
	"""{ngày: loại} của một năm — những ngày KHÁC với mẫu tuần (nghỉ ghép / làm bù).

	`custom_working_days` là mẫu tuần lặp lại vô hạn: nó không nói được "riêng thứ Bảy 29/08/2026
	thì đi làm". Mô hình cũ nói được (HR xoá dòng `weekly_off` của đúng ngày đó), nên thiếu bảng
	này thì việc tách lịch là một bước LÙI về khả năng biểu đạt. Xem spec §3b.
	"""
	rows = frappe.get_all(
		"Work Calendar Day",
		filters={
			"parent": "Work Calendar Settings",
			"parenttype": "Work Calendar Settings",
			"parentfield": "calendar_days",
			"year": int(year),
		},
		fields=["holiday_date", "day_type"],
	)
	return {getdate(r.holiday_date): r.day_type for r in rows if r.holiday_date}


def is_scheduled_day(employee: str, date) -> bool:
	"""Nằm trong lịch tuần. KHÔNG xét ngày lễ.

	= (thứ có trong mẫu tuần) HOẶC (ngày được khai "Làm bù"). Ngoại lệ chỉ cần biết ở ĐÂY; sáu nơi
	tiêu thụ đúng theo mà không phải sửa dòng nào — đó là lợi tức của thiết kế một cửa.
	"""
	date = getdate(date)
	if calendar_exceptions(date.year).get(date) == MAKE_UP_DAY:
		return True
	return date.weekday() in employee_weekdays(employee, date)


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


def shift_runs(employees: list[str], start, end) -> dict[str, list[tuple]]:
	"""{nhân viên: [(từ ngày, tới ngày, ca)]} — mọi Shift Assignment chồng lấn khoảng, MỘT truy vấn.

	Nền của các hàm bulk. Không gộp được thành "ca của cả kỳ": ca đổi giữa kỳ là chuyện thường
	(Miyano cấp ca theo từng tháng), mà đổi ca là đổi lịch tuần, tức đổi mẫu số lương.
	"""
	if not employees:
		return {}
	rows = frappe.get_all(
		"Shift Assignment",
		filters=[
			["employee", "in", employees],
			["docstatus", "=", 1],
			["status", "=", "Active"],
			["start_date", "<=", getdate(end)],
		],
		or_filters=[["end_date", "is", "not set"], ["end_date", ">=", getdate(start)]],
		fields=["employee", "shift_type", "start_date", "end_date"],
		order_by="start_date asc",
	)
	runs = {}
	for r in rows:
		runs.setdefault(r.employee, []).append(
			(getdate(r.start_date), getdate(r.end_date) if r.end_date else None, r.shift_type)
		)
	return runs


def weekdays_by_date(employee: str, start, end) -> dict[date, frozenset[int]]:
	"""Lịch tuần áp cho TỪNG ngày của khoảng — tôn trọng việc đổi ca giữa kỳ.

	Lấy ca của một ngày rồi áp cho cả kỳ là sai ngay khi có Shift Assignment cắt ngang tháng.
	Chỉ tra lịch tuần một lần cho mỗi ca khác nhau, nên vẫn là vài truy vấn chứ không phải N.
	"""
	runs = shift_runs([employee], start, end).get(employee, [])
	default_shift = frappe.get_cached_value("Employee", employee, "default_shift")
	cache: dict[str | None, frozenset[int] | None] = {}

	def days_of(shift):
		if shift not in cache:
			cache[shift] = shift_weekdays(shift)
		return cache[shift]

	fallback = company_default_weekdays()
	out = {}
	for d in dates_in_range(start, end):
		shift = next(
			(s for (frm, to, s) in runs if frm <= d and (to is None or to >= d)),
			default_shift,
		)
		days = days_of(shift) or fallback
		if days is None:
			frappe.throw(
				_(
					"Chưa khai ngày làm việc trong tuần cho nhân viên {0} (trên ca hoặc trong Cấu hình lịch làm việc)."
				).format(employee),
				exc=WorkScheduleNotConfigured,
			)
		out[d] = days
	return out


def make_up_days_between(start, end) -> set[date]:
	"""Ngày `Làm bù` (cuối tuần phải đi làm) rơi trong khoảng — gộp mọi năm mà khoảng chạm tới."""
	years = {getdate(start).year, getdate(end).year}
	first, last = getdate(start), getdate(end)
	out = set()
	for year in years:
		out |= {
			d
			for d, day_type in calendar_exceptions(year).items()
			if day_type == MAKE_UP_DAY and first <= d <= last
		}
	return out


def scheduled_days_between(employee: str, start, end) -> set[date]:
	"""MẪU SỐ LƯƠNG: ngày theo lịch tuần trong khoảng, **KỂ CẢ ngày lễ**.

	Ngày lễ hưởng nguyên lương nên nó nằm TRONG mẫu số (HR chốt 2026-08-04). Đừng đổi sang
	`working_*` — sẽ hụt đúng bằng số ngày lễ của tháng, và chỉ lộ ở tháng có lễ.

	Ngày `Làm bù` được cộng vào: đi làm thứ Bảy thì tháng đó có thêm một ngày công thật.
	"""
	from_pattern = {d for d, days in weekdays_by_date(employee, start, end).items() if d.weekday() in days}
	return from_pattern | make_up_days_between(start, end)


def public_holidays_between(employee: str, start, end) -> set[date]:
	"""Ngày lễ trong khoảng, ĐÃ giao với lịch tuần (phòng dòng lễ nhập nhầm vào T7/CN)."""
	holiday_list = holiday_list_for(employee, start)
	if not holiday_list:
		return set()
	rows = frappe.get_all(
		"Holiday",
		filters={
			"parent": holiday_list,
			"parenttype": "Holiday List",
			"holiday_date": ["between", [getdate(start), getdate(end)]],
			"weekly_off": 0,
		},
		pluck="holiday_date",
	)
	return {getdate(d) for d in rows} & scheduled_days_between(employee, start, end)


def non_working_days_between(employee: str, start, end) -> set[date]:
	"""Ngày KHÔNG phải đi làm = hợp của ngoài lịch tuần và ngày lễ. Đã khử trùng.

	Tập thay thế cho `get_holiday_dates_between` ở mọi nơi tiêu thụ. Trong giai đoạn chuyển tiếp
	(Holiday List còn dòng nghỉ cuối tuần) tập này bằng ĐÚNG tập cũ — đó là lý do các bước đổi
	consumer đều bất biến và thứ tự triển khai không quan trọng.
	"""
	everything = set(dates_in_range(start, end))
	return (everything - scheduled_days_between(employee, start, end)) | public_holidays_between(
		employee, start, end
	)


def working_days_between(employee: str, start, end) -> set[date]:
	"""Ngày PHẢI ĐI LÀM trong khoảng = theo lịch tuần (kể cả làm bù), TRỪ ngày lễ.

	Khác `scheduled_days_between` đúng ở ngày lễ: `scheduled_*` là mẫu số lương (lễ hưởng lương nên
	nằm trong), `working_*` là kỳ vọng có mặt (lễ thì không ai phải có mặt). Giờ định mức dùng tập
	này; đừng dùng lẫn."""
	return scheduled_days_between(employee, start, end) - public_holidays_between(employee, start, end)


# Giờ ca khi nhân viên không có ca, hoặc ca không khai được giờ vào/ra hợp lệ. Đây là LƯỚI AN TOÀN
# để báo cáo không vỡ, KHÔNG phải chính sách "một ngày công = 8 giờ": chính sách nằm ở Shift Type.
FALLBACK_SHIFT_HOURS = 8.0


def shift_hours_per_day(shift: str | None) -> float:
	"""Số giờ làm của một ngày theo ca = (giờ ra - giờ vào - phần trùng nghỉ trưa).

	Khung nghỉ trưa đi qua `resolve_lunch_window` của bộ chấm công, để lớp phòng thủ "khung trưa
	rác" (Frappe điền giờ hiện tại vào ô trống → khung rộng 0 giây) chỉ viết ở một chỗ."""
	if not shift:
		return FALLBACK_SHIFT_HOURS

	from hrms.hr.doctype.attendance.vn_day_classifier import resolve_lunch_window

	meta = frappe.get_meta("Shift Type")
	lunch_fields = [f for f in ("custom_lunch_start", "custom_lunch_end") if meta.has_field(f)]
	cfg = frappe.db.get_value("Shift Type", shift, ["start_time", "end_time", *lunch_fields], as_dict=True)
	if not cfg or cfg.start_time is None or cfg.end_time is None or cfg.end_time <= cfg.start_time:
		return FALLBACK_SHIFT_HOURS

	lunch_start, lunch_end = resolve_lunch_window(cfg.get("custom_lunch_start"), cfg.get("custom_lunch_end"))
	lunch = max(timedelta(0), min(cfg.end_time, lunch_end) - max(cfg.start_time, lunch_start))
	return round((cfg.end_time - cfg.start_time - lunch).total_seconds() / 3600.0, 2)


def standard_hours_between(employee: str, start, end, exclude_leave: bool = True) -> float:
	"""GIỜ ĐỊNH MỨC của nhân viên trong khoảng = Σ giờ ca của từng ngày phải đi làm.

	Định mức là *kỳ vọng có mặt*, nên:

	- theo **ca của đúng ngày đó** (đổi ca giữa kỳ là chuyện thường) — không hardcode 8h;
	- theo **lịch làm việc** (`working_days_between`) — không đọc Holiday List, vì danh sách đó chỉ
	  còn ngày lễ; đếm "ngày trong tháng trừ số dòng" là tính cả thứ Bảy, Chủ nhật vào định mức;
	- `exclude_leave`: bỏ những ngày đã nghỉ CÓ ĐƠN (cả ngày → trừ trọn giờ ca; nửa ngày → trừ một
	  nửa). Không trừ thì người nghỉ phép đúng quy định luôn bị báo thiếu giờ. Ngày **vắng** thì ở
	  lại trong định mức — đó chính là ngày đáng ra phải có mặt.
	"""
	days = working_days_between(employee, start, end)
	if not days:
		return 0.0

	runs = shift_runs([employee], start, end).get(employee, [])
	default_shift = frappe.get_cached_value("Employee", employee, "default_shift")
	hours_of: dict[str | None, float] = {}

	def hours_on(day) -> float:
		shift = next((s for (frm, to, s) in runs if frm <= day and (to is None or to >= day)), default_shift)
		if shift not in hours_of:
			hours_of[shift] = shift_hours_per_day(shift)
		return hours_of[shift]

	total = sum(hours_on(d) for d in days)

	if exclude_leave:
		for att in frappe.get_all(
			"Attendance",
			filters={
				"employee": employee,
				"docstatus": 1,
				"attendance_date": ["between", [getdate(start), getdate(end)]],
				"status": ["in", ["On Leave", "Half Day"]],
			},
			fields=["attendance_date", "status", "leave_type"],
		):
			day = getdate(att.attendance_date)
			if day not in days:
				continue
			if att.status == "On Leave":
				total -= hours_on(day)
			elif att.leave_type:  # nửa ngày nghỉ có đơn; `1/2X` (thiếu giờ, không loại nghỉ) thì không trừ
				total -= hours_on(day) / 2

	return round(max(total, 0.0), 2)


def scheduled_days_map(employees: list[str], start, end) -> dict[str, dict[date, str]]:
	"""{nhân viên: {ngày: "scheduled" | "rest" | "holiday"}} — bản đồ gộp cho báo cáo/bảng công.

	Bảng công là 31 ngày x N nhân viên; gọi API lẻ trong vòng lặp là N+1 truy vấn. Ở đây mỗi ca
	chỉ tra lịch tuần một lần và mỗi Holiday List chỉ quét một lần.
	"""
	out: dict[str, dict[date, str]] = {}
	holidays_by_list: dict[str, set[date]] = {}

	for employee in employees:
		holiday_list = holiday_list_for(employee, start)
		if holiday_list and holiday_list not in holidays_by_list:
			rows = frappe.get_all(
				"Holiday",
				filters={
					"parent": holiday_list,
					"parenttype": "Holiday List",
					"holiday_date": ["between", [getdate(start), getdate(end)]],
					"weekly_off": 0,
				},
				pluck="holiday_date",
			)
			holidays_by_list[holiday_list] = {getdate(d) for d in rows}
		holidays = holidays_by_list.get(holiday_list, set())

		make_up = make_up_days_between(start, end)
		days = {}
		for d, weekdays in weekdays_by_date(employee, start, end).items():
			if d.weekday() not in weekdays and d not in make_up:
				days[d] = "rest"
			elif d in holidays:
				days[d] = "holiday"
			else:
				days[d] = "scheduled"
		out[employee] = days
	return out


def shift_window(employee: str, date) -> tuple[datetime, datetime] | None:
	"""(giờ vào, giờ ra) của ca trong ngày, hoặc `None` nếu ngày đó ngoài lịch tuần.

	Đây là định nghĩa "trong ca / ngoài ca" mà tính năng OT sẽ dùng — khai một chỗ để OT không
	phải phát minh lại khái niệm.
	"""
	if not is_scheduled_day(employee, date):
		return None
	shift = employee_shift(employee, date)
	if not shift:
		return None
	timings = frappe.get_cached_value("Shift Type", shift, ["start_time", "end_time"])
	if not timings or timings[0] is None or timings[1] is None:
		return None
	on = getdate(date)
	return (
		datetime.combine(on, time.min) + timings[0],
		datetime.combine(on, time.min) + timings[1],
	)
