# Copyright (c) 2015, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt


from datetime import datetime, timedelta

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.query_builder.functions import Date
from frappe.utils import (
	add_days,
	cint,
	cstr,
	flt,
	format_date,
	get_datetime,
	get_link_to_form,
	getdate,
	nowdate,
)

import hrms
from hrms.hr.doctype.shift_assignment.shift_assignment import has_overlapping_timings
from hrms.hr.utils import (
	get_holiday_dates_for_employee,
	get_holidays_for_employee,
	validate_active_employee,
)


class DuplicateAttendanceError(frappe.ValidationError):
	pass


class OverlappingShiftAttendanceError(frappe.ValidationError):
	pass


class Attendance(Document):
	def before_validate(self):
		self.apply_vn_half_day_classifier()
		self.apply_attendance_code_bridge()

	def before_insert(self):
		if self.half_day_status == "":
			self.half_day_status = None

	def restore_code_driven_half_day_status(self):
		"""A half-day *leave* entered via mã công (1/2P, 1/2K, or a worked+leave split like X|P)
		has no backing Leave Application, so check_leave_record forces half_day_status="Absent".
		That is wrong here: the worked half IS present and the leave half's pay effect is already
		carried by leave_type (paid leaves aren't in payroll's LWP map; unpaid ones dock via it).
		Forcing Absent makes get_half_absent_days dock an extra 0.5 — over-deducting a paid half
		(1/2P) and double-deducting an unpaid half (1/2K). When a code drove this Half Day and set
		a leave_type, restore the worked half to Present. NN (no leave_type) is left Absent so it
		still docks 0.5 exactly like a native Half Day."""
		code_driven = (
			self.get("custom_attendance_code")
			or self.get("custom_morning_code")
			or self.get("custom_afternoon_code")
		)
		if code_driven and self.status == "Half Day" and self.leave_type and not self.leave_application:
			self.half_day_status = "Present"

	# module-level fallbacks for shifts that enable the split but leave a config field blank
	VN_DEFAULT_LUNCH_START = timedelta(hours=12)
	VN_DEFAULT_LUNCH_END = timedelta(hours=13, minutes=30)
	VN_DEFAULT_MIN_FRACTION = 0.5
	VN_DEFAULT_GRACE_MINUTES = 15

	def apply_vn_half_day_classifier(self):
		"""For a shift that opts into VN split-half-day, derive morning/afternoon codes + a
		lunch-excluded net working_hours from the day's in/out, so the code bridge produces the
		correct status/công. Gated + a no-op unless: shift set with custom_split_half_day=1,
		in/out present, no manual code, and status not On Leave."""
		if not self.get("shift") or not self.get("in_time") or not self.get("out_time"):
			return
		if self.get("custom_attendance_code") or self.get("custom_morning_code") or self.get(
			"custom_afternoon_code"
		):
			return  # respect a manually entered code
		if self.get("status") == "On Leave" or self.get("leave_type"):
			# A day already attributed to a leave — full day, or a half-day leave whose other half
			# was worked — must keep that attribution. Re-deriving both halves from the clock would
			# rewrite leave_type from the leave-less "V" code and silently drop the employee's leave.
			return

		cfg = frappe.db.get_value(
			"Shift Type",
			self.shift,
			[
				"start_time",
				"end_time",
				"custom_split_half_day",
				"custom_lunch_start",
				"custom_lunch_end",
				"custom_half_day_min_fraction",
				"custom_half_day_grace_minutes",
			],
			as_dict=True,
		)
		if not cfg or not cint(cfg.custom_split_half_day) or not (cfg.start_time and cfg.end_time):
			return

		midnight = datetime.combine(getdate(self.attendance_date), datetime.min.time())
		lunch_start = cfg.custom_lunch_start or self.VN_DEFAULT_LUNCH_START
		lunch_end = cfg.custom_lunch_end or self.VN_DEFAULT_LUNCH_END
		m_start, m_end = midnight + cfg.start_time, midnight + lunch_start
		a_start, a_end = midnight + lunch_end, midnight + cfg.end_time
		in_t, out_t = get_datetime(self.in_time), get_datetime(self.out_time)
		grace = timedelta(minutes=cint(cfg.custom_half_day_grace_minutes) or self.VN_DEFAULT_GRACE_MINUTES)
		min_frac = flt(cfg.custom_half_day_min_fraction) or self.VN_DEFAULT_MIN_FRACTION

		def overlap_hours(lo, hi, w_lo, w_hi):
			start, end = max(lo, w_lo), min(hi, w_hi)
			return max(0.0, (end - start).total_seconds() / 3600.0)

		m_net = overlap_hours(in_t, out_t, m_start, m_end)
		a_net = overlap_hours(in_t, out_t, a_start, a_end)
		m_dur = (m_end - m_start).total_seconds() / 3600.0
		a_dur = (a_end - a_start).total_seconds() / 3600.0
		# coverage uses a grace-expanded interval (tolerate small late-in / early-out); net hours do not
		m_cov = (overlap_hours(in_t - grace, out_t + grace, m_start, m_end) / m_dur) if m_dur else 0.0
		a_cov = (overlap_hours(in_t - grace, out_t + grace, a_start, a_end) / a_dur) if a_dur else 0.0

		self.working_hours = round(m_net + a_net, 2)
		worked_m, worked_a = m_cov >= min_frac, a_cov >= min_frac
		if worked_m and worked_a:
			self.custom_morning_code = self.custom_afternoon_code = "X"
		elif worked_m:
			self.custom_morning_code, self.custom_afternoon_code = "X", "V"
		elif worked_a:
			self.custom_morning_code, self.custom_afternoon_code = "V", "X"
		else:
			self.custom_attendance_code = "V"

	def apply_attendance_code_bridge(self):
		"""Two-way bridge between VN attendance codes (mã công) and the native status fields
		that payroll reads (status / leave_type / half_day_status). It never touches the
		skip logic and only sets fields native entry would set, so payroll stays invariant.

		Forward (user entered code(s)): morning/afternoon (or a single day code) -> native fields
		+ custom_work_credit (Σ work_fraction of Công-category halves).
		Reverse (record has a status but no code, e.g. from auto-attendance / leave): derive
		custom_attendance_code for display only, without changing native fields.
		"""
		if not frappe.get_meta("Attendance").has_field("custom_attendance_code"):
			return  # custom-field fixtures not installed yet

		morning = self.get("custom_morning_code") or self.get("custom_attendance_code")
		afternoon = self.get("custom_afternoon_code") or self.get("custom_attendance_code")

		if morning or afternoon:
			self._apply_codes_forward(morning or afternoon, afternoon or morning)
		else:
			self._derive_attendance_code_reverse()

	def _get_attendance_code(self, name):
		if not name:
			return None
		return frappe.db.get_value(
			"Attendance Code",
			name,
			["category", "work_fraction", "is_paid", "maps_to_status", "leave_type"],
			as_dict=True,
		)

	def _apply_codes_forward(self, morning, afternoon):
		m = self._get_attendance_code(morning)
		a = self._get_attendance_code(afternoon)
		if not (m and a):
			return

		# công đi làm thực tế = Σ work_fraction (worked-công fraction) of each half × 0.5.
		# work_fraction already excludes non-working codes (P/Ô/K = 0), so no category filter needed;
		# this also lets a single half-day code (NN/1/2P/1/2K, work_fraction 0.5) count its worked half.
		self.custom_work_credit = sum(flt(c.work_fraction) * 0.5 for c in (m, a))
		# single display code only when the whole day is one code
		self.custom_attendance_code = morning if morning == afternoon else None

		if m.maps_to_status == a.maps_to_status:
			self.status = m.maps_to_status
			self.leave_type = m.leave_type if m.maps_to_status in ("On Leave", "Half Day") else None
			if m.maps_to_status == "Half Day":
				# a single Half-Day code (NN/1/2P/1/2K): worked half is present, the other half is
				# leave (if leave_type set) or unpaid absence (NN). Mirrors native Half-Day entry.
				self.half_day_status = "Present"
		else:
			# one working half + one non-working half -> Half Day; the non-working half sets leave_type
			self.status = "Half Day"
			leave_half = m if m.maps_to_status not in ("Present", "Work From Home") else a
			self.leave_type = leave_half.leave_type
			self.half_day_status = "Present" if leave_half.maps_to_status == "On Leave" else "Absent"

	def _derive_attendance_code_reverse(self):
		if self.get("custom_attendance_code") or not self.status:
			return
		# ["is","not set"] reliably matches NULL/'' Link values (unlike ["in", ["", None]])
		filters = {"maps_to_status": self.status, "leave_type": self.leave_type or ["is", "not set"]}
		code = frappe.db.get_value("Attendance Code", filters, "name")
		if not code:
			return
		self.custom_attendance_code = code
		c = self._get_attendance_code(code)
		self.custom_work_credit = flt(c.work_fraction) if c else 0

	def validate(self):
		from erpnext.controllers.status_updater import validate_status

		validate_status(self.status, ["Present", "Absent", "On Leave", "Half Day", "Work From Home"])
		validate_active_employee(self.employee)
		self.validate_attendance_date()
		self.validate_duplicate_record()
		self.validate_overlapping_shift_attendance()
		self.validate_employee_status()
		self.check_leave_record()
		# check_leave_record forces half_day_status="Absent" when no Leave Application backs the day;
		# undo that for mã-công half-day leaves (the worked half is present). Runs on every save path.
		self.restore_code_driven_half_day_status()

	def on_cancel(self):
		self.unlink_attendance_from_checkins()
		self.reset_skipped_checkins()

	def reset_skipped_checkins(self):
		"""Re-enable auto attendance for check-ins that were auto-skipped (and are still
		unlinked) for this employee & date, so the next `process_auto_attendance` run can
		reprocess them. This Attendance may have been the record that blocked them (e.g. a
		duplicate/overlapping-shift attendance), so cancelling it should un-stick them
		instead of leaving `skip_auto_attendance` set forever."""
		EmployeeCheckin = frappe.qb.DocType("Employee Checkin")
		(
			frappe.qb.update(EmployeeCheckin)
			.set(EmployeeCheckin.skip_auto_attendance, 0)
			.where(
				(EmployeeCheckin.employee == self.employee)
				& (EmployeeCheckin.skip_auto_attendance == 1)
				& (EmployeeCheckin.attendance.isnull() | (EmployeeCheckin.attendance == ""))
				& (Date(EmployeeCheckin.shift_start) == self.attendance_date)
			)
		).run()

	def validate_attendance_date(self):
		date_of_joining = frappe.db.get_value("Employee", self.employee, "date_of_joining")

		if date_of_joining and getdate(self.attendance_date) < getdate(date_of_joining):
			frappe.throw(
				_("Attendance date {0} can not be less than employee {1}'s joining date: {2}").format(
					frappe.bold(format_date(self.attendance_date)),
					frappe.bold(self.employee),
					frappe.bold(format_date(date_of_joining)),
				)
			)

	def validate_duplicate_record(self):
		duplicate = self.get_duplicate_attendance_record()

		if duplicate:
			frappe.throw(
				_("Attendance for employee {0} is already marked for the date {1}: {2}").format(
					frappe.bold(self.employee),
					frappe.bold(format_date(self.attendance_date)),
					get_link_to_form("Attendance", duplicate),
				),
				title=_("Duplicate Attendance"),
				exc=DuplicateAttendanceError,
			)

	def get_duplicate_attendance_record(self) -> str | None:
		Attendance = frappe.qb.DocType("Attendance")
		query = (
			frappe.qb.from_(Attendance)
			.select(Attendance.name)
			.where(
				(Attendance.employee == self.employee)
				& (Attendance.docstatus < 2)
				& (Attendance.attendance_date == self.attendance_date)
				& (Attendance.name != self.name)
				& (
					Attendance.half_day_status.isnull()
					| (Attendance.half_day_status == "")
					| (Attendance.modify_half_day_status == 0)
				)
			)
			.for_update()
		)

		if self.shift:
			query = query.where(
				((Attendance.shift.isnull()) | (Attendance.shift == ""))
				| (
					((Attendance.shift.isnotnull()) | (Attendance.shift != ""))
					& (Attendance.shift == self.shift)
				)
			)

		duplicate = query.run(pluck=True)

		return duplicate[0] if duplicate else None

	def validate_overlapping_shift_attendance(self):
		attendance = self.get_overlapping_shift_attendance()

		if attendance:
			frappe.throw(
				_("Attendance for employee {0} is already marked for an overlapping shift {1}: {2}").format(
					frappe.bold(self.employee),
					frappe.bold(attendance.shift),
					get_link_to_form("Attendance", attendance.name),
				),
				title=_("Overlapping Shift Attendance"),
				exc=OverlappingShiftAttendanceError,
			)

	def get_overlapping_shift_attendance(self) -> dict:
		if not self.shift:
			return {}

		Attendance = frappe.qb.DocType("Attendance")
		same_date_attendance = (
			frappe.qb.from_(Attendance)
			.select(Attendance.name, Attendance.shift)
			.where(
				(Attendance.employee == self.employee)
				& (Attendance.docstatus < 2)
				& (Attendance.attendance_date == self.attendance_date)
				& (Attendance.shift != self.shift)
				& (Attendance.name != self.name)
			)
		).run(as_dict=True)

		for d in same_date_attendance:
			if has_overlapping_timings(self.shift, d.shift):
				return d

		return {}

	def validate_employee_status(self):
		if frappe.db.get_value("Employee", self.employee, "status") == "Inactive":
			frappe.throw(_("Cannot mark attendance for an Inactive employee {0}").format(self.employee))

	def check_leave_record(self):
		LeaveApplication = frappe.qb.DocType("Leave Application")
		leave_record = (
			frappe.qb.from_(LeaveApplication)
			.select(
				LeaveApplication.leave_type,
				LeaveApplication.half_day,
				LeaveApplication.half_day_date,
				LeaveApplication.name,
			)
			.where(
				(LeaveApplication.employee == self.employee)
				& (self.attendance_date >= LeaveApplication.from_date)
				& (self.attendance_date <= LeaveApplication.to_date)
				& (LeaveApplication.status == "Approved")
				& (LeaveApplication.docstatus == 1)
			)
		).run(as_dict=True)

		if leave_record:
			for d in leave_record:
				self.leave_type = d.leave_type
				self.leave_application = d.name
				if d.half_day_date == getdate(self.attendance_date):
					self.status = "Half Day"
					frappe.msgprint(
						_("Employee {0} on Half day on {1}").format(
							self.employee, format_date(self.attendance_date)
						)
					)
				else:
					self.status = "On Leave"
					frappe.msgprint(
						_("Employee {0} is on Leave on {1}").format(
							self.employee, format_date(self.attendance_date)
						)
					)

		if self.status in ("On Leave", "Half Day"):
			if not leave_record:
				self.modify_half_day_status = 0
				self.half_day_status = "Absent"
				frappe.msgprint(
					_("No leave record found for employee {0} on {1}").format(
						self.employee, format_date(self.attendance_date)
					),
					alert=1,
				)
		elif self.leave_type:
			self.leave_type = None
			self.leave_application = None

	def validate_employee(self):
		emp = frappe.db.sql(
			"select name from `tabEmployee` where name = %s and status = 'Active'", self.employee
		)
		if not emp:
			frappe.throw(_("Employee {0} is not active or does not exist").format(self.employee))

	def unlink_attendance_from_checkins(self):
		EmployeeCheckin = frappe.qb.DocType("Employee Checkin")
		linked_logs = (
			frappe.qb.from_(EmployeeCheckin)
			.select(EmployeeCheckin.name)
			.where(EmployeeCheckin.attendance == self.name)
			.for_update()
			.run(as_dict=True)
		)

		if linked_logs:
			(
				frappe.qb.update(EmployeeCheckin)
				.set("attendance", "")
				.where(EmployeeCheckin.attendance == self.name)
			).run()

			frappe.msgprint(
				msg=_("Unlinked Attendance record from Employee Checkins: {}").format(
					", ".join(get_link_to_form("Employee Checkin", log.name) for log in linked_logs)
				),
				title=_("Unlinked logs"),
				indicator="blue",
				is_minimizable=True,
				wide=True,
			)

	def on_update(self):
		self.publish_update()

	def after_delete(self):
		self.publish_update()
		# a deleted draft Attendance can also have been the record blocking auto attendance
		# (duplicate check uses docstatus < 2); un-stick those check-ins too
		self.reset_skipped_checkins()

	def publish_update(self):
		employee_user = frappe.db.get_value("Employee", self.employee, "user_id", cache=True)
		hrms.refetch_resource("hrms:attendance_calendar_events", employee_user)


