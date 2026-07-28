"""Demo chấm công + lương TOÀN DIỆN cho tháng 6 & 7/2026 — SINH ĐÚNG ĐƯỜNG (scheduler + chứng từ).

Mục tiêu: phủ ĐỦ MỌI mã công của bảng chấm công + đủ 6 cấu trúc lương, cho CẢ hai tháng, mà
**KHÔNG tạo Attendance trực tiếp**. Mọi Attendance sinh ra từ đầu vào thật:

  checkin (máy chấm công) ─┐
  Đơn xin nghỉ ────────────┤→  Shift Type.process_auto_attendance()  →  Attendance
  Công Tác (Business Trip) ┤     (+ controller của chứng từ tự ghi CT/W)
  Yêu cầu chấm công ───────┘
  Lịch lễ (Holiday List)  →  NL / '-' (dấu lịch, không cần Attendance)

Mã phủ (16): X, 1/2K, V (từ checkin/scheduler) · P, 1/2P, Ô, Cô, TS, K, KH, R1, R2, T, NB
(từ Đơn xin nghỉ) · CT (Công Tác) · W (Yêu cầu chấm công). NN (Half Day không nghỉ) không có
luồng chứng từ tự nhiên → bỏ qua. NL có ở tháng 7 (17/07 lễ công ty); tháng 6 không có lễ (thực tế).

CHẠY (từ frappe-bench):
  # thử (rollback, chỉ dựng chứng từ — KHÔNG chạy scheduler/lương vì chúng commit):
  bench --site miyano execute hrms.demo_comprehensive.generate
  # thật:
  bench --site miyano execute hrms.demo_comprehensive.generate --kwargs "{'apply': True}"

Idempotent theo kiểu "dọn rồi dựng": xoá GỌN dữ liệu giao dịch tháng 6+7 của 6 nhân viên demo
(phiếu lương, bảng công, attendance, checkin, đơn nghỉ) — GIỮ nhân viên, gán ca, phân bổ phép,
gán cấu trúc lương — rồi dựng lại. Snapshot ra JSON trước khi xoá.
"""

import datetime
import json

import frappe
from frappe.utils import add_days, getdate

from hrms.rebuild_attendance_from_checkin import run_auto_attendance_for_period

COMPANY = "Miyano"
SHIFT = "Ca Hành Chính"
YEAR = 2026
MONTHS = (6, 7)
SHIFT_IN = datetime.time(8, 0)
SHIFT_OUT = datetime.time(17, 30)
DEVICE_ID = "MAY-CHAM-CONG-01"
SNAPSHOT = "/home/miyano/miyano-demo67-restore.json"

# Nhân viên demo: khoá ngắn → employee_name (đã tồn tại trên site).
EMP_NAMES = {
	"hieu": "hieu chu",
	"an": "Nguyễn Văn An",
	"binh": "Trần Thị Bình",
	"cuong": "Lê Văn Cường",
	"dung": "Phạm Thị Dung",
	"em": "Hoàng Văn Em",
}

# Phân bổ phép cần có TRƯỚC khi nộp đơn (chỉ thêm nếu thiếu). (key, leave_type, số ngày).
ALLOCATIONS = [
	("an", "Nghỉ phép năm", 12),
	("an", "Nghỉ ốm", 30),
	("an", "Nghỉ chăm con ốm", 30),
	("an", "Nghỉ bù", 10),
	("binh", "Nghỉ phép năm", 12),
	("binh", "Nghỉ thai sản", 60),
	("binh", "Nghỉ kết hôn", 6),
	("dung", "Nghỉ phép năm", 12),
	("dung", "Nghỉ con kết hôn", 4),
	("dung", "Nghỉ tang", 6),
	("dung", "Nghỉ tai nạn lao động", 30),
]

