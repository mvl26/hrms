"""Comprehensive one-off demo/test data for reviewing the VN timekeeping stack on a dev site.
Run: bench --site <site> execute hrms.demo_data.create_demo_data
Idempotent: clears the demo employees' month + demo sheet/trip/leave and rebuilds. Each flow is
wrapped so a partial failure still leaves the rest usable; the return dict reports per-section status.

Month = Sep 2026 (has 01-02/09 Quốc khánh -> 'NL'; Sundays -> '-').
"""

import frappe
from frappe.utils import getdate

COMPANY = "Miyano"
SHIFT = "Ca Hành Chính"
YEAR, MONTH = 2026, 9
EMP_DEFS = {
	"an": ("Nguyễn Văn An", "Male"),
	"binh": ("Trần Thị Bình", "Female"),
	"cuong": ("Lê Văn Cường", "Male"),
	"dung": ("Phạm Thị Dung", "Female"),
	"em": ("Hoàng Văn Em", "Male"),
}


def _d(day):
	return getdate(f"{YEAR}-{MONTH:02d}-{day:02d}")


def _ensure_shift():
	if not frappe.db.exists("Shift Type", SHIFT):
		frappe.get_doc(
			{
				"doctype": "Shift Type",
				"__newname": SHIFT,
				"start_time": "08:00:00",
				"end_time": "17:30:00",
				"custom_split_half_day": 1,
				"custom_lunch_start": "12:00:00",
				"custom_lunch_end": "13:30:00",
				"custom_half_day_min_fraction": 0.5,
				"custom_half_day_grace_minutes": 15,
			}
		).insert()


def _ensure_employees():
	emps = {}
	for key, (name, gender) in EMP_DEFS.items():
		existing = frappe.db.get_value("Employee", {"employee_name": name, "company": COMPANY}, "name")
		if existing:
			emps[key] = existing
			continue
		emps[key] = (
			frappe.get_doc(
				{
					"doctype": "Employee",
					"employee_name": name,
					"first_name": name,
					"company": COMPANY,
					"gender": gender,
					"date_of_birth": "1990-01-01",
					"date_of_joining": "2025-01-01",
					"status": "Active",
					"default_shift": SHIFT,
				}
			)
			.insert()
			.name
		)
	return emps


def _clear(emps):
	names = list(emps.values())
	for dt, filt in [
		("Employee Checkin", {"employee": ["in", names]}),
		("Attendance", {"employee": ["in", names], "attendance_date": ["between", [_d(1), _d(30)]]}),
		("Leave Application", {"employee": ["in", names]}),
		("Leave Allocation", {"employee": ["in", names]}),
		("Business Trip", {"destination": "Hà Nội"}),
		("Monthly Attendance Sheet", {"company": COMPANY, "month": str(MONTH), "year": YEAR}),
	]:
		for n in frappe.get_all(dt, filters=filt, pluck="name"):
			try:
				doc = frappe.get_doc(dt, n)
				if doc.docstatus == 1:
					doc.cancel()
				frappe.delete_doc(dt, n, force=True, ignore_permissions=True)
			except Exception:
				pass


def _code(emp, day, code):
	frappe.get_doc(
		{
			"doctype": "Attendance",
			"employee": emp,
			"company": COMPANY,
			"attendance_date": _d(day),
			"custom_attendance_code": code,
		}
	).insert().submit()


def _shift_att(emp, day, in_hm, out_hm):
	frappe.get_doc(
		{
			"doctype": "Attendance",
			"employee": emp,
			"company": COMPANY,
			"attendance_date": _d(day),
			"shift": SHIFT,
			"in_time": f"{_d(day)} {in_hm}:00",
			"out_time": f"{_d(day)} {out_hm}:00",
		}
	).insert().submit()