@frappe.whitelist()
def get_events(start, end, filters=None):
	employee = frappe.db.get_value("Employee", {"user_id": frappe.session.user})
	if not employee:
		return []
	if isinstance(filters, str):
		import json

		filters = json.loads(filters)
	if not filters:
		filters = []
	filters.append(["attendance_date", "between", [get_datetime(start).date(), get_datetime(end).date()]])
	attendance_records = add_attendance(filters)
	add_holidays(attendance_records, start, end, employee)
	return attendance_records


def add_attendance(filters):
	attendance = frappe.get_list(
		"Attendance",
		fields=[
			"name",
			"'Attendance' as doctype",
			"attendance_date",
			"employee_name",
			"status",
			"docstatus",
		],
		filters=filters,
	)
	for record in attendance:
		record["title"] = f"{record.employee_name} : {record.status}"
	return attendance


def add_holidays(events, start, end, employee=None):
	holidays = get_holidays_for_employee(employee, start, end)
	if not holidays:
		return

	for holiday in holidays:
		events.append(
			{
				"doctype": "Holiday",
				"attendance_date": holiday.holiday_date,
				"title": _("Holiday") + ": " + cstr(holiday.description),
				"name": holiday.name,
				"allDay": 1,
			}
		)


def mark_attendance(
	employee,
	attendance_date,
	status,
	shift=None,
	leave_type=None,
	late_entry=False,
	early_exit=False,
	half_day_status=None,
):
	savepoint = "attendance_creation"

	try:
		frappe.db.savepoint(savepoint)
		attendance = frappe.new_doc("Attendance")
		attendance.update(
			{
				"doctype": "Attendance",
				"employee": employee,
				"attendance_date": attendance_date,
				"status": status,
				"shift": shift,
				"leave_type": leave_type,
				"late_entry": late_entry,
				"early_exit": early_exit,
				"half_day_status": half_day_status,
			}
		)
		attendance.insert()
		attendance.submit()
	except (DuplicateAttendanceError, OverlappingShiftAttendanceError):
		frappe.db.rollback(save_point=savepoint)
		return

	return attendance.name