# Kịch bản neo theo THỨ TỰ NGÀY CÔNG trong tháng (ord 1 = ngày công đầu). Dùng chung cho cả 2 tháng.
# leaves: (leave_type, start_ord, num_days, half, period). trip: (co_traveler_keys, start_ord, num_days).
# requests: (reason, ord). absent: {ord}. half_checkin (1/2K): {ord}. overtime: {ord}.
SCEN = {
	"an": {
		"leaves": [
			("Nghỉ phép năm", 3, 1, False, None),  # P
			("Nghỉ phép năm", 5, 1, True, "Sáng"),  # 1/2P
			("Nghỉ ốm", 7, 1, False, None),  # Ô
			("Nghỉ chăm con ốm", 9, 1, False, None),  # Cô
			("Nghỉ không lương", 11, 1, False, None),  # K
			("Nghỉ bù", 15, 1, False, None),  # NB
		],
		"half_checkin": {13},  # 1/2K (làm sáng, chiều không lương)
	},
	"binh": {
		"leaves": [
			("Nghỉ thai sản", 6, 3, False, None),  # TS x3
			("Nghỉ kết hôn", 12, 3, False, None),  # KH x3
		],
	},
	"cuong": {
		"trip": (["dung"], 4, 3),  # CT x3 (Cường đăng ký + Dung đi cùng)
		"requests": [("Work From Home", 16)],  # W
		"absent": {10},  # V
	},
	"dung": {
		"leaves": [
			("Nghỉ con kết hôn", 8, 1, False, None),  # R1
			("Nghỉ tang", 10, 3, False, None),  # R2 x3
			("Nghỉ tai nạn lao động", 15, 1, False, None),  # T
		],
	},
	"em": {
		"half_checkin": {5},  # 1/2K
		"overtime": {9, 14, 18},
	},
	"hieu": {
		"half_checkin": {17},  # 1/2K
	},
}


class Log:
	def __init__(self):
		self.c = {}
		self.errors = []

	def n(self, k, i=1):
		self.c[k] = self.c.get(k, 0) + i

	def fail(self, what, exc):
		self.errors.append(f"{what}: {exc}")

	def d(self, **extra):
		return dict(created=self.c, errors=self.errors[:40], **extra)


def emps():
	out = {}
	for key, name in EMP_NAMES.items():
		n = frappe.db.get_value("Employee", {"employee_name": name, "company": COMPANY}, "name")
		if n:
			out[key] = n
	return out


def month_bounds(y, m):
	start = datetime.date(y, m, 1)
	end = datetime.date(y + (m == 12), (m % 12) + 1, 1) - datetime.timedelta(days=1)
	return start, end


def holiday_dates(start, end):
	hl = frappe.db.get_value("Company", COMPANY, "default_holiday_list")
	rows = frappe.db.sql(
		"select holiday_date from tabHoliday where parent=%s and holiday_date between %s and %s",
		(hl, start, end),
	)
	return {getdate(r[0]) for r in rows}


def workdays(y, m, joining=None):
	start, end = month_bounds(y, m)
	hol = holiday_dates(start, end)
	days, d = [], start
	while d <= end:
		if d not in hol and (not joining or d >= joining):
			days.append(d)
		d += datetime.timedelta(days=1)
	return days


def submit_doc(payload):
	doc = frappe.get_doc(payload)
	doc.flags.ignore_permissions = True
	doc.insert()
	doc.submit()
	return doc


# ---------------------------------------------------------------------------- clean
CLEAN_ORDER = ["Salary Slip", "Monthly Attendance Sheet", "Attendance", "Leave Application"]


