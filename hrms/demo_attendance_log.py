"""Sinh nhật ký chấm công thực tế (checkin -> attendance) cho một tháng, để soi luồng VN.

Khác `hrms.demo_data`: file kia set thẳng **mã công** để phủ hết 13 ký hiệu + công tác + bảng
tháng; file này đi từ **đầu vào thật** — cặp Employee Checkin IN/OUT có nhiễu (đi muộn, về sớm,
tăng ca), Leave Application được duyệt, rồi để hệ thống tự suy ra Attendance. Dùng nó khi cần
kiểm chứng bộ phân loại nửa ngày / cầu nối mã công trên dữ liệu giống máy chấm công đẩy vào.

**KHÔNG tạo Attendance trực tiếp.** Chỉ dựng hai đầu vào có thật — dấu chấm công và đơn nghỉ —
rồi gọi `Shift Type.process_auto_attendance()`. Nhờ vậy mỗi bản ghi Attendance đều truy ngược
được về dấu chấm sinh ra nó (cột `attendance` trên Employee Checkin).

CHẠY (từ thư mục frappe-bench):

  # 1) Chạy thử — không ghi gì, trả về đúng những gì sẽ tạo:
  bench --site <site> execute hrms.demo_attendance_log.generate

  # 2) Ghi thật:
  bench --site <site> execute hrms.demo_attendance_log.generate --kwargs "{'apply': True}"

  # 3) Tháng khác:
  bench --site <site> execute hrms.demo_attendance_log.generate --kwargs "{'year': 2026, 'month': 7}"

Idempotent: bỏ qua chứng từ đã tồn tại. Attendance trong khoảng ngày của **đúng các nhân viên
demo** bị huỷ + xoá rồi dựng lại để số liệu nhất quán — không đụng nhân viên khác, không đụng
tháng khác.

CẢNH BÁO: `hrms.demo_data.create_demo_data` xoá Employee Checkin / Leave Application của cùng 5
nhân viên demo **không lọc theo ngày**, nên chạy nó sẽ xoá luôn dữ liệu do file này sinh ra.

Kịch bản neo theo **thứ tự ngày công trong tháng** (không phải ngày dương lịch) nên tháng nào
cũng dùng được. Giờ giấc random nhưng seed theo mã nhân viên -> chạy lại ra y hệt.
"""

import datetime
import random

import frappe
from frappe.utils import getdate

from hrms.demo_data import COMPANY, EMP_DEFS, SHIFT, _ensure_employees
from hrms.rebuild_attendance_from_checkin import run_auto_attendance_for_period

SHIFT_IN = datetime.time(8, 0)
SHIFT_OUT = datetime.time(17, 30)
DEVICE_ID = "MAY-CHAM-CONG-01"

# Kịch bản theo thứ tự ngày công (1 = ngày công đầu tiên của tháng), khoá theo key trong EMP_DEFS.
# Với tháng 6/2026 (26 ngày công, chỉ nghỉ Chủ nhật) các số này ra đúng: Bình nghỉ phép 15-17/6,
# Cường nghỉ ốm 9-10/6, Dung không lương 25/6, nửa ngày Cường 22/6 & Em 18/6, Dung vắng 4/6.
LEAVE_PLAN = {
	"binh": {"leave_type": "Nghỉ phép năm", "workday": 13, "days": 3},
	"cuong": {"leave_type": "Nghỉ ốm", "workday": 8, "days": 2},
	"dung": {"leave_type": "Nghỉ không lương", "workday": 22, "days": 1},
}
HALF_DAYS = {"cuong": {19}, "em": {16}}
ABSENT_DAYS = {"dung": {4}}
OVERTIME_DAYS = {"an": {9, 21}, "em": {5, 10, 17, 20, 23}}
ALLOCATIONS = [(key, "Nghỉ phép năm", 12) for key in EMP_DEFS] + [("cuong", "Nghỉ ốm", 30)]


class Log:
	def __init__(self):
		self.created = {}
		self.skipped = {}
		self.errors = []

	def note(self, bucket, key):
		d = getattr(self, bucket)
		d[key] = d.get(key, 0) + 1

	def fail(self, what, exc):
		self.errors.append(f"{what}: {exc}")

	def as_dict(self, **extra):
		return dict(created=self.created, skipped=self.skipped, errors=self.errors[:30], **extra)


def month_bounds(year, month):
	start = datetime.date(year, month, 1)
	end = datetime.date(year + (month == 12), (month % 12) + 1, 1) - datetime.timedelta(days=1)
	return start, end


def daterange(start, end):
	day = start
	while day <= end:
		yield day
		day += datetime.timedelta(days=1)


def get_holidays(start, end):
	holiday_list = frappe.db.get_value("Company", COMPANY, "default_holiday_list")
	if not holiday_list:
		return set()
	rows = frappe.db.sql(
		"select holiday_date from tabHoliday where parent=%s and holiday_date between %s and %s",
		(holiday_list, start, end),
	)
	return {getdate(r[0]) for r in rows}


