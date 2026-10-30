# Copyright (c) 2026, Miyano Việt Nam.
from calendar import monthrange
from datetime import datetime

import frappe
from frappe import _
from frappe.query_builder.functions import Extract
from frappe.utils import cint, flt, get_datetime, getdate, time_diff_in_hours
from frappe.utils.nestedset import get_descendants_of

LUNCH_BREAK_HOURS = 1.5
# Chỉ là giá trị dự phòng khi không suy được giờ từ ca — KHÔNG phải chính sách. Giờ định mức thật
# lấy từ ca của từng ngày, xem `work_schedule.standard_hours_between`.
STANDARD_HOURS_PER_DAY = 8.0
FULL_DAY_STATUSES = ("Present", "Work From Home")

# Ngày đã chấm là nghỉ thì dù có punch lẻ cũng không tính là ngày làm việc ở văn phòng.
NON_PRESENCE_STATUSES = ("Absent", "On Leave")

# Ngày làm việc bình thường TẠI VĂN PHÒNG. `Work From Home` (mã `W` làm tại nhà, `CT` đi công tác)
# không nằm ở đây; những nơi tính giờ theo giấy tờ thêm nó vào riêng (xem `off_site_fraction`).
# Nghỉ lễ / nghỉ tuần không có bản ghi Attendance nào nên tự rơi ra ngoài.
OFFICE_STATUSES = ("Present", "Half Day")


def compute_net_hours(status, in_time, out_time, working_hours, is_split=False):
	"""Giờ làm net của một ngày: gross (out-in hoặc working_hours) trừ nghỉ trưa theo status.
	Với ca tách sáng/chiều (is_split) thì working_hours ĐÃ là net (đã loại trưa) -> dùng thẳng."""
	if is_split:
		return max(round(flt(working_hours), 2), 0.0)
	if in_time and out_time:
		gross = flt(time_diff_in_hours(out_time, in_time))
	else:
		gross = flt(working_hours)

	if gross <= 0:
		return 0.0

	if status in FULL_DAY_STATUSES:
		return max(round(gross - LUNCH_BREAK_HOURS, 2), 0.0)
	if status == "Half Day":
		return round(gross, 2)
	return 0.0


def get_lunch_window_map():
	"""{ca: khung nghỉ trưa} — cùng luật với bộ chấm mã công (`resolve_lunch_window`).

	Đọc phòng thủ: hai field này là custom field (fixtures), site chưa migrate thì chưa có.
	"""
	from hrms.hr.doctype.attendance.vn_day_classifier import resolve_lunch_window

	meta = frappe.get_meta("Shift Type")
	if not (meta.has_field("custom_lunch_start") and meta.has_field("custom_lunch_end")):
		return {}

	return {
		shift.name: resolve_lunch_window(shift.custom_lunch_start, shift.custom_lunch_end)
		for shift in frappe.get_all("Shift Type", fields=["name", "custom_lunch_start", "custom_lunch_end"])
	}


def get_split_shift_config_map():
	"""{ca tách buổi: cấu hình khung ca} — cùng nguồn cấu hình với `Attendance.get_split_shift_config`.

	Đọc phòng thủ: cờ tách buổi và bộ field giờ linh hoạt đều là custom field (fixtures); site chưa
	migrate thì chưa có field và câu lọc theo chúng sẽ vỡ. Ca bật cờ nhưng thiếu giờ vào/ra ca thì
	bỏ qua — đúng như bộ chấm mã công, nó trả None và không chấm ngày nào cả.
	"""
	meta = frappe.get_meta("Shift Type")
	if not meta.has_field("custom_split_half_day"):
		return {}

	optional = ("custom_lunch_start", "custom_lunch_end", "custom_flexible_shift", "custom_flex_band_minutes")
	fields = ["name", "start_time", "end_time"] + [f for f in optional if meta.has_field(f)]

	return {
		row.name: row
		for row in frappe.get_all("Shift Type", filters={"custom_split_half_day": 1}, fields=fields)
		if row.start_time and row.end_time
	}


