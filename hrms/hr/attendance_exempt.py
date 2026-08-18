# Copyright (c) 2026, Miyano Việt Nam.
"""Miyano — nhân viên MIỄN CHẤM CÔNG: ngày làm việc tự sinh đủ công.

Một số người (giám đốc, người có giờ làm không cố định) không quẹt thẻ, nhưng công của họ là công
khoán theo tháng. Không có module này thì `mark_absent_for_dates_with_no_attendance` chấm họ VẮNG cả
tháng và `payment_days` bị trừ sạch.

Module giữ TOÀN BỘ luật; các điểm móc trong shift_type / attendance / business_trip chỉ gọi vào đây.
Ngày tự sinh ghi bằng MÃ CÔNG (`X`) — `status` / `leave_type` / `custom_work_credit` do cầu nối
`Attendance.apply_attendance_code_bridge` suy ra, không đặt tay (một nguồn sự thật).

Xem `docs/spec/attendance-exempt-employees.md`.
"""

import frappe
from frappe import _
from frappe.utils import add_days, cint, get_last_day, getdate

from erpnext.setup.doctype.employee.employee import is_holiday

EXEMPT_CODE = "X"
# Cửa sổ lùi tối đa của lượt quét tự động — CHỐT CHẶN CHI PHÍ, không phải luật nghiệp vụ: bật cờ cho
# người vào làm từ 2020 mà không giới hạn thì mỗi giờ job lại cày sáu năm lịch sử. Bù xa hơn thì
# dùng `generate_for_month`.
BACKFILL_DAYS = 31

EMPLOYEE_FIELDS = [
	"name",
	"status",
	"company",
	"default_shift",
	"date_of_joining",
	"relieving_date",
	"custom_exempt_from_checkin",
	"custom_exempt_from_checkin_from",
]


def exempt_fields_installed() -> bool:
	"""Fixtures đã lên site chưa. Chưa thì mọi thứ im lặng và hành vi cũ y nguyên — cùng khuôn
	phòng thủ với `Attendance.get_split_shift_config`."""
	return frappe.get_meta("Employee").has_field("custom_exempt_from_checkin")


def is_exempt(employee: str, date) -> bool:
	"""Nhân viên này có được miễn chấm công vào NGÀY này không."""
	if not employee or not exempt_fields_installed():
		return False
	row = frappe.db.get_value("Employee", employee, EMPLOYEE_FIELDS, as_dict=True)
	if not row or not cint(row.custom_exempt_from_checkin) or row.status != "Active":
		return False
	date = getdate(date)
	start = row.custom_exempt_from_checkin_from or row.date_of_joining
	if start and date < getdate(start):
		return False
	if row.relieving_date and date > getdate(row.relieving_date):
		return False
	return True


def exempt_employees() -> list:
	"""Mọi nhân viên đang làm việc có bật cờ miễn chấm công."""
	if not exempt_fields_installed():
		return []
	return frappe.get_all(
		"Employee",
		filters={"status": "Active", "custom_exempt_from_checkin": 1},
		fields=EMPLOYEE_FIELDS,
	)


def fill_full_day(employee: str, date) -> str | None:
	"""Sinh MỘT ngày công đủ (mã X) cho người miễn chấm công. Trả None nếu không được phép sinh.

	Thứ tự lá chắn là có chủ ý: rẻ trước, đắt sau, và "đã có dữ liệu" luôn thắng."""
	from hrms.hr.doctype.attendance_request.attendance_request_miyano import reapply_attendance_request
	from hrms.hr.period_lock import is_period_locked

	date = getdate(date)
	if not is_exempt(employee, date):
		return None
	if frappe.db.exists(
		"Attendance", {"employee": employee, "attendance_date": date, "docstatus": ["<", 2]}
	):
		return None  # người thật (hoặc kênh khác) đã quyết định ngày này
	if is_holiday(employee, date, raise_exception=False):
		return None  # T7/CN/lễ: không ai có công, kể cả người miễn chấm công
	if is_period_locked(employee, date):
		return None  # kỳ đã chốt là đóng băng
	if reapply_attendance_request(employee, date):
		return None  # đơn đã duyệt dựng lại ngày công theo đơn — đơn thắng

	row = frappe.db.get_value("Employee", employee, ["company", "default_shift"], as_dict=True)
	doc = frappe.get_doc(
		{
			"doctype": "Attendance",
			"employee": employee,
			"attendance_date": date,
			"company": row.company,
			"shift": row.default_shift,
			"custom_attendance_code": EXEMPT_CODE,
			"custom_auto_filled": 1,
		}
	)
	doc.flags.ignore_permissions = True
	doc.insert(ignore_permissions=True)
	doc.submit()
	doc.add_comment("Comment", _("Tự sinh: nhân viên miễn chấm công (full công)"))
	return doc.name


def process_exempt_employees():
	"""Scheduler `hourly_long`: lấp đầy ngày công cho MỌI người có cờ, kể cả người không được phân
	ca tháng đó (phân ca ở Miyano cấp theo từng tháng, quên là mất công cả tháng)."""
	if not exempt_fields_installed():
		return
	end = add_days(getdate(), -1)  # hôm nay chưa hết thì chưa kết luận
	floor = add_days(end, -BACKFILL_DAYS)
	for emp in exempt_employees():
		start = getdate(emp.custom_exempt_from_checkin_from or emp.date_of_joining or floor)
		if start < floor:
			start = floor
		stop = end
		if emp.relieving_date and getdate(emp.relieving_date) < stop:
			stop = getdate(emp.relieving_date)
		day = start
		while day <= stop:
			fill_full_day(emp.name, day)
			day = add_days(day, 1)
		# giữ tiến độ giữa các nhân viên, y như `process_auto_attendance`
		frappe.db.commit()  # nosemgrep


@frappe.whitelist()
def generate_for_month(month, year, employee: str | None = None) -> int:
	"""Chạy bù cả tháng — cho người bật cờ giữa chừng, hoặc sau khi huỷ chốt kỳ để sửa.

	Trả về SỐ NGÀY đã sinh để HR đối chiếu; không sinh ngày hôm nay và tương lai."""
	frappe.only_for(("HR Manager", "System Manager"))
	start = getdate(f"{cint(year)}-{cint(month):02d}-01")
	end = get_last_day(start)
	yesterday = add_days(getdate(), -1)
	if end > yesterday:
		end = yesterday
	rows = [frappe._dict(name=employee)] if employee else exempt_employees()
	created = 0
	for emp in rows:
		day = start
		while day <= end:
			if fill_full_day(emp.name, day):
				created += 1
			day = add_days(day, 1)
	return created