def leave_dates(key, workdays):
	"""Ngày dương lịch của đợt nghỉ: neo vào ngày công thứ N rồi trải theo lịch."""
	plan = LEAVE_PLAN.get(key)
	if not plan or plan["workday"] > len(workdays):
		return {}, None
	first = workdays[plan["workday"] - 1]
	last = first + datetime.timedelta(days=plan["days"] - 1)
	span = {d: plan["leave_type"] for d in daterange(first, last) if d in set(workdays)}
	return span, (first, last, plan["leave_type"])


def submit_doc(payload):
	doc = frappe.get_doc(payload)
	doc.flags.ignore_permissions = True
	doc.insert()
	doc.submit()
	return doc


def guard_payroll(emp_ids, start, end):
	"""Không cho đụng vào tháng đã chạy lương — sinh lại chấm công sẽ lệch số đã chốt."""
	slips = frappe.get_all(
		"Salary Slip",
		filters={
			"employee": ["in", emp_ids],
			"docstatus": ["<", 2],
			"start_date": ["<=", end],
			"end_date": [">=", start],
		},
		fields=["name", "employee"],
	)
	if slips:
		frappe.throw(
			f"Đã có {len(slips)} Salary Slip phủ khoảng {start}..{end} của các nhân viên demo "
			f"(vd {slips[0].name}). Không sinh lại chấm công cho tháng đã chạy lương."
		)


def clear_old_attendance(log, emp_ids, start, end):
	"""Xoá Attendance cũ của kỳ, TRỪ bản do Leave Application sinh ra.

	Đơn nghỉ đã tồn tại sẽ bị bỏ qua ở lần chạy sau, nên nếu xoá luôn bản ghi của nó thì không
	còn gì dựng lại — job auto-attendance cố tình không đụng vào ngày đã có đơn nghỉ.
	"""
	rows = frappe.get_all(
		"Attendance",
		filters={
			"employee": ["in", emp_ids],
			"attendance_date": ["between", [start, end]],
			"leave_application": ["is", "not set"],
		},
		fields=["name", "docstatus"],
	)
	for row in rows:
		try:
			if row.docstatus == 1:
				frappe.get_doc("Attendance", row.name).cancel()
			frappe.delete_doc("Attendance", row.name, force=True, ignore_permissions=True)
			log.note("created", "deleted_old_attendance")
		except Exception as exc:
			log.fail(f"DeleteAttendance {row.name}", exc)


def make_shift_assignments(log, emps, start, end):
	for emp in emps.values():
		if frappe.db.exists(
			"Shift Assignment", {"employee": emp, "start_date": start, "docstatus": ["<", 2]}
		):
			log.note("skipped", "shift_assignment")
			continue
		try:
			submit_doc(
				{
					"doctype": "Shift Assignment",
					"employee": emp,
					"company": COMPANY,
					"shift_type": SHIFT,
					"start_date": start,
					"end_date": end,
					"status": "Active",
				}
			)
			log.note("created", "shift_assignment")
		except Exception as exc:
			log.fail(f"ShiftAssignment {emp}", exc)


def make_leave_allocations(log, emps, year):
	for key, leave_type, days in ALLOCATIONS:
		emp = emps.get(key)
		if not emp:
			continue
		from_date, to_date = f"{year}-01-01", f"{year}-12-31"
		if frappe.db.exists(
			"Leave Allocation",
			{"employee": emp, "leave_type": leave_type, "from_date": from_date, "docstatus": 1},
		):
			log.note("skipped", "leave_allocation")
			continue
		try:
			submit_doc(
				{
					"doctype": "Leave Allocation",
					"employee": emp,
					"company": COMPANY,
					"leave_type": leave_type,
					"from_date": from_date,
					"to_date": to_date,
					"new_leaves_allocated": days,
				}
			)
			log.note("created", "leave_allocation")
		except Exception as exc:
			log.fail(f"LeaveAllocation {emp}/{leave_type}", exc)


def make_leave_applications(log, emps, workdays):
	"""Submit đơn nghỉ. HRMS tự tạo Attendance 'On Leave' ngay tại đây, nên các ngày nghỉ đã có
	bản ghi trước khi vòng chấm công chạy — `make_attendance` phải tôn trọng, không ghi đè."""
	for key in LEAVE_PLAN:
		emp = emps.get(key)
		_, span = leave_dates(key, workdays)
		if not emp or not span:
			continue
		first, last, leave_type = span
		if frappe.db.exists(
			"Leave Application",
			{"employee": emp, "from_date": first, "leave_type": leave_type, "docstatus": 1},
		):
			log.note("skipped", "leave_application")
			continue
		try:
			submit_doc(
				{
					"doctype": "Leave Application",
					"employee": emp,
					"company": COMPANY,
					"leave_type": leave_type,
					"from_date": first,
					"to_date": last,
					"posting_date": first - datetime.timedelta(days=3),
					"description": f"Đơn xin {leave_type.lower()}",
					"leave_approver": "Administrator",
					"status": "Approved",
				}
			)
			log.note("created", "leave_application")
		except Exception as exc:
			log.fail(f"LeaveApplication {emp}", exc)


