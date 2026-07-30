# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt
"""Bước SOÁT CÔNG — mắt xích còn thiếu giữa "máy sinh công" và "chốt công".

Trước bước này, HR muốn sửa một ngày công phải Cancel → Amend từng bản ghi (không field nào cho
`allow_on_submit`), nên trên thực tế không ai sửa. Module này cho HR nhìn cả tháng dưới dạng lưới,
tô đỏ những ô đáng ngờ, và sửa ngay tại chỗ — qua **đúng một cửa ghi** duy nhất.

Hai nguyên tắc:

1. **Không dựng logic suy diễn thứ hai.** Lưới lấy nguyên `get_sheet_rows` mà report và Bảng Công
   Tháng đang dùng; ở đây chỉ thêm phần đánh cờ bất thường.
2. **Mọi thay đổi đi qua `apply_correction`**, luôn kèm lý do và luôn đẻ ra một vết trong
   `Attendance Correction Log`. Không mở `allow_on_submit` trên form Attendance — mở ra là có đường
   ghi thứ hai không ai kiểm soát.
"""

import json

import frappe
from frappe import _
from frappe.utils import cint, flt, getdate

from hrms.hr.report.monthly_attendance_report.monthly_attendance_report import (
	MARKER_HOLIDAY,
	MARKER_WEEKLY_OFF,
	get_sheet_rows,
)

# Cờ bất thường — ô nào mang cờ thì HR phải nhìn tận mắt trước khi chốt công.
FLAG_SINGLE_PUNCH = "SINGLE_PUNCH"  # có bản ghi nhưng < 2 lượt chấm → giờ ra/vào không đáng tin
FLAG_SHORT_HOURS = "SHORT_HOURS"  # đi làm nhưng không đủ số giờ tối thiểu (mã 1/2X)
FLAG_NO_RECORD = "NO_RECORD"  # ngày làm việc mà không có bản ghi công nào
FLAG_CHECKIN_ON_HOLIDAY = "CHECKIN_ON_HOLIDAY"  # ngày nghỉ nhưng có người chấm công
FLAG_ABSENT = "ABSENT"  # vắng không lý do

FLAG_LABEL = {
	FLAG_SINGLE_PUNCH: _("Chỉ có 1 lượt chấm"),
	FLAG_SHORT_HOURS: _("Thiếu giờ so với quy định"),
	FLAG_NO_RECORD: _("Ngày làm việc không có bản ghi"),
	FLAG_CHECKIN_ON_HOLIDAY: _("Ngày nghỉ nhưng có chấm công"),
	FLAG_ABSENT: _("Vắng không lý do"),
}

SHORT_HOURS_CODE = "1/2X"
ABSENT_CODE = "V"
# Ô nghỉ theo lịch. KHÔNG gộp ô trống ("") vào đây: ô trống nghĩa là ngày làm việc mà không có bản
# ghi công nào — chính là thứ `NO_RECORD` phải bắt. (Ngày ngoài thời gian làm việc của nhân viên
# cũng cho ô trống, nên `get_review_grid` phải loại chúng bằng ngày vào làm / ngày nghỉ việc.)
REST_MARKERS = (MARKER_WEEKLY_OFF, MARKER_HOLIDAY)


def anomaly_flags(symbol: str, punches: int, has_record: bool, is_rest_day: bool) -> list[str]:
	"""Cờ của MỘT ô trong lưới. Thuần logic, không chạm DB — test được trực tiếp.

	`symbol` là ký hiệu report đã suy ra cho ngày đó, `punches` là số lượt chấm gắn vào ngày,
	`has_record` cho biết có Attendance đã submit hay không, `is_rest_day` là ngày nghỉ/lễ."""
	flags = []
	if is_rest_day:
		if punches:
			flags.append(FLAG_CHECKIN_ON_HOLIDAY)
		return flags

	if not has_record:
		flags.append(FLAG_NO_RECORD)
		return flags

	if symbol == SHORT_HOURS_CODE:
		flags.append(FLAG_SHORT_HOURS)
	if symbol == ABSENT_CODE:
		flags.append(FLAG_ABSENT)
	if punches == 1:
		flags.append(FLAG_SINGLE_PUNCH)
	return flags


