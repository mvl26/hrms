# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt
"""Bảng chấm công tháng — read-only monthly timekeeping sheet.

Pivots by employee x day-of-month. Each cell is the mã công for that day:
- a real Attendance record → its code (or morning/afternoon codes, e.g. "X/P");
- otherwise a calendar marker derived (NOT stored) from the employee's data:
  `-` on a weekly-off (rest day) or after the relieving date, `NL` on a public holiday.

Totals columns sum per category: Công = actual worked công (Σ work_fraction), and the unworked
remainder of each half goes to that code's own category — or to Vắng when the code is itself a
"Công" code that only covers half a day (1/2X), so every attended day still adds up to a full công.
Read-only: never writes, so it is safe against payroll and existing data.
"""

from calendar import monthrange

import frappe
from frappe import _
from frappe.utils import cint, flt, getdate
from frappe.utils.nestedset import get_descendants_of

from erpnext.setup.doctype.employee.employee import get_holiday_list_for_employee

from hrms.hr.attendance_legend import legend_html, legend_row

Filters = frappe._dict

# display-only markers derived from the calendar, not Attendance Code master records
MARKER_TERMINATED = "-"  # after relieving_date — HR convention: rest-day dash
MARKER_NOT_JOINED = "-"  # before date_of_joining — same dash: chưa thuộc biên chế ngày đó
MARKER_WEEKLY_OFF = "-"  # nghỉ hàng tuần (CN/T7) — HR convention: rest-day dash
MARKER_HOLIDAY = "NL"  # ngày nghỉ lễ có lương — kept distinct so paid holidays stay visible

# Loại nhận phần không đi làm của một mã thuộc loại "Công" (mã V cũng thuộc loại này)
CATEGORY_UNEXCUSED = "Vắng"

# Nghỉ lễ hưởng lương — suy từ Holiday List (không phải Attendance Code), đếm riêng một cột
CATEGORY_HOLIDAY = "Nghỉ lễ"

# "Tổng công" = SỐ NGÀY ĐƯỢC TRẢ LƯƠNG (đi làm + mọi nghỉ có lương: P/Ô/Cô/TS/T/NB/N). Cột chủ đạo,
# in đậm. KHÔNG gồm Vắng / Không lương (không lương) và Nghỉ lễ (đếm riêng nếu cần).
TOTAL_PAID = "Tổng công"

# Cột tổng hợp hiển thị trên report (theo yêu cầu — gọn). Ốm/chăm con ốm/nghỉ bù đã gộp vào Tổng công
# nên không có cột riêng; Vắng/Nghỉ lễ chỉ còn ký hiệu trong lưới. (category nội bộ, nhãn hiển thị)
REPORT_CATEGORIES = [
	("Phép", "Phép năm"),
	("Thai sản", "Thai sản"),
	("Không lương", "Không lương"),
	("Tai nạn LĐ", "Tai nạn lao động"),
	("Việc riêng", "Nghỉ riêng"),
]


# ── Mã màu bảng công (THUẦN HIỂN THỊ) ────────────────────────────────────────────────────────
# Một nguồn màu duy nhất: report on-screen (formatter JS) và print format (Jinja) đều suy màu từ đây.
# Không đụng dữ liệu/status/payroll — chỉ tô nền để trạng thái mỗi ngày đọc được bằng mắt.

# category của Attendance Code → state màu. Mã có work_fraction ∈ (0,1) (1/2P, 1/2K, 1/2X) được
# xử lý riêng thành "half" TRƯỚC khi tra bảng này, nên ở đây chỉ cần map theo category.
CATEGORY_STATE = {
	"Công": "work",
	"Phép": "leave",
	"Việc riêng": "leave",  # nghỉ hiếu hỉ có lương — mặc định gộp cùng phép (vàng)
	"Ốm": "sick",
	"Thai sản": "sick",
	"Tai nạn LĐ": "sick",
	"Nghỉ bù": "comp",
	"Không lương": "unpaid",
	"Vắng": "absent",
	CATEGORY_HOLIDAY: "holiday",  # "Nghỉ lễ" — marker lịch, không phải Attendance Code
}