def credited_hours(in_time, out_time, attendance_date, cfg):
	"""Giờ QUY CÔNG của một ngày ca tách buổi: phần có mặt nằm trong khung ca, đã trừ nghỉ trưa.

	Không đọc `Attendance.working_hours` nữa: từ `19617d7` field đó giữ giờ CÓ MẶT thật (không bị
	khung ca cắt), nên lấy nó làm "giờ quy công" thì cột đối chiếu của báo cáo bằng đúng cột giờ có
	mặt và mất sạch ý nghĩa — người ở lại tới 19:30 hiện 10h quy công trong khi bảng chấm công chỉ
	trả 8h. Tính lại bằng chính hàm mà `classify_day` dùng để chấm mã công.
	"""
	from hrms.hr.doctype.attendance.vn_day_classifier import (
		DEFAULT_FLEX_BAND_MINUTES,
		counted_hours,
		resolve_lunch_window,
	)

	if not (in_time and out_time):
		return 0.0

	in_time, out_time = get_datetime(in_time), get_datetime(out_time)
	if out_time <= in_time:
		return 0.0

	lunch_start, lunch_end = resolve_lunch_window(cfg.get("custom_lunch_start"), cfg.get("custom_lunch_end"))
	band = cfg.get("custom_flex_band_minutes")

	return counted_hours(
		in_time,
		out_time,
		day=datetime.combine(getdate(attendance_date), datetime.min.time()),
		start_time=cfg.get("start_time"),
		end_time=cfg.get("end_time"),
		lunch_start=lunch_start,
		lunch_end=lunch_end,
		flexible=bool(cint(cfg.get("custom_flexible_shift"))),
		band_minutes=DEFAULT_FLEX_BAND_MINUTES if band is None else cint(band),
	)


def presence_hours(in_time, out_time, attendance_date, lunch_start=None, lunch_end=None):
	"""Giờ thực sự có mặt: (giờ ra - giờ vào) trừ phần giao với khung nghỉ trưa.

	KHÔNG cắt theo khung ca — ở lại sau giờ tan ca vẫn được tính. Thiếu giờ vào hoặc giờ ra thì
	không xác định được thời gian có mặt → 0.
	"""
	from hrms.hr.doctype.attendance.vn_day_classifier import overlap_hours, resolve_lunch_window

	if not (in_time and out_time):
		return 0.0

	in_time, out_time = get_datetime(in_time), get_datetime(out_time)
	if out_time <= in_time:
		return 0.0

	day = datetime.combine(getdate(attendance_date), datetime.min.time())
	lunch_start, lunch_end = resolve_lunch_window(lunch_start, lunch_end)
	lunch = overlap_hours(in_time, out_time, day + lunch_start, day + lunch_end)
	present = (out_time - in_time).total_seconds() / 3600.0
	return round(max(present - lunch, 0.0), 2)


# ---------------------------------------------------------------------------
# Ngày làm việc theo GIẤY TỜ (không có lượt chấm ở văn phòng)
# ---------------------------------------------------------------------------

# User chốt 2026-10-29: phần ngày có công theo giấy tờ được tính ĐỦ giờ ca — đi công tác, làm tại
# nhà, làm từ xa, quên chấm vẫn là làm việc, chỉ không chấm công ở văn phòng. Đi muộn / về sớm thì
# đã có giờ vào-ra thật nên giữ giờ thật. Nghỉ phép không bao giờ có công theo đường này.
REQUEST_FULL_HOURS_REASONS = frozenset({"Work From Home", "On Duty", "Remote Work", "Missed Punch"})
# Ngày không có Yêu cầu chấm công (Công Tác, nhập tay) nhận ra qua mã: CT / W là làm ngoài văn phòng.
OFF_SITE_WORK_CODES = frozenset({"CT", "W"})


def attendance_request_map(names) -> dict:
	"""{tên Yêu cầu chấm công: reason/half_day/half_day_date} — một truy vấn cho cả bảng."""
	names = sorted({n for n in names or () if n})
	if not names:
		return {}
	return {
		r.name: r
		for r in frappe.get_all(
			"Attendance Request",
			filters={"name": ["in", names]},
			fields=["name", "reason", "half_day", "half_day_date"],
		)
	}


def off_site_fraction(attendance_date, request=None, code=None, morning=None, afternoon=None) -> float:
	"""Phần ngày (0 / 0,5 / 1) có công theo giấy tờ và được tính đủ giờ ca.

	Có Yêu cầu chấm công thì đơn quyết định (nửa ngày → 0,5, còn lại → 1; đi muộn / về sớm → 0).
	Không có đơn thì đọc mã: cả ngày `CT`/`W` → 1, mỗi buổi `CT`/`W` → 0,5."""
	if request:
		if request.get("reason") not in REQUEST_FULL_HOURS_REASONS:
			return 0.0
		half_date = request.get("half_day_date")
		if cint(request.get("half_day")) and half_date and getdate(half_date) == getdate(attendance_date):
			return 0.5
		return 1.0
	if code in OFF_SITE_WORK_CODES:
		return 1.0
	return 0.5 * ((morning in OFF_SITE_WORK_CODES) + (afternoon in OFF_SITE_WORK_CODES))