def punch_counts(employees: list, start, end) -> dict:
	"""{employee: {ngày: số lượt chấm}} — đếm theo NGÀY CHẤM, không theo bản ghi công, để bắt được
	cả lượt chấm rơi vào ngày nghỉ (những lượt đó không bao giờ được gắn vào Attendance)."""
	if not employees:
		return {}
	rows = frappe.db.sql(
		"""SELECT employee, DATE(time) AS d, COUNT(*) AS n
		   FROM `tabEmployee Checkin`
		   WHERE employee IN %(emps)s AND DATE(time) BETWEEN %(start)s AND %(end)s
		   GROUP BY employee, DATE(time)""",
		{"emps": employees, "start": start, "end": end},
		as_dict=True,
	)
	out = {}
	for r in rows:
		out.setdefault(r.employee, {})[getdate(r.d).day] = cint(r.n)
	return out


def attendance_names(employees: list, start, end) -> dict:
	"""{employee: {ngày: tên Attendance}} cho những bản ghi đã submit — để lưới biết sửa cái nào."""
	if not employees:
		return {}
	rows = frappe.get_all(
		"Attendance",
		filters={"employee": ["in", employees], "attendance_date": ["between", [start, end]], "docstatus": 1},
		fields=["name", "employee", "attendance_date"],
	)
	out = {}
	for r in rows:
		out.setdefault(r.employee, {})[getdate(r.attendance_date).day] = r.name
	return out


@frappe.whitelist()
def get_review_grid(filters=None) -> dict:
	"""Lưới soát công của một tháng: hàng nhân viên x cột ngày, kèm cờ bất thường từng ô.

	Trả `{rows: [...], flags: {employee: {day: [flag]}}, flag_labels: {...}}`. `rows` chính là
	`get_sheet_rows` — cùng một nguồn suy diễn với report và Bảng Công Tháng."""
	if isinstance(filters, str):
		filters = json.loads(filters)
	filters = frappe._dict(filters or {})

	rows = get_sheet_rows(filters)
	if not rows:
		return {"rows": [], "flags": {}, "flag_labels": FLAG_LABEL, "days_in_month": 0}

	from calendar import monthrange

	year, month = cint(filters.year), cint(filters.month)
	last = monthrange(year, month)[1]
	start = getdate(f"{year}-{month:02d}-01")
	end = getdate(f"{year}-{month:02d}-{last:02d}")

	employees = [r["employee"] for r in rows]
	punches = punch_counts(employees, start, end)
	names = attendance_names(employees, start, end)
	employment = {
		e.name: e
		for e in frappe.get_all(
			"Employee",
			filters={"name": ["in", employees]},
			fields=["name", "date_of_joining", "relieving_date"],
		)
	}

	flags = {}
	for row in rows:
		emp = row["employee"]
		emp_punch, emp_names = punches.get(emp, {}), names.get(emp, {})
		emp_job = employment.get(emp) or frappe._dict()
		day_flags = {}
		# Duyệt TRỌN tháng, không duyệt `row["days"]`: report chỉ đặt khoá cho ngày có bản ghi, ngày
		# lễ/CN, hoặc ngày ngoài thời gian làm việc. Ngày làm việc mà thiếu bản ghi thì KHÔNG có khoá
		# nào cả — duyệt theo khoá là vĩnh viễn không thấy nó, tức cờ NO_RECORD không bao giờ nổi.
		for day in range(1, last + 1):
			symbol = row["days"].get(day, "")
			d = getdate(f"{year}-{month:02d}-{day:02d}")
			# ngoài thời gian làm việc thì ô trống là đương nhiên, không phải thiếu bản ghi
			outside = (emp_job.date_of_joining and d < getdate(emp_job.date_of_joining)) or (
				emp_job.relieving_date and d > getdate(emp_job.relieving_date)
			)
			f = anomaly_flags(
				symbol,
				emp_punch.get(day, 0),
				bool(emp_names.get(day)),
				symbol in REST_MARKERS or bool(outside),
			)
			if f:
				day_flags[day] = f
		row["attendance_names"] = emp_names
		if day_flags:
			flags[emp] = day_flags

	# `days_in_month` để giao diện vẽ TRỌN tháng: `row["days"]` không có khoá cho ngày thiếu bản ghi,
	# vẽ theo nó thì đúng những ô cần soát nhất lại không có chỗ để hiện.
	return {"rows": rows, "flags": flags, "flag_labels": FLAG_LABEL, "days_in_month": last}