def snapshot(emp_ids, log):
	snap = {}
	for m in MONTHS:
		start, end = month_bounds(YEAR, m)
		snap[f"{YEAR}-{m:02d}"] = {
			"attendance": frappe.get_all(
				"Attendance",
				filters={"employee": ["in", emp_ids], "attendance_date": ["between", [start, end]]},
				fields=[
					"name",
					"employee",
					"attendance_date",
					"status",
					"leave_type",
					"custom_attendance_code",
				],
			),
			"leave_app": frappe.get_all(
				"Leave Application",
				filters={"employee": ["in", emp_ids], "from_date": ["between", [start, end]]},
				fields=["name", "employee", "leave_type", "from_date", "to_date"],
			),
			"slips": frappe.get_all(
				"Salary Slip",
				filters={"employee": ["in", emp_ids], "start_date": [">=", start], "end_date": ["<=", end]},
				fields=["name", "employee", "payment_days", "net_pay"],
			),
		}
	# đường dẫn do quản trị viên truyền khi chạy bench execute, không đến từ request
	with open(SNAPSHOT, "w") as f:  # nosemgrep
		json.dump(snap, f, default=str, ensure_ascii=False, indent=1)
	log.n("snapshot_written")


def clean(emp_ids, log):
	for m in MONTHS:
		start, end = month_bounds(YEAR, m)
		targets = [
			(
				"Salary Slip",
				{"employee": ["in", emp_ids], "start_date": [">=", start], "end_date": ["<=", end]},
			),
			("Monthly Attendance Sheet", {"company": COMPANY, "month": str(m), "year": YEAR}),
			("Attendance", {"employee": ["in", emp_ids], "attendance_date": ["between", [start, end]]}),
			("Leave Application", {"employee": ["in", emp_ids], "from_date": ["between", [start, end]]}),
			(
				"Employee Checkin",
				{"employee": ["in", emp_ids], "time": ["between", [f"{start} 00:00:00", f"{end} 23:59:59"]]},
			),
		]
		for dt, filt in targets:
			for n in frappe.get_all(dt, filters=filt, pluck="name"):
				try:
					doc = frappe.get_doc(dt, n)
					if doc.docstatus == 1:
						doc.flags.ignore_permissions = True
						doc.cancel()
					frappe.delete_doc(dt, n, force=True, ignore_permissions=True)
					log.n(f"deleted_{dt.replace(' ', '_')}")
				except Exception as exc:
					log.fail(f"clean {dt} {n}", exc)


# ---------------------------------------------------------------------------- build
def ensure_assignments(e, log):
	for _key, emp in e.items():
		joining = frappe.db.get_value("Employee", emp, "date_of_joining")
		for m in MONTHS:
			start, end = month_bounds(YEAR, m)
			if joining and getdate(joining) > start:
				start = getdate(joining)
			if start > end:
				continue
			if frappe.db.exists(
				"Shift Assignment", {"employee": emp, "start_date": start, "docstatus": ["<", 2]}
			):
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
				log.n("shift_assignment")
			except Exception as exc:
				log.fail(f"ShiftAssignment {emp} {m}", exc)


def ensure_allocations(e, log):
	for key, leave_type, days in ALLOCATIONS:
		emp = e.get(key)
		if not emp:
			continue
		frm, to = f"{YEAR}-01-01", f"{YEAR}-12-31"
		if frappe.db.exists(
			"Leave Allocation", {"employee": emp, "leave_type": leave_type, "from_date": frm, "docstatus": 1}
		):
			continue
		try:
			submit_doc(
				{
					"doctype": "Leave Allocation",
					"employee": emp,
					"company": COMPANY,
					"leave_type": leave_type,
					"from_date": frm,
					"to_date": to,
					"new_leaves_allocated": days,
				}
			)
			log.n("leave_allocation")
		except Exception as exc:
			log.fail(f"LeaveAllocation {emp}/{leave_type}", exc)