def day_plan(key, day, ordinal, workdays):
	"""(status, leave_type) cho một ngày công."""
	on_leave, _ = leave_dates(key, workdays)
	if day in on_leave:
		return "On Leave", on_leave[day]
	if ordinal in ABSENT_DAYS.get(key, set()):
		return "Absent", None
	if ordinal in HALF_DAYS.get(key, set()):
		return "Half Day", None
	return "Present", None


def clock_times(key, day, ordinal, status, rnd):
	"""Giờ vào/ra thực tế — có đi muộn, về sớm, tăng ca. Thứ tự bốc số phải giữ nguyên để
	chạy lại ra cùng kết quả."""
	if status not in ("Present", "Half Day"):
		return None, None
	late = rnd.choice([0, 0, 0, 3, 7, 12, 18])
	in_dt = datetime.datetime.combine(day, SHIFT_IN) + datetime.timedelta(minutes=late)
	if status == "Half Day":
		out_dt = datetime.datetime.combine(day, datetime.time(12, 0))
	elif ordinal in OVERTIME_DAYS.get(key, set()):
		out_dt = datetime.datetime.combine(day, SHIFT_OUT) + datetime.timedelta(
			minutes=rnd.choice([90, 120, 150, 180])
		)
	else:
		out_dt = datetime.datetime.combine(day, SHIFT_OUT) + datetime.timedelta(
			minutes=rnd.choice([-8, -3, 0, 0, 5, 11, 25])
		)
	return in_dt, out_dt


def make_checkins(log, emp, in_dt, out_dt):
	"""Chỉ tạo dấu chấm công. Attendance KHÔNG được tạo ở đây — nó phải do
	`Shift Type.process_auto_attendance()` sinh ra từ chính các dấu chấm này, nếu không thì cột
	`attendance` trên checkin rỗng và không có gì chứng minh số công đến từ máy chấm công."""
	for log_type, stamp in (("IN", in_dt), ("OUT", out_dt)):
		if frappe.db.exists("Employee Checkin", {"employee": emp, "time": stamp}):
			log.note("skipped", "checkin")
			continue
		try:
			doc = frappe.get_doc(
				{
					"doctype": "Employee Checkin",
					"employee": emp,
					"log_type": log_type,
					"time": stamp,
					"shift": SHIFT,
					"device_id": DEVICE_ID,
					"skip_auto_attendance": 0,
				}
			)
			doc.flags.ignore_permissions = True
			doc.insert()
			log.note("created", "checkin")
		except Exception as exc:
			log.fail(f"Checkin {emp} {stamp}", exc)


def generate(year=2026, month=6, apply=False):
	"""Sinh checkin + đơn nghỉ cho `month/year`, rồi để job sinh Attendance. Dry-run trừ khi apply.

	KHÔNG tạo Attendance trực tiếp: chỉ dựng dấu chấm công và đơn nghỉ — hai đầu vào có thật —
	rồi gọi `process_auto_attendance()` để hệ thống tự suy ra ngày công. Nhờ vậy mỗi bản ghi
	Attendance đều truy ngược được về dấu chấm sinh ra nó.
	"""
	start, end = month_bounds(int(year), int(month))
	holidays = get_holidays(start, end)
	workdays = [d for d in daterange(start, end) if d.weekday() != 6 and d not in holidays]

	log = Log()
	emps = _ensure_employees()
	emp_ids = list(emps.values())
	guard_payroll(emp_ids, start, end)

	clear_old_attendance(log, emp_ids, start, end)
	make_shift_assignments(log, emps, start, end)
	make_leave_allocations(log, emps, int(year))
	make_leave_applications(log, emps, workdays)

	for key, emp in emps.items():
		rnd = random.Random(emp)  # tái lập được: cùng mã nhân viên -> cùng giờ giấc
		for ordinal, day in enumerate(workdays, start=1):
			status, _leave_type = day_plan(key, day, ordinal, workdays)
			in_dt, out_dt = clock_times(key, day, ordinal, status, rnd)
			if in_dt:
				make_checkins(log, emp, in_dt, out_dt)

	if apply:
		# Attendance chỉ được sinh ở đây, từ chính các dấu chấm vừa tạo. Job commit bên trong
		# nên bước này không chạy được ở chế độ dry-run.
		log.auto = run_auto_attendance_for_period(SHIFT, start, end)

	result = log.as_dict(
		auto_attendance=getattr(log, "auto", "bỏ qua ở chế độ chạy thử"),
		applied=bool(apply),
		period=f"{start}..{end}",
		workdays=len(workdays),
		holidays=sorted(str(h) for h in holidays),
		employees=emps,
	)
	if apply:
		frappe.db.commit()
	else:
		frappe.db.rollback()
		result["note"] = "DRY-RUN: đã rollback. Thêm --kwargs \"{'apply': True}\" để ghi thật."
	print(frappe.as_json(result))
	return result