def payroll_snapshot(doc) -> dict:
	"""Ảnh chụp các field payroll đọc + mã công — dùng cho hai đầu của một vết điều chỉnh."""
	return {
		"custom_attendance_code": doc.get("custom_attendance_code"),
		"status": doc.get("status"),
		"leave_type": doc.get("leave_type"),
		"half_day_status": doc.get("half_day_status"),
	}


@frappe.whitelist()
def apply_correction(attendance: str, code: str, reason: str | None = None) -> dict:
	"""Đổi mã công của MỘT ngày đã submit, cập nhật đúng các field payroll, và ghi vết.

	Đây là cửa ghi DUY NHẤT của bước soát. Attendance đã submit nên không field nào sửa được qua
	đường thường; ta chạy lại cầu nối mã công rồi `db_set` kết quả — cùng bộ field mà một lần nhập
	tay hợp lệ sẽ đặt, không hơn."""
	if not reason or not reason.strip():
		frappe.throw(_("Phải nhập lý do điều chỉnh."))
	if not frappe.db.exists("Attendance Code", code):
		frappe.throw(_("Mã công {0} không tồn tại.").format(code))

	doc = frappe.get_doc("Attendance", attendance)
	doc.check_permission("write")

	from hrms.hr.period_lock import guard_period_not_locked

	guard_period_not_locked(doc)

	before = payroll_snapshot(doc)

	doc.custom_attendance_code = code
	doc.custom_morning_code = None
	doc.custom_afternoon_code = None
	doc.apply_attendance_code_bridge()
	# Half Day do mã dẫn dắt mà không có đơn nghỉ: đi đúng đường native (check_leave_record) —
	# nửa kia là vắng không phép, trừ 0,5 qua half-absent.
	if doc.status == "Half Day" and not doc.leave_type:
		doc.half_day_status = "Absent"

	after = payroll_snapshot(doc)
	after["custom_work_credit"] = flt(doc.get("custom_work_credit"))

	frappe.db.set_value(
		"Attendance",
		doc.name,
		{
			"custom_attendance_code": doc.custom_attendance_code,
			"custom_morning_code": None,
			"custom_afternoon_code": None,
			"custom_work_credit": doc.get("custom_work_credit"),
			"status": doc.status,
			"leave_type": doc.leave_type,
			"half_day_status": doc.half_day_status,
		},
	)

	from hrms.hr.doctype.attendance_correction_log.attendance_correction_log import log_correction

	log = log_correction(doc, before, after, reason.strip())
	return {"attendance": doc.name, "log": log, "before": before, "after": after}


@frappe.whitelist()
def apply_corrections_bulk(corrections) -> dict:
	"""Áp nhiều điều chỉnh trong một lượt. `corrections` là list `{attendance, code, reason}`."""
	if isinstance(corrections, str):
		corrections = json.loads(corrections)
	results = [apply_correction(c["attendance"], c["code"], c.get("reason")) for c in corrections]
	return {"applied": len(results), "results": results}