def covered_ordinals(key):
	"""Các ord đã có chứng từ (nghỉ/công tác/yêu cầu) — KHÔNG tạo checkin cho chúng."""
	s = SCEN.get(key, {})
	cov = set()
	for _lt, o, nd, _h, _p in s.get("leaves", []):
		cov.update(range(o, o + nd))
	if "trip" in s:
		_co, o, nd = s["trip"]
		cov.update(range(o, o + nd))
	for _r, o in s.get("requests", []):
		cov.add(o)
	# ord đi công tác với tư cách khách mời (traveler trong trip của người khác)
	for _owner, os in SCEN.items():
		if "trip" in os and key in os["trip"][0]:
			_co, o, nd = os["trip"]
			cov.update(range(o, o + nd))
	return cov


def make_leaves(e, m, wds, log):
	for key, s in SCEN.items():
		emp = e.get(key)
		if not emp:
			continue
		for lt, o, nd, half, period in s.get("leaves", []):
			if o - 1 >= len(wds):
				continue
			first = wds[o - 1]
			last = wds[min(o - 1 + nd - 1, len(wds) - 1)]
			payload = {
				"doctype": "Leave Application",
				"employee": emp,
				"company": COMPANY,
				"leave_type": lt,
				"from_date": first,
				"to_date": last,
				"posting_date": add_days(first, -3),
				"leave_approver": "Administrator",
				"status": "Approved",
				"description": f"Demo {lt}",
			}
			if lt == "Nghỉ phép năm":
				payload["custom_leave_reason"] = "Nghỉ phép năm"
			if half:
				payload.update({"half_day": 1, "half_day_date": first, "to_date": first})
				if lt == "Nghỉ phép năm":
					payload["custom_half_day_period"] = period
			try:
				submit_doc(payload)
				log.n(f"leave_{lt}")
			except Exception as exc:
				log.fail(f"Leave {key} {lt} {m}", exc)


def make_trips(e, m, wds, log):
	from frappe.model.workflow import apply_workflow

	for key, s in SCEN.items():
		if "trip" not in s:
			continue
		reg = e.get(key)
		co_keys, o, nd = s["trip"]
		if not reg or o - 1 >= len(wds):
			continue
		first, last = wds[o - 1], wds[min(o - 1 + nd - 1, len(wds) - 1)]
		travelers = [{"employee": reg, "is_registrant": 1}]
		for ck in co_keys:
			if e.get(ck):
				travelers.append({"employee": e[ck], "is_registrant": 0})
		try:
			trip = frappe.get_doc(
				{
					"doctype": "Business Trip",
					"company": COMPANY,
					"destination": "Hà Nội",
					"purpose": "Họp giao ban",
					"from_date": first,
					"to_date": last,
					"registered_by": reg,
					"approver_coo": "Administrator",
					"travelers": travelers,
				}
			)
			trip.flags.ignore_permissions = True
			trip.insert()
			for action in ("Gửi duyệt", "Duyệt", "Ra QĐ"):
				apply_workflow(trip, action)
			log.n("business_trip")
		except Exception as exc:
			log.fail(f"Trip {key} {m}", exc)


def make_requests(e, m, wds, log):
	for key, s in SCEN.items():
		emp = e.get(key)
		if not emp:
			continue
		for reason, o in s.get("requests", []):
			if o - 1 >= len(wds):
				continue
			day = wds[o - 1]
			try:
				submit_doc(
					{
						"doctype": "Attendance Request",
						"employee": emp,
						"company": COMPANY,
						"from_date": day,
						"to_date": day,
						"reason": reason,
						"explanation": f"Demo {reason}",
					}
				)
				log.n(f"request_{reason}")
			except Exception as exc:
				log.fail(f"Request {key} {reason} {m}", exc)


