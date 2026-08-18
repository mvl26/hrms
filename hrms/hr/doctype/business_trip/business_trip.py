# Copyright (c) 2026, Miyano Việt Nam.
"""Business Trip (Business Trip) — a multi-person trip request driven by a Frappe Workflow
(Nháp -> Chờ COO duyệt -> COO đã duyệt -> Đã ra QĐ -> Hoàn tất). Desk-only; never touches
Attendance or payroll. Trip expenses are separate per-traveler Expense Claims linked back here."""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, getdate


class BusinessTrip(Document):
	def validate(self):
		self.validate_dates()
		self.validate_travelers()
		self.validate_approver()

	def validate_dates(self):
		if self.from_date and self.to_date and getdate(self.from_date) > getdate(self.to_date):
			frappe.throw(_("Từ ngày không được sau Đến ngày."))

	def validate_travelers(self):
		if not self.travelers:
			frappe.throw(_("Vui lòng thêm ít nhất một người đi công tác."))

	def validate_approver(self):
		# Người duyệt (COO) bắt buộc trước khi rời trạng thái Nháp (trình duyệt qua workflow).
		if self.workflow_state and self.workflow_state != "Nháp" and not self.approver_coo:
			frappe.throw(_("Cần chọn người duyệt (COO) trước khi trình duyệt."))

	# --- notifications / assignment on workflow state change ---
	def on_update(self):
		self.notify_on_state_change()

	def on_update_after_submit(self):
		self.notify_on_state_change()

	def notify_on_state_change(self):
		"""Assign a ToDo (+ bell notification) to the right actor when the workflow moves on."""
		if not self.has_value_changed("workflow_state"):
			return
		state = self.workflow_state
		if state == "Chờ COO duyệt":
			self.assign_actor(self.approver_coo, _("Duyệt đề nghị công tác {0}").format(self.name))
		elif state == "COO đã duyệt":
			self.create_travel_attendance()  # approved → mark travel days as CT (đi công tác)
			for user in self.hr_manager_users():
				self.assign_actor(user, _("Ra QĐ cử đi công tác {0}").format(self.name))
		elif state == "Đã ra QĐ":
			self.assign_actor(
				self.employee_user(self.registered_by),
				_("Làm đề nghị thanh toán công tác {0}").format(self.name),
			)

	def assign_actor(self, user, description):
		if not user:
			return
		if frappe.get_all(
			"ToDo",
			filters={
				"reference_type": "Business Trip",
				"reference_name": self.name,
				"allocated_to": user,
				"status": "Open",
			},
			limit=1,
		):
			return  # already assigned — don't duplicate
		from frappe.desk.form.assign_to import add as assign_add

		assign_add(
			{"assign_to": [user], "doctype": "Business Trip", "name": self.name, "description": description}
		)

	def hr_manager_users(self):
		users = frappe.get_all(
			"Has Role", filters={"role": "HR Manager", "parenttype": "User"}, pluck="parent"
		)
		return [u for u in set(users) if frappe.db.get_value("User", u, "enabled")]

	def employee_user(self, employee):
		return frappe.db.get_value("Employee", employee, "user_id") if employee else None

	# --- attendance integration (đi công tác → mã CT) ---
	def create_travel_attendance(self):
		"""On approval, mark each traveler's working days in the trip window as 'CT' (đi công tác).
		Skips holidays/weekends and days that already have an Attendance record. CT maps to native
		Work From Home (a paid working day) via the attendance-code bridge — payroll-neutral."""
		from frappe.utils import add_days, getdate

		from erpnext.setup.doctype.employee.employee import is_holiday

		if not frappe.db.exists("Attendance Code", "CT"):
			return
		start, end = getdate(self.from_date), getdate(self.to_date)
		for t in self.travelers:
			day = start
			while day <= end:
				if not is_holiday(t.employee, day, raise_exception=False):
					auto_filled = self.auto_filled_attendance(t.employee, day)
					if auto_filled:
						self.convert_auto_filled_to_trip(auto_filled)
					elif not self.has_attendance(t.employee, day):
						att = frappe.get_doc(
							{
								"doctype": "Attendance",
								"employee": t.employee,
								"attendance_date": day,
								"custom_attendance_code": "CT",
								"company": self.company
								or frappe.db.get_value("Employee", t.employee, "company"),
							}
						)
						att.flags.ignore_permissions = True
						att.insert(ignore_permissions=True)
						att.submit()
				day = add_days(day, 1)

	def attendance_row(self, employee, date):
		return frappe.db.get_value(
			"Attendance",
			{"employee": employee, "attendance_date": date, "docstatus": ["<", 2]},
			["name", "custom_auto_filled", "in_time", "out_time"],
			as_dict=True,
		)

	def has_attendance(self, employee, date):
		return bool(self.attendance_row(employee, date))

	def auto_filled_attendance(self, employee, date) -> str | None:
		"""Ngày công do máy sinh cho người miễn chấm công (và chưa có giờ vào/ra thật) — coi như ô
		trống: chuyến công tác được phép ghi đè thành CT. Mọi bản ghi khác là dữ liệu thật."""
		row = self.attendance_row(employee, date)
		if row and cint(row.custom_auto_filled) and not row.in_time and not row.out_time:
			return row.name
		return None

	def convert_auto_filled_to_trip(self, attendance: str):
		"""X (tự sinh) -> CT trên bản ghi ĐÃ SUBMIT.

		Dùng `db_set` chứ không `save`: không field mã công nào có `allow_on_submit`, `save` sẽ ném
		lỗi. Đây đúng khuôn mà `leave_application.create_or_update_attendance` đang dùng.
		`custom_work_credit` không đổi (X và CT đều `work_fraction = 1.0`), và `Present ->
		Work From Home` không đụng lương (payroll chỉ trừ theo Absent / Half Day / leave_type LWP)."""
		from hrms.hr.period_lock import is_period_locked

		doc = frappe.get_doc("Attendance", attendance)
		if is_period_locked(doc.employee, doc.attendance_date):
			return
		doc.db_set({"custom_attendance_code": "CT", "status": "Work From Home", "custom_auto_filled": 0})
		doc.add_comment(
			"Comment",
			_("Chuyển công tự sinh (miễn chấm công) sang CT theo Công Tác {0}").format(self.name),
		)

	# --- expense claim (per-traveler payment) ---
	@frappe.whitelist()
	def make_expense_claim(self, employee: str | None = None):
		"""Return a PREFILLED (unsaved) Expense Claim for one traveler — linked to this trip, with
		the trip's COO as expense_approver. The traveler completes the expense rows and saves; the
		claim links back via the Expense Claim hook. Defaults to the current user's employee."""
		if self.workflow_state not in ("Đã ra QĐ", "Hoàn tất"):
			frappe.throw(_("Chỉ tạo đề nghị thanh toán sau khi chuyến đã được duyệt và ra QĐ."))

		employee = employee or frappe.db.get_value("Employee", {"user_id": frappe.session.user}, "name")
		if not employee:
			frappe.throw(_("Không xác định được nhân viên của bạn."))

		row = next((t for t in self.travelers if t.employee == employee), None)
		if not row:
			frappe.throw(_("Nhân viên không có trong danh sách người đi công tác của chuyến này."))
		existing = row.expense_claim or frappe.db.exists(
			"Expense Claim", {"custom_business_trip": self.name, "employee": employee, "docstatus": ["<", 2]}
		)
		if existing:
			frappe.throw(_("Đã có đề nghị thanh toán cho người này: {0}").format(existing))

		claim = frappe.new_doc("Expense Claim")
		claim.employee = employee
		claim.company = self.company or frappe.db.get_value("Employee", employee, "company")
		claim.custom_business_trip = self.name
		claim.expense_approver = self.approver_coo
		return claim.as_dict()


def link_claim_to_trip(doc, method=None):
	"""Expense Claim hook: when a claim carrying custom_business_trip is created, write it back onto
	the matching traveler row so per-person trip costs are traceable."""
	trip = doc.get("custom_business_trip")
	if not trip or not doc.get("employee"):
		return
	row = frappe.db.get_value("Business Trip Traveler", {"parent": trip, "employee": doc.employee}, "name")
	if row:
		frappe.db.set_value("Business Trip Traveler", row, "expense_claim", doc.name, update_modified=False)