# state → nhãn chú giải + màu nền/chữ (cặp cho nền sáng & nền tối của Desk). Thứ tự = thứ tự chú giải.
STATE_STYLE = {
	# nhãn hằng số ở module level: bọc _() sẽ đóng băng bản dịch lúc import; dịch tại nơi render
	"work": {  # nosemgrep
		"label": "Đi làm đủ / công tác",
		"bg": "#d9efdc",
		"fg": "#1d6b34",
		"bg_dark": "#1f3a2a",
		"fg_dark": "#83dc9d",
	},
	# nhãn hằng số ở module level: bọc _() sẽ đóng băng bản dịch lúc import; dịch tại nơi render
	"half": {  # nosemgrep
		"label": "Làm nửa ngày",
		"bg": "#e8dcf7",
		"fg": "#6b3fb0",
		"bg_dark": "#312145",
		"fg_dark": "#c6aaf2",
	},
	# nhãn hằng số ở module level: bọc _() sẽ đóng băng bản dịch lúc import; dịch tại nơi render
	"leave": {  # nosemgrep
		"label": "Nghỉ phép / việc riêng",
		"bg": "#fbedc4",
		"fg": "#8a6410",
		"bg_dark": "#3d3416",
		"fg_dark": "#e8ca6b",
	},
	# nhãn hằng số ở module level: bọc _() sẽ đóng băng bản dịch lúc import; dịch tại nơi render
	# nosemgrep
	"sick": {
		"label": "Ốm / thai sản / TNLĐ",
		"bg": "#fbe0cc",
		"fg": "#a54e18",
		"bg_dark": "#3f2a19",
		"fg_dark": "#f2ac7c",
	},
	# nhãn hằng số ở module level: bọc _() sẽ đóng băng bản dịch lúc import; dịch tại nơi render
	# nosemgrep
	"absent": {
		"label": "Vắng",
		"bg": "#f7d3d3",
		"fg": "#b32626",
		"bg_dark": "#3f2020",
		"fg_dark": "#f28d8d",
	},  # nosemgrep
	# nhãn hằng số ở module level: bọc _() sẽ đóng băng bản dịch lúc import; dịch tại nơi render
	"unpaid": {  # nosemgrep
		"label": "Nghỉ không lương",
		"bg": "#ecd7dd",
		"fg": "#8f3a52",
		"bg_dark": "#3a2028",
		"fg_dark": "#e592a6",
	},
	# nhãn hằng số ở module level: bọc _() sẽ đóng băng bản dịch lúc import; dịch tại nơi render
	"comp": {  # nosemgrep
		"label": "Nghỉ bù",
		"bg": "#cfeae5",
		"fg": "#187a6d",
		"bg_dark": "#173430",
		"fg_dark": "#74d3c5",
	},
	# nhãn hằng số ở module level: bọc _() sẽ đóng băng bản dịch lúc import; dịch tại nơi render
	"holiday": {  # nosemgrep
		"label": "Nghỉ lễ (có lương)",
		"bg": "#d3e3f7",
		"fg": "#245fa0",
		"bg_dark": "#1c2c40",
		"fg_dark": "#8fbcee",
	},
	# nhãn hằng số ở module level: bọc _() sẽ đóng băng bản dịch lúc import; dịch tại nơi render
	"off": {  # nosemgrep
		"label": "Nghỉ tuần / nghỉ việc",
		"bg": "#eae8e2",
		"fg": "#918d84",
		"bg_dark": "#2a2924",
		"fg_dark": "#9c988e",
	},
}


def day_state(symbol: str, code_map: dict) -> str | None:
	"""State màu của một ô bảng công (thuần hiển thị; màu tra ở STATE_STYLE).

	Ưu tiên: **có phần đi làm nửa buổi → 'half'** (bắt 1/2P, 1/2K, 1/2X và ô ghép có nửa đi làm),
	rồi tới marker lịch ('-'/'NL'), rồi category của mã. Trả None cho ô trống (không tô)."""
	if not symbol:
		return None
	if symbol == MARKER_WEEKLY_OFF:  # "-" (nghỉ tuần / sau nghỉ việc)
		return "off"
	if symbol == MARKER_HOLIDAY:  # "NL"
		return "holiday"
	# Mã đơn trước — vài mã (1/2P, 1/2K) tự chứa dấu "/" nên không được coi là ô ghép.
	c = code_map.get(symbol)
	if c:
		if 0 < flt(c.work_fraction) < 1:  # nửa ngày đi làm
			return "half"
		return CATEGORY_STATE.get(c.category)
	if "/" in symbol:  # ô ghép sáng/chiều, vd "X/P"
		halves = [code_map.get(h) for h in symbol.split("/", 1)]
		if any(h and 0 < flt(h.work_fraction) for h in halves):
			return "half"  # có ít nhất một nửa đi làm
		morning = halves[0]
		return CATEGORY_STATE.get(morning.category) if morning else None
	return None