@frappe.whitelist()
def mark_bulk_attendance(data):
	import json

	if isinstance(data, str):
		data = json.loads(data)
	data = frappe._dict(data)
	if not data.unmarked_days:
		frappe.throw(_("Please select a date."))
		return

	for date in data.unmarked_days:
		doc_dict = {
			"doctype": "Attendance",
			"employee": data.employee,
			"attendance_date": get_datetime(date),
			"status": data.status,
			"half_day_status": "Absent" if data.status == "Half Day" else None,
		}
		attendance = frappe.get_doc(doc_dict).insert()
		attendance.submit()


@frappe.whitelist()
def get_unmarked_days(employee, from_date, to_date, exclude_holidays=0):
	joining_date, relieving_date = frappe.get_cached_value(
		"Employee", employee, ["date_of_joining", "relieving_date"]
	)

	from_date = max(getdate(from_date), joining_date or getdate(from_date))
	to_date = min(getdate(to_date), relieving_date or getdate(to_date))

	records = frappe.get_all(
		"Attendance",
		fields=["attendance_date", "employee"],
		filters=[
			["attendance_date", ">=", from_date],
			["attendance_date", "<=", to_date],
			["employee", "=", employee],
			["docstatus", "!=", 2],
		],
	)

	marked_days = [getdate(record.attendance_date) for record in records]

	if cint(exclude_holidays):
		holiday_dates = get_holiday_dates_for_employee(employee, from_date, to_date)
		holidays = [getdate(record) for record in holiday_dates]
		marked_days.extend(holidays)

	unmarked_days = []

	while from_date <= to_date:
		if from_date not in marked_days:
			unmarked_days.append(from_date)

		from_date = add_days(from_date, 1)

	return unmarked_days