def with_off_site_hours(presence, fraction, shift_hours) -> float:
	"""Giờ của ngày = giờ có mặt thật + phần theo giấy tờ x giờ ca. Cả ngày theo giấy tờ → đúng giờ ca
	(dấu chấm lẻ nếu có không cộng thêm)."""
	if fraction >= 1:
		return round(flt(shift_hours), 2)
	if fraction <= 0:
		return flt(presence)
	return round(flt(presence) + fraction * flt(shift_hours), 2)


class ShiftHours(dict):
	"""{ca: giờ ca/ngày} nhớ đệm trong một lượt dựng báo cáo (`work_schedule.shift_hours_per_day`)."""

	def __missing__(self, shift):
		from hrms.hr.work_schedule import shift_hours_per_day

		self[shift] = shift_hours_per_day(shift or None)
		return self[shift]


def day_hours(row, presence, requests: dict, shift_hours: ShiftHours) -> float:
	"""Giờ làm của một dòng Attendance (cần `attendance_date`, `shift`, `attendance_request`, ba mã)."""
	fraction = off_site_fraction(
		row.attendance_date,
		requests.get(row.get("attendance_request")),
		row.get("custom_attendance_code"),
		row.get("custom_morning_code"),
		row.get("custom_afternoon_code"),
	)
	if not fraction:
		return presence
	shift = row.get("shift")
	if not shift and row.get("employee"):
		# ngày do đơn sinh ra thường không mang ca (đơn không bắt buộc chọn ca) → ca của ngày đó
		from hrms.hr.work_schedule import employee_shift

		shift = employee_shift(row.employee, row.attendance_date)
	return with_off_site_hours(presence, fraction, shift_hours[shift or ""])


def off_site_fields() -> list[str]:
	"""Field `day_hours` cần — đọc phòng thủ: ba mã công là custom field (fixtures)."""
	meta = frappe.get_meta("Attendance")
	optional = ("custom_attendance_code", "custom_morning_code", "custom_afternoon_code")
	return ["attendance_request", *(f for f in optional if meta.has_field(f))]


def office_day_fraction(status: str | None, leave_type: str | None = None) -> float:
	"""Ngày đó chiếm bao nhiêu phần của một ngày công tại văn phòng.

	Không phải mọi `Half Day` đều là nửa ngày công. Phân biệt bằng `leave_type` — thứ đã có sẵn
	trên chính bản ghi Attendance, không phải tra thêm:

	- **`1/2X` (làm nửa ngày THIẾU GIỜ), `leave_type` rỗng → 1 ngày.** Người đó vẫn đi làm cả ngày,
	  chỉ là thiếu giờ. Chia cho 0,5 thì 4 giờ hoá ra 8h/ngày, CHE MẤT đúng cái mà chỉ số này sinh
	  ra để phát hiện (user chốt 2026-09-14).
	- **`1/2P` / `1/2K` (nghỉ nửa ngày có phép), `leave_type` có giá trị → 0,5 ngày.** Nửa kia là
	  nghỉ hợp lệ, họ chỉ phải làm nửa ngày nên không được tính như người làm cả ngày.

	Nhận biết bằng `leave_type` chứ không liệt kê mã cứng: mã nghỉ nửa ngày mới thêm về sau vẫn
	chạy đúng. Và KHÔNG đụng `custom_work_credit` — đó là số ngày ĐƯỢC TRẢ LƯƠNG (nghỉ không lương
	nửa ngày vẫn đi làm nửa ngày), còn ở đây cần phần ngày CÓ MẶT tại văn phòng."""
	if status != "Half Day":
		return 1.0
	return 0.5 if leave_type else 1.0