@frappe.whitelist()
def get_color_map() -> dict:
	"""Bảng màu {state → {label, bg, fg, bg_dark, fg_dark}} cho formatter JS của report.
	Thuần hiển thị; JS chỉ tra màu theo state đã tính sẵn ở server (`_state_<day>`)."""
	return STATE_STYLE


def _cell_code_map() -> dict:
	"""code_map cache trong 1 request — print format gọi cho từng ô nên tránh query lặp lại."""
	cached = getattr(frappe.local, "_bcct_code_map", None)
	if cached is None:
		cached = frappe.local._bcct_code_map = get_code_map()
	return cached


def attendance_cell_style(symbol: str) -> str:
	"""CSS inline (màu nền bản sáng) cho một ô mã công trên print format. Rỗng nếu không tô.
	Phơi làm Jinja method qua hooks.py để bản in dùng chung nguồn màu với report."""
	state = day_state(symbol, _cell_code_map())
	if not state or state not in STATE_STYLE:
		return ""
	s = STATE_STYLE[state]
	return f"background:{s['bg']};color:{s['fg']};"


def attendance_state_styles() -> dict:
	"""STATE_STYLE cho khối chú giải màu trên print format (Jinja method)."""
	return STATE_STYLE


def execute(filters: Filters | None = None) -> tuple:
	filters = frappe._dict(filters or {})
	if not (filters.month and filters.year):
		frappe.throw(_("Please select month and year."))

	year, month = cint(filters.year), cint(filters.month)
	days = monthrange(year, month)[1]

	code_map = get_code_map()
	rows = get_sheet_rows(filters)

	columns = get_columns(days)
	data = _rows_to_report_data(rows, days, code_map)
	# Chú thích ký hiệu ra hai đường: khối chip màu ở `message` (đẹp, chỉ có trên màn hình) và ĐÚNG
	# MỘT dòng cuối bảng (thuần văn bản) để nó theo được vào file Excel — `message` không vào file,
	# mà dòng chỉ thêm lúc xuất thì bị `visible_idx` lọc mất.
	data.append(legend_row())
	return columns, data, legend_html()


def get_code_map() -> dict:
	"""{code: {category, work_fraction, is_paid, maps_to_status, leave_type}} for every Attendance Code."""
	rows = frappe.get_all(
		"Attendance Code",
		fields=["name", "code_name", "category", "work_fraction", "is_paid", "maps_to_status", "leave_type"],
	)
	return {r.name: r for r in rows}


# Loại nghỉ CÓ LƯƠNG (đếm vào Tổng công): mọi mã is_paid=1 KHÔNG thuộc mấy loại này. "Công" chỉ tính
# phần đi làm thực (work_fraction); "Không lương"/"Vắng" không lương → không vào Tổng công.
NON_PAID_LEAVE_CATEGORIES = ("Công", "Không lương", "Vắng")


def is_paid_leave(code) -> bool:
	"""Mã nghỉ CÓ LƯƠNG (Phép/Ốm/Chăm con ốm/Thai sản/TNLĐ/Nghỉ bù/Việc riêng) → phần nghỉ tính đủ công."""
	return bool(code and cint(code.is_paid) and code.category not in NON_PAID_LEAVE_CATEGORIES)


def _company_filter(filters: Filters) -> list | None:
	if not filters.get("company"):
		return None
	companies = [filters.company]
	if filters.get("include_company_descendants"):
		companies += get_descendants_of("Company", filters.company)
	return companies


def get_employees(filters: Filters, start, end) -> list:
	"""Roster to render: everyone employed at some point during the month (joined on/before
	month-end and not relieved before month-start), optionally scoped to a company tree."""
	conds = [["Employee", "date_of_joining", "<=", end]]
	companies = _company_filter(filters)
	if companies:
		conds.append(["Employee", "company", "in", companies])
	return frappe.get_all(
		"Employee",
		filters=conds,
		or_filters=[
			["Employee", "relieving_date", "is", "not set"],
			["Employee", "relieving_date", ">=", start],
		],
		fields=["name", "employee_name", "holiday_list", "relieving_date", "date_of_joining"],
		order_by="employee_name",
	)


