# Copyright (c) 2026, Miyano Việt Nam.
"""Quét lệch giữa ô **Công** (bảng chấm công / Bảng Công Tháng) và số ngày **phiếu lương** trả, theo
từng bản ghi Attendance. CHỈ ĐỌC — không ghi gì.

Hai bên đọc hai nguồn khác nhau: Công tính từ MÃ CÔNG (`custom_work_credit`), phiếu lương tính từ
`status` / `leave_type` / `half_day_status`. Bản ghi nào để hai nguồn nói ngược nhau (vd mã 1/2P =
Công 1 nhưng nửa kia Absent → lương 0,5) đều hiện ra ở đây, kèm field để biết vì sao.

    bench --site <site> execute hrms.attendance_payroll_consistency.scan \
          --kwargs "{'from_date': '2026-10-01', 'to_date': '2026-10-31'}"

Không so ngày nghỉ BHXH chi trả (ốm, chăm con ốm, thai sản): Công = 0 theo định nghĩa (công ty
không trả) trong khi payroll trả theo tỷ lệ của loại nghỉ — khác nhau là đúng. Không so ngày ngoài
lịch làm việc: bảng công không cộng ngày đó vào Tổng công.
"""

import frappe
from frappe.utils import flt, getdate

FIELDS = [
	"name",
	"employee",
	"employee_name",
	"attendance_date",
	"status",
	"leave_type",
	"half_day_status",
	"modify_half_day_status",
	"leave_application",
	"custom_attendance_code",
	"custom_morning_code",
	"custom_afternoon_code",
	"custom_work_credit",
]


def payroll_days(att) -> float:
	"""Số ngày phiếu lương trả cho MỘT bản ghi — qua đúng hai truy vấn của Salary Slip
	(`calculate_lwp_ppl_and_absent_days_based_on_attendance` + `get_half_absent_days`)."""
	ss = frappe.new_doc("Salary Slip")
	ss.employee = att.employee
	ss.start_date = ss.end_date = att.attendance_date  # actual_* suy từ hai ô này + ngày vào/nghỉ việc
	lwp, absent = ss.calculate_lwp_ppl_and_absent_days_based_on_attendance(
		holidays=[], daily_wages_fraction_for_half_day=0.5, consider_marked_attendance_on_holidays=False
	)
	half_absent = ss.get_half_absent_days(consider_marked_attendance_on_holidays=False, holidays=[])
	return 1 - flt(lwp) - flt(absent) - 0.5 * flt(half_absent)


def mismatches(from_date, to_date, employee: str | None = None) -> list[dict]:
	from hrms.hr.work_schedule import is_working_day

	ppl = set(frappe.get_all("Leave Type", {"is_ppl": 1}, pluck="name"))
	filters = {"docstatus": 1, "attendance_date": ("between", [getdate(from_date), getdate(to_date)])}
	if employee:
		filters["employee"] = employee
	out = []
	for att in frappe.get_all(
		"Attendance", filters=filters, fields=FIELDS, order_by="attendance_date, employee"
	):
		if att.leave_type in ppl or not is_working_day(att.employee, att.attendance_date):
			continue
		paid = payroll_days(att)
		credit = flt(att.custom_work_credit)
		if abs(paid - credit) > 0.001:
			out.append(frappe._dict(att, payroll_days=paid, cong=credit))
	return out


def scan(from_date, to_date, employee: str | None = None) -> list[dict]:
	rows = mismatches(from_date, to_date, employee)
	print(f"Kỳ {from_date} → {to_date}: {len(rows)} bản ghi Công ≠ ngày phiếu lương trả")
	for r in rows:
		code = r.custom_attendance_code or f"{r.custom_morning_code}/{r.custom_afternoon_code}"
		print(
			f"  {r.name}  {r.employee} {r.employee_name}  {r.attendance_date}  mã={code} Công={r.cong}"
			f"  lương={r.payroll_days}  | status={r.status} leave_type={r.leave_type or '-'}"
			f" nửa_kia={r.half_day_status or '-'} modify={r.modify_half_day_status}"
			f" đơn={r.leave_application or '-'}"
		)
	return rows