def office_hours_map(employees, start, end) -> dict:
	"""{employee: {"hours": tổng giờ có mặt, "days": số ngày}} cho các ngày làm việc TẠI VĂN PHÒNG.

	Mẫu số của "TB giờ/ngày": ngày `Present`/`Half Day` có giờ vào lẫn giờ ra, VÀ (từ 2026-10-29)
	ngày làm theo giấy tờ — công tác / làm tại nhà / làm từ xa / quên chấm — tính đủ giờ ca cho phần
	đơn phủ (`day_hours`). Nghỉ phép (`On Leave`), nghỉ lễ, nghỉ tuần (không có Attendance) không vào.

	Một truy vấn gộp cho cả bảng, cùng lối với `lunch_days_map`."""
	employees = list(employees or [])
	if not employees:
		return {}

	lunch_windows = get_lunch_window_map()
	rows = frappe.get_all(
		"Attendance",
		filters={
			"employee": ["in", employees],
			"attendance_date": ["between", [start, end]],
			"docstatus": 1,
			# `Work From Home` (mã CT / W) vào từ 2026-10-29: ngày làm theo giấy tờ tính đủ giờ ca
			"status": ["in", (*OFFICE_STATUSES, "Work From Home")],
		},
		fields=[
			"employee",
			"attendance_date",
			"status",
			"leave_type",
			"shift",
			"in_time",
			"out_time",
			*off_site_fields(),
		],
	)
	requests = attendance_request_map(r.get("attendance_request") for r in rows)
	shift_hours = ShiftHours()

	totals = {}
	for r in rows:
		lunch_start, lunch_end = lunch_windows.get(r.shift or "", (None, None))
		hours = presence_hours(r.in_time, r.out_time, r.attendance_date, lunch_start, lunch_end)
		hours = day_hours(r, hours, requests, shift_hours)
		if hours <= 0:  # không có giờ vào/ra → không phải ngày ở văn phòng, không kéo TB xuống
			continue
		total = totals.setdefault(r.employee, {"hours": 0.0, "days": 0.0})
		total["hours"] += hours
		total["days"] += office_day_fraction(r.status, r.leave_type)
	return totals


def avg_office_hours(totals: dict | None) -> float:
	"""Giờ làm trung bình một ngày = tổng giờ / số ngày; 0 khi chưa có ngày nào ở văn phòng."""
	if not totals or not totals.get("days"):
		return 0.0
	return round(totals["hours"] / totals["days"], 2)


def format_hours_hm(hours) -> str:
	"""Giờ thập phân -> "8h12" (7,75 giờ là "7h45").

	Lối viết thời lượng của bảng chấm công VN. Không dùng "08:12" vì đọc ra thành giờ đồng hồ
	(8 giờ 12 sáng) chứ không phải "làm 8 tiếng 12 phút". Không có giờ nào thì để trống."""
	minutes = round(flt(hours) * 60)
	if minutes <= 0:
		return ""
	return f"{minutes // 60}h{minutes % 60:02d}"


def get_week_buckets(year, month):
	"""Chia các ngày trong tháng thành tuần dương lịch (T2-CN, ISO), chỉ giữ ngày thuộc tháng."""
	year, month = cint(year), cint(month)
	total_days = monthrange(year, month)[1]

	buckets = {}
	order = []
	for day in range(1, total_days + 1):
		iso_year, iso_week, _weekday = getdate(f"{year}-{month:02d}-{day:02d}").isocalendar()
		key = (iso_year, iso_week)
		if key not in buckets:
			buckets[key] = []
			order.append(key)
		buckets[key].append(day)

	return [{"label": f"{_('Week')} {i}", "days": buckets[key]} for i, key in enumerate(order, start=1)]


def prepare_filters(filters):
	"""Đảm bảo month/year (mặc định tháng hiện tại) và companies (suy từ company)."""
	filters = frappe._dict(filters or {})
	today = getdate()
	filters.month = cint(filters.get("month")) or today.month
	filters.year = cint(filters.get("year")) or today.year

	if not filters.get("companies"):
		company = filters.get("company")
		companies = [company] if company else []
		if company:
			# gồm cả company con (nhất quán với báo cáo chấm công)
			companies.extend(get_descendants_of("Company", company))
		filters.companies = companies

	return filters