def get_attendances(filters: Filters, start, end) -> dict:
	"""{employee: {day-of-month: attendance}} for the month.

	Only submitted Attendance (docstatus==1) is counted — the same rows payroll reads. A draft
	may never be submitted (or gets cancelled), so counting it would let a frozen sheet diverge
	from the Salary Slip; the upstream Monthly Attendance Sheet report filters the same way."""
	q = {"attendance_date": ["between", [start, end]], "docstatus": 1}
	companies = _company_filter(filters)
	if companies:
		q["company"] = ["in", companies]

	rows = frappe.get_all(
		"Attendance",
		filters=q,
		fields=[
			"employee",
			"attendance_date",
			"status",
			"leave_type",
			"custom_attendance_code",
			"custom_morning_code",
			"custom_afternoon_code",
		],
	)
	by_emp = {}
	for a in rows:
		by_emp.setdefault(a.employee, {})[getdate(a.attendance_date).day] = a
	return by_emp


def get_holidays(employees: list, start, end) -> dict:
	"""{employee: {day-of-month: is_weekly_off}} from each employee's resolved Holiday List."""
	cache = {}
	result = {}
	for e in employees:
		hl = e.holiday_list or get_holiday_list_for_employee(e.name, raise_exception=False)
		if not hl:
			result[e.name] = {}
			continue
		if hl not in cache:
			rows = frappe.get_all(
				"Holiday",
				filters={
					"parent": hl,
					"parenttype": "Holiday List",
					"holiday_date": ["between", [start, end]],
				},
				fields=["holiday_date", "weekly_off"],
			)
			cache[hl] = {getdate(r.holiday_date).day: cint(r.weekly_off) for r in rows}
		result[e.name] = cache[hl]
	return result


def get_columns(days: int) -> list:
	columns = [
		{
			"fieldname": "employee",
			"label": _("Mã NV"),
			"fieldtype": "Link",
			"options": "Employee",
			"width": 110,
		},
		{"fieldname": "employee_name", "label": _("Nhân viên"), "fieldtype": "Data", "width": 180},
	]
	for day in range(1, days + 1):
		columns.append({"fieldname": f"day_{day}", "label": str(day), "fieldtype": "Data", "width": 45})
	# Cột chủ đạo: Tổng công = số ngày được trả lương (in đậm ở formatter JS + bản in)
	columns.append(
		{"fieldname": "tong_cong", "label": _(TOTAL_PAID), "fieldtype": "Float", "width": 90, "precision": 2}
	)
	for idx, (_cat, label) in enumerate(REPORT_CATEGORIES):
		columns.append(
			{"fieldname": f"cat_{idx}", "label": _(label), "fieldtype": "Float", "width": 85, "precision": 2}
		)
	columns.append(
		{"fieldname": "lunch_days", "label": _("Số buổi ăn trưa"), "fieldtype": "Int", "width": 90}
	)
	return columns


def _resolve_day(att, code_map: dict) -> tuple:
	"""Return (display, morning_code, afternoon_code) for one attendance, mirroring the bridge:
	explicit morning/afternoon win, then a single day code, else reverse-derive from status."""
	morning = att.custom_morning_code or att.custom_attendance_code
	afternoon = att.custom_afternoon_code or att.custom_attendance_code
	if not (morning or afternoon):
		derived = _reverse_code(att.status, att.leave_type, code_map)
		morning = afternoon = derived
	else:
		morning = morning or afternoon
		afternoon = afternoon or morning

	if not morning:
		return "", None, None
	display = morning if morning == afternoon else f"{morning}/{afternoon}"
	return display, morning, afternoon


def _reverse_code(status, leave_type, code_map: dict):
	if not status:
		return None
	for name, r in code_map.items():
		if r.maps_to_status == status and (r.leave_type or None) == (leave_type or None):
			return name
	return None