def _attendance(emps, status):
	an, binh, cuong, dung, em = (emps[k] for k in ("an", "binh", "cuong", "dung", "em"))
	# An — every manual code
	for day in (3, 4, 5):
		_code(an, day, "X")
	plan = {
		7: "P",
		8: "1/2P",
		9: "Ô",
		10: "Cô",
		11: "KH",
		12: "NN",
		14: "1/2K",
		15: "V",
		16: "K",
		17: "NB",
		18: "T",
	}
	for day, code in plan.items():
		_code(an, day, code)
	for day in (21, 22, 23, 24, 25):
		_code(an, day, "X")
	status["An (manual codes)"] = "ok"

	# Bình — classifier from in/out + maternity block
	_shift_att(binh, 3, "08:00", "17:30")  # full
	_shift_att(binh, 4, "08:00", "12:00")  # morning only
	_shift_att(binh, 5, "13:30", "17:30")  # afternoon only
	_shift_att(binh, 7, "08:00", "15:00")  # morning + afternoon<50%
	_shift_att(binh, 8, "12:10", "13:20")  # inside lunch -> absent
	_shift_att(binh, 9, "08:00", "17:30")
	for day in (14, 15, 16):
		_shift_att(binh, day, "08:00", "17:30")
	for day in (17, 18, 19):
		_code(binh, day, "TS")  # thai sản (multi-day)
	for day in (21, 22, 23, 24, 25):
		_shift_att(binh, day, "08:00", "17:30")
	status["Bình (classifier + TS)"] = "ok"

	# Cường — X, leaving 10-12 for the business trip (CT auto-attendance)
	for day in (3, 4, 5, 7, 8, 9, 14, 15, 16, 17, 18, 19, 21, 22, 23, 24, 25):
		_code(cuong, day, "X")
	status["Cường (X; 10-12 reserved for trip)"] = "ok"

	# Dung — X except 7-8 which come from the leave application
	for day in (3, 4, 5, 9, 10, 11, 12, 14, 15, 16, 17, 18, 19, 21, 22, 23, 24, 25):
		_code(dung, day, "X")
	status["Dung (X; 7-8 from leave app)"] = "ok"

	# Em — checkins + classifier attendance
	for day in (3, 4, 5, 9, 10, 11):
		frappe.get_doc(
			{"doctype": "Employee Checkin", "employee": em, "log_type": "IN", "time": f"{_d(day)} 08:00:00"}
		).insert()
		frappe.get_doc(
			{"doctype": "Employee Checkin", "employee": em, "log_type": "OUT", "time": f"{_d(day)} 17:30:00"}
		).insert()
		_shift_att(em, day, "08:00", "17:30")
	for day in (14, 15, 16, 17, 18, 19, 21, 22, 23, 24, 25):
		_shift_att(em, day, "08:00", "17:30")
	status["Em (checkins + attendance)"] = "ok"


def _leave_flow(emps, status):
	dung = emps["dung"]
	frappe.get_doc(
		{
			"doctype": "Leave Allocation",
			"employee": dung,
			"leave_type": "Nghỉ ốm",
			"from_date": f"{YEAR}-01-01",
			"to_date": f"{YEAR}-12-31",
			"new_leaves_allocated": 30,
		}
	).insert().submit()
	la = frappe.get_doc(
		{
			"doctype": "Leave Application",
			"employee": dung,
			"leave_type": "Nghỉ ốm",
			"from_date": _d(7),
			"to_date": _d(8),
			"leave_approver": "Administrator",
			"status": "Approved",
			"company": COMPANY,
		}
	)
	la.insert()
	la.submit()  # on_submit -> update_attendance -> Attendance On Leave -> reverse code 'Ô'
	status["Leave Application -> auto Attendance"] = la.name


def _business_trip(emps, status):
	from frappe.model.workflow import apply_workflow

	binh, cuong = emps["binh"], emps["cuong"]
	trip = frappe.get_doc(
		{
			"doctype": "Business Trip",
			"company": COMPANY,
			"destination": "Hà Nội",
			"purpose": "Họp giao ban quý",
			"from_date": _d(10),
			"to_date": _d(12),
			"registered_by": cuong,
			"approver_coo": "Administrator",
			"travelers": [{"employee": binh, "is_registrant": 0}, {"employee": cuong, "is_registrant": 1}],
		}
	)
	trip.insert()
	for action in ("Gửi duyệt", "Duyệt", "Ra QĐ"):
		try:
			apply_workflow(trip, action)
		except Exception as e:
			status[f"trip:{action}"] = f"stopped: {e}"
			break
	trip.reload()
	status["Business Trip"] = f"{trip.name} @ {trip.workflow_state}"


def _sheet(status):
	sheet = frappe.get_doc(
		{"doctype": "Monthly Attendance Sheet", "company": COMPANY, "month": str(MONTH), "year": YEAR}
	)
	sheet.insert()
	sheet.populate_from_attendance()
	sheet.save()
	sheet.submit()  # freeze the snapshot
	status["Monthly Attendance Sheet (submitted)"] = sheet.name


def create_demo_data():
	status = {}
	_ensure_shift()
	emps = _ensure_employees()
	_clear(emps)
	_attendance(emps, status)
	for fn in (_leave_flow, _business_trip):
		try:
			fn(emps, status)
		except Exception as e:
			status[fn.__name__] = f"FAILED: {e}"
	try:
		_sheet(status)
	except Exception as e:
		status["_sheet"] = f"FAILED: {e}"
	frappe.db.commit()
	status["employees"] = emps
	return status