def get_net_hours_map(filters):
	"""{employee: {shift: {day_of_month: net_hours}}} cho tháng/năm trong filters."""
	companies = filters.get("companies") or ([filters.get("company")] if filters.get("company") else [])
	if not companies:
		# tránh SQL `company IN ()` (lỗi cú pháp) khi chưa xác định được company
		return {}

	Attendance = frappe.qb.DocType("Attendance")
	query = (
		frappe.qb.from_(Attendance)
		.select(
			Attendance.employee,
			Attendance.shift,
			Extract("day", Attendance.attendance_date).as_("day_of_month"),
			Attendance.status,
			Attendance.attendance_date,
			Attendance.in_time,
			Attendance.out_time,
			Attendance.working_hours,
			*(Attendance[f] for f in off_site_fields()),
		)
		.where(
			(Attendance.docstatus == 1)
			& (Attendance.company.isin(companies))
			& (Extract("month", Attendance.attendance_date) == filters.get("month"))
			& (Extract("year", Attendance.attendance_date) == filters.get("year"))
		)
	)
	if filters.get("employee"):
		query = query.where(Attendance.employee == filters.get("employee"))

	# ca tách sáng/chiều đã lưu working_hours net (đã loại trưa) -> dashboard không trừ trưa lần nữa
	split_shifts = set(frappe.get_all("Shift Type", filters={"custom_split_half_day": 1}, pluck="name"))

	records = query.run(as_dict=True)
	requests = attendance_request_map(d.get("attendance_request") for d in records)
	lunch_windows = get_lunch_window_map()
	shift_hours = ShiftHours()

	hours_map = {}
	for d in records:
		shift = d.shift or ""
		if off_site_fraction(
			d.attendance_date,
			requests.get(d.get("attendance_request")),
			d.get("custom_attendance_code"),
			d.get("custom_morning_code"),
			d.get("custom_afternoon_code"),
		):
			# ngày theo giấy tờ: `working_hours` đã là giờ ĐÃ CỘNG phần đơn → tính lại từ giờ có mặt,
			# cộng phần đơn một lần (dựa vào `working_hours` là cộng hai lần)
			lunch_start, lunch_end = lunch_windows.get(shift, (None, None))
			presence = presence_hours(d.in_time, d.out_time, d.attendance_date, lunch_start, lunch_end)
			net = day_hours(d, presence, requests, shift_hours)
		else:
			net = compute_net_hours(
				d.status, d.in_time, d.out_time, d.working_hours, is_split=shift in split_shifts
			)
		hours_map.setdefault(d.employee, {}).setdefault(shift, {})[d.day_of_month] = net

	return hours_map


def _employee_total(shift_hours):
	return sum(net for days in shift_hours.values() for net in days.values())


def get_hours_by_week(filters):
	"""Tổng giờ làm toàn công ty theo từng tuần trong tháng. -> {labels, values}"""
	filters = prepare_filters(filters)
	hours_map = get_net_hours_map(filters)
	buckets = get_week_buckets(filters.year, filters.month)

	labels, values = [], []
	for bucket in buckets:
		day_set = set(bucket["days"])
		total = 0.0
		for shift_hours in hours_map.values():
			for days in shift_hours.values():
				for day, net in days.items():
					if day in day_set:
						total += net
		labels.append(bucket["label"])
		values.append(round(total, 2))

	return {"labels": labels, "values": values}


def get_hours_by_department(filters):
	"""Tổng giờ làm theo từng phòng ban trong tháng. -> {labels, values}"""
	filters = prepare_filters(filters)
	hours_map = get_net_hours_map(filters)

	employees = list(hours_map.keys())
	dept_of = {}
	if employees:
		for emp in frappe.get_all(
			"Employee", filters={"name": ["in", employees]}, fields=["name", "department"]
		):
			dept_of[emp.name] = emp.department or _("No Department")

	totals = {}
	for emp, shift_hours in hours_map.items():
		dept = dept_of.get(emp, _("No Department"))
		totals[dept] = totals.get(dept, 0.0) + _employee_total(shift_hours)

	labels = list(totals.keys())
	values = [round(totals[d], 2) for d in labels]
	return {"labels": labels, "values": values}


# ---------------------------------------------------------------------------
# Định mức (standard hours = Σ giờ ca của những ngày phải đi làm — xem work_schedule)
# ---------------------------------------------------------------------------


def get_standard_hours(total_days, num_holidays):
	"""Công thức CŨ: 8h x (tổng ngày - số ngày nghỉ). Không còn nơi nào trong app gọi.

	Giữ lại như một phép tính thuần cho ai cần ước lượng nhanh; định mức thật của nhân viên đi qua
	`get_standard_hours_map` / `work_schedule.standard_hours_between`."""
	working_days = max(cint(total_days) - cint(num_holidays), 0)
	return round(STANDARD_HOURS_PER_DAY * working_days, 2)