def get_sheet_rows(filters: Filters) -> list[dict]:
	"""Semantic per-employee rows shared by this report AND the Bảng Công Tháng DocType:
	``{employee, employee_name, days: {day-of-month: symbol}, totals: {category: float}}``.
	Công total = Σ work_fraction x 0.5 (worked-công); the unworked remainder (1 - work_fraction) x 0.5
	of each half lands in that code's category, falling back to Vắng for a half-covering "Công" code.
	This is the single source of timekeeping derivation — consumers must not re-implement it."""
	filters = frappe._dict(filters or {})
	year, month = cint(filters.year), cint(filters.month)
	days = monthrange(year, month)[1]
	start = getdate(f"{year}-{month:02d}-01")
	end = getdate(f"{year}-{month:02d}-{days:02d}")

	code_map = get_code_map()
	employees = get_employees(filters, start, end)
	attendances = get_attendances(filters, start, end)
	holidays = get_holidays(employees, start, end)

	from hrms.vn_payroll.lunch import lunch_days_map  # nguồn duy nhất; 1 truy vấn gộp cho cả bảng

	lunch_by_emp = lunch_days_map([e.name for e in employees], start, end)

	rows = []
	for e in employees:
		emp_att = attendances.get(e.name, {})
		emp_hol = holidays.get(e.name, {})
		relieving = getdate(e.relieving_date) if e.relieving_date else None
		joining = getdate(e.date_of_joining) if e.date_of_joining else None
		day_syms = {}
		totals = {}

		for day in range(1, days + 1):
			d = getdate(f"{year}-{month:02d}-{day:02d}")
			# priority: đã ngừng việc > bản ghi Attendance > ngày lễ/CN > (trước khi vào làm →) trống
			if relieving and d > relieving:
				day_syms[day] = MARKER_TERMINATED
				continue
			att = emp_att.get(day)
			if att:
				display, morning, afternoon = _resolve_day(att, code_map)
				day_syms[day] = display
				for half in (morning, afternoon):
					c = code_map.get(half)
					if not c:
						continue
					wf = flt(c.work_fraction)
					totals["Công"] = totals.get("Công", 0.0) + wf * 0.5  # công thực đi làm
					totals[TOTAL_PAID] = totals.get(TOTAL_PAID, 0.0) + wf * 0.5  # phần đi làm luôn có lương
					rest = (1 - wf) * 0.5  # phần không đi làm của nửa buổi này
					if rest:
						# Mã nghỉ (P, Ô, 1/2P…) ghi vào đúng loại của nó. Mã thuộc loại "Công" mà
						# không làm đủ buổi (1/2X = đi làm thiếu giờ) không nói nửa kia nghỉ vì gì, nên
						# nửa đó là nghỉ không lý do -> Vắng. Thiếu nhánh này thì ngày 1/2X chỉ quy ra
						# 0.5 công và dòng bảng công không cân về số ngày công của tháng.
						bucket = c.category if c.category != "Công" else CATEGORY_UNEXCUSED
						totals[bucket] = totals.get(bucket, 0.0) + rest
						# Nghỉ CÓ LƯƠNG (P/Ô/Cô/TS/T/NB/N) tính vào Tổng công = số ngày được trả lương.
						if is_paid_leave(c):
							totals[TOTAL_PAID] = totals.get(TOTAL_PAID, 0.0) + rest
			elif joining and d < joining:
				# chưa vào làm → cùng dấu với ngày sau khi nghỉ việc. Để trống thì mơ hồ: HR không
				# phân biệt được "chưa vào làm" với "quên chấm công", trong khi payroll đã loại các
				# ngày này khỏi payment_days theo date_of_joining.
				day_syms[day] = MARKER_NOT_JOINED
			elif day in emp_hol:
				if emp_hol[day]:
					day_syms[day] = MARKER_WEEKLY_OFF  # nghỉ hàng tuần (CN) — không tính công
				else:
					# nghỉ lễ hưởng lương → đếm vào cột "Nghỉ lễ" (nghỉ nhưng vẫn hưởng lương)
					day_syms[day] = MARKER_HOLIDAY
					totals[CATEGORY_HOLIDAY] = totals.get(CATEGORY_HOLIDAY, 0.0) + 1.0

		rows.append(
			{
				"employee": e.name,
				"employee_name": e.employee_name,
				"days": day_syms,
				"totals": totals,
				"lunch_days": lunch_by_emp.get(e.name, 0),  # số buổi ăn trưa (nguồn duy nhất)
			}
		)
	return rows


def _rows_to_report_data(rows: list[dict], days: int, code_map: dict) -> list:
	"""Map the shared semantic rows onto this report's flat column layout (day_N / tong_cong / cat_i).

	Also stashes a hidden ``_state_<day>`` (màu state, thuần hiển thị) per day for the JS formatter —
	not a rendered column, just metadata carried on the row so classification stays in Python."""
	data = []
	for r in rows:
		totals = r["totals"]
		row = {
			"employee": r["employee"],
			"employee_name": r["employee_name"],
			"lunch_days": cint(r.get("lunch_days")),
			"tong_cong": flt(totals.get(TOTAL_PAID)),
			**{f"cat_{i}": flt(totals.get(cat)) for i, (cat, _label) in enumerate(REPORT_CATEGORIES)},
		}
		for day, sym in r["days"].items():
			row[f"day_{day}"] = sym
			state = day_state(sym, code_map)
			if state:
				row[f"_state_{day}"] = state
		data.append(row)
	return data