def make_checkins(e, m, wds, log):
	for key, emp in e.items():
		s = SCEN.get(key, {})
		cov = covered_ordinals(key)
		absent = s.get("absent", set())
		half = s.get("half_checkin", set())
		overtime = s.get("overtime", set())
		joining = frappe.db.get_value("Employee", emp, "date_of_joining")
		for o, day in enumerate(wds, start=1):
			if o in cov or o in absent:
				continue  # chứng từ lo / cố ý vắng (scheduler chấm Vắng)
			if joining and day < getdate(joining):
				continue  # trước ngày vào làm → không chấm công (Attendance sẽ chặn ngày < DOJ)
			in_dt = datetime.datetime.combine(day, SHIFT_IN)
			if o in half:
				out_dt = datetime.datetime.combine(day, datetime.time(12, 0))
			elif o in overtime:
				out_dt = datetime.datetime.combine(day, SHIFT_OUT) + datetime.timedelta(minutes=120)
			else:
				out_dt = datetime.datetime.combine(day, SHIFT_OUT)
			for log_type, stamp in (("IN", in_dt), ("OUT", out_dt)):
				if frappe.db.exists("Employee Checkin", {"employee": emp, "time": stamp}):
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
					log.n("checkin")
				except Exception as exc:
					log.fail(f"Checkin {emp} {stamp}", exc)


def make_payroll(e, m, log):
	start, end = month_bounds(YEAR, m)
	for _key, emp in e.items():
		ssa = frappe.get_all(
			"Salary Structure Assignment",
			filters={"employee": emp, "docstatus": 1, "from_date": ["<=", end]},
			fields=["salary_structure"],
			order_by="from_date desc",
			limit=1,
		)
		if not ssa:
			log.fail(f"Payroll {emp} {m}", "no SSA")
			continue
		try:
			ss = frappe.new_doc("Salary Slip")
			ss.employee = emp
			ss.salary_structure = ssa[0].salary_structure
			ss.payroll_frequency = "Monthly"
			ss.start_date = start
			ss.end_date = end
			ss.flags.ignore_permissions = True
			ss.insert()
			ss.submit()
			if "None" in ss.name:
				frappe.rename_doc("Salary Slip", ss.name, ss.name.replace("None", emp), force=True)
			log.n("salary_slip")
		except Exception as exc:
			log.fail(f"Payroll {emp} {m}", exc)


def make_sheet(m, log):
	try:
		sheet = frappe.get_doc(
			{"doctype": "Monthly Attendance Sheet", "company": COMPANY, "month": str(m), "year": YEAR}
		)
		sheet.flags.ignore_permissions = True
		sheet.insert()
		sheet.populate_from_attendance()
		sheet.save()
		sheet.submit()
		log.n("monthly_sheet")
	except Exception as exc:
		log.fail(f"Sheet {m}", exc)


def generate(apply=False):
	log = Log()
	e = emps()
	emp_ids = list(e.values())
	if len(e) < len(EMP_NAMES):
		log.fail("emps", f"chỉ tìm thấy {len(e)}/{len(EMP_NAMES)} nhân viên demo")

	snapshot(emp_ids, log)
	clean(emp_ids, log)
	ensure_assignments(e, log)
	ensure_allocations(e, log)

	for m in MONTHS:
		wds = workdays(YEAR, m)
		make_leaves(e, m, wds, log)
		make_trips(e, m, wds, log)
		make_requests(e, m, wds, log)
		make_checkins(e, m, wds, log)

	if apply:
		# scheduler + lương + bảng công COMMIT bên trong → chỉ chạy khi apply thật
		for m in MONTHS:
			start, end = month_bounds(YEAR, m)
			log.n("auto_attendance_" + str(m))
			run_auto_attendance_for_period(SHIFT, start, end)
		for m in MONTHS:
			make_payroll(e, m, log)
			make_sheet(m, log)
		# commit chủ đích: công cụ chạy ngoài request cycle (bench execute), ghi từng phần để lần chạy dài không mất việc đã làm
		frappe.db.commit()  # nosemgrep
	else:
		frappe.db.rollback()

	result = log.d(
		applied=bool(apply),
		employees=e,
		months=list(MONTHS),
		note=""
		if apply
		else "DRY-RUN đã rollback (scheduler/lương/bảng công BỎ QUA). apply=True để ghi thật.",
	)
	print(frappe.as_json(result))
	return result