def get_effective_days_in_month(year, month):
	"""Số ngày dùng tính định mức: cả tháng, nhưng nếu là tháng hiện tại (chưa kết thúc)
	thì chỉ tính tới hôm nay — để KPI giữa tháng không báo mọi người thiếu giờ."""
	year, month = cint(year), cint(month)
	total = monthrange(year, month)[1]
	today = getdate()
	if year == today.year and month == today.month:
		return min(total, today.day)
	return total


def get_standard_hours_map(filters, employees=None):
	"""{employee: giờ định mức} của tháng, theo CA và LỊCH LÀM VIỆC của từng người.

	Trước đây = (số ngày trong tháng - số dòng Holiday List) x 8h. Từ khi ngày nghỉ tuần được gỡ
	khỏi Holiday List, công thức đó tính cả thứ Bảy, Chủ nhật vào định mức và cả công ty bị báo
	thiếu giờ. Nay hỏi thẳng `work_schedule.standard_hours_between` — cùng nguồn với chấm công.

	Tháng hiện tại chỉ tính tới hôm nay (`get_effective_days_in_month`), để KPI giữa tháng không
	báo mọi người thiếu giờ."""
	from hrms.hr.work_schedule import standard_hours_between

	filters = prepare_filters(filters)
	year, month = cint(filters.year), cint(filters.month)
	start = getdate(f"{year}-{month:02d}-01")
	end = getdate(f"{year}-{month:02d}-{get_effective_days_in_month(year, month):02d}")

	if employees:
		emp_filters = {"name": ["in", employees]}
	elif filters.get("companies"):
		emp_filters = {"company": ["in", filters.companies], "status": "Active"}
	else:
		return {}

	return {
		name: standard_hours_between(name, start, end)
		for name in frappe.get_all("Employee", filters=emp_filters, pluck="name")
	}


def get_active_employee_count(filters):
	"""Số nhân sự Active trong các company của filters (mẫu số cho KPI trung bình)."""
	filters = prepare_filters(filters)
	if not filters.get("companies"):
		return 0
	return frappe.db.count("Employee", {"company": ["in", filters.companies], "status": "Active"})


# ---------------------------------------------------------------------------
# KPI number card methods (type Custom -> trả {"value", "fieldtype"})
# ---------------------------------------------------------------------------


def _parse_card_filters(filters):
	if isinstance(filters, str):
		filters = frappe.parse_json(filters)
	if isinstance(filters, list | tuple):
		parsed = {}
		for f in filters:
			if isinstance(f, list | tuple) and len(f) >= 4:
				parsed[f[1]] = f[3]
		filters = parsed
	filters = frappe._dict(filters or {})
	if not filters.get("company"):
		filters.company = frappe.defaults.get_user_default("Company")
	return prepare_filters(filters)


@frappe.whitelist()
def get_total_working_hours_card(filters: str | list | dict | None = None) -> dict:
	frappe.has_permission("Attendance", throw=True)
	filters = _parse_card_filters(filters)
	net_map = get_net_hours_map(filters)
	total = sum(_employee_total(shift_hours) for shift_hours in net_map.values())
	return {"value": round(total, 2), "fieldtype": "Float"}


@frappe.whitelist()
def get_avg_working_hours_card(filters: str | list | dict | None = None) -> dict:
	frappe.has_permission("Attendance", throw=True)
	filters = _parse_card_filters(filters)
	headcount = get_active_employee_count(filters)
	if not headcount:
		return {"value": 0.0, "fieldtype": "Float"}
	net_map = get_net_hours_map(filters)
	total = sum(_employee_total(shift_hours) for shift_hours in net_map.values())
	return {"value": round(total / headcount, 2), "fieldtype": "Float"}


@frappe.whitelist()
def get_under_target_count_card(filters: str | list | dict | None = None) -> dict:
	frappe.has_permission("Attendance", throw=True)
	filters = _parse_card_filters(filters)
	# duyệt MỌI nhân sự Active — người vắng cả tháng (0 giờ) cũng là thiếu giờ
	std_map = get_standard_hours_map(filters)
	if not std_map:
		return {"value": 0, "fieldtype": "Int"}
	net_map = get_net_hours_map(filters)
	count = 0
	for employee, standard in std_map.items():
		actual = _employee_total(net_map.get(employee, {}))
		if actual < standard:
			count += 1
	return {"value": count, "fieldtype": "Int"}
