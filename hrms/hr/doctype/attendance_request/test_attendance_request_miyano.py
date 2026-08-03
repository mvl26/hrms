# Copyright (c) 2026, Miyano Việt Nam.
"""Miyano — tách bạch Yêu cầu chấm công khỏi Đơn xin nghỉ.

Kênh Attendance Request được mở lại (đã từng khoá) có DUYỆT bởi quản lý trực tiếp, và ghi mã công
riêng (W/CT/X) — thuần hiển thị, lương bất biến. Chạy qua harness rollback (KHÔNG bench run-tests
trên miyano). Test hook bằng thuộc tính in-memory (KHÔNG insert Custom Field/Property Setter — bẫy DDL).
"""

import json
import os

import frappe
from frappe.tests.utils import FrappeTestCase

from hrms.tests.isolation import PerTestRollback
from hrms.tests.vn_test_utils import test_employee

_FIX_DIR = os.path.join(frappe.get_app_path("hrms"), "fixtures")
_FIXTURE = os.path.join(_FIX_DIR, "attendance_code.json")

# 4 tình huống yêu cầu chấm công (giá trị reason) — WFH/On Duty là option native, 2 cái sau Miyano thêm.
EXPECTED_REASONS = {"Work From Home", "On Duty", "Quên chấm công", "Đi muộn/về sớm"}


def _codes():
	with open(_FIXTURE, encoding="utf-8") as f:
		return {c["name"]: c for c in json.load(f)}


def _load_fixture(name):
	with open(os.path.join(_FIX_DIR, f"{name}.json"), encoding="utf-8") as f:
		return json.load(f)


class TestAttendanceCodeFixturesW(PerTestRollback, FrappeTestCase):
	"""T1 — mã công W (mới) cho kênh yêu cầu chấm công; on-duty tái dùng CT có sẵn."""

	def test_W_work_from_home_paid_full(self):
		w = _codes().get("W")
		self.assertIsNotNone(w, "thiếu Attendance Code 'W' trong fixture")
		self.assertEqual(w["category"], "Công")
		self.assertEqual(w["maps_to_status"], "Work From Home")  # cùng status CT → payroll-neutral
		self.assertEqual(w["work_fraction"], 1.0)
		self.assertEqual(w["is_paid"], 1)

	def test_on_duty_reuses_existing_CT(self):
		# on-duty (ra ngoài công việc = công tác) hiện mã CT có sẵn — không thêm mã mới.
		ct = _codes().get("CT")
		self.assertIsNotNone(ct, "thiếu Attendance Code 'CT'")
		self.assertEqual(ct["category"], "Công")
		self.assertEqual(ct["work_fraction"], 1.0)
		self.assertEqual(ct["is_paid"], 1)

	def test_fixture_json_valid(self):
		# đọc được = JSON hợp lệ; đảm bảo không phá các mã cũ.
		codes = _codes()
		for required in ("X", "CT", "P", "W"):
			self.assertIn(required, codes)
		self.assertNotIn("CV", codes)  # đã bỏ CV, dùng CT cho công tác/on-duty


class TestAttendanceRequestFixtures(PerTestRollback, FrappeTestCase):
	"""T2 — field người duyệt + mở rộng options reason, đồng bộ bộ lọc fixtures."""

	def _custom_fields(self):
		return {c["name"]: c for c in _load_fixture("custom_field")}

	def test_custom_approver_field_defined(self):
		cf = self._custom_fields().get("Attendance Request-custom_approver")
		self.assertIsNotNone(cf, "thiếu Custom Field Attendance Request-custom_approver")
		self.assertEqual(cf["dt"], "Attendance Request")
		self.assertEqual(cf["fieldtype"], "Link")
		self.assertEqual(cf["options"], "User")  # người duyệt = User

	def test_custom_approver_in_hooks_fixture_filter(self):
		import hrms.hooks as hooks

		names = set()
		for entry in hooks.fixtures:
			if isinstance(entry, dict) and entry.get("dt") == "Custom Field":
				nf = (entry.get("filters") or {}).get("name")
				if isinstance(nf, list | tuple) and nf and nf[0] == "in":
					names |= set(nf[1])
		self.assertIn("Attendance Request-custom_approver", names)

	def test_reason_property_setter_extends_options(self):
		ps = {p["name"]: p for p in _load_fixture("property_setter")}
		reason_ps = next(
			(
				p
				for p in ps.values()
				if p.get("doc_type") == "Attendance Request"
				and p.get("field_name") == "reason"
				and p.get("property") == "options"
			),
			None,
		)
		self.assertIsNotNone(reason_ps, "thiếu Property Setter mở rộng options reason")
		opts = {o for o in (reason_ps["value"] or "").split("\n") if o}
		self.assertEqual(opts, EXPECTED_REASONS)

	def test_reason_property_setter_in_hooks_fixtures(self):
		import hrms.hooks as hooks

		has_ps = any(isinstance(e, dict) and e.get("dt") == "Property Setter" for e in hooks.fixtures)
		self.assertTrue(has_ps, "hooks.fixtures chưa export Property Setter")


def _flatten(hook_val):
	if not hook_val:
		return []
	return [hook_val] if isinstance(hook_val, str) else list(hook_val)


class TestAttendanceRequestApproval(PerTestRollback, FrappeTestCase):
	"""T3 — mở lại Attendance Request có DUYỆT bởi quản lý trực tiếp (reports_to)."""

	def _mgr_emp(self):
		mgr = frappe.db.get_value("Employee", {"status": "Active", "user_id": ["is", "set"]}, "name")
		mgr_user = frappe.db.get_value("Employee", mgr, "user_id")
		emp = frappe.db.get_value("Employee", {"status": "Active", "name": ["!=", mgr]}, "name")
		return mgr, mgr_user, emp

	def _no_role_user(self):
		email = "attreq_norole@example.com"
		if not frappe.db.exists("User", email):
			u = frappe.get_doc(
				{"doctype": "User", "email": email, "first_name": "NoRole", "send_welcome_email": 0}
			)
			u.flags.ignore_permissions = True
			u.insert(ignore_permissions=True)
		return email

	# --- người duyệt mặc định = quản lý trực tiếp ---
	def test_default_approver_from_reports_to(self):
		from hrms.hr.doctype.attendance_request.attendance_request_miyano import set_default_approver

		mgr, mgr_user, emp = self._mgr_emp()
		frappe.db.set_value("Employee", emp, "reports_to", mgr)
		doc = frappe._dict(doctype="Attendance Request", employee=emp)
		set_default_approver(doc)
		self.assertEqual(doc.get("custom_approver"), mgr_user)

	def test_default_approver_not_overwritten(self):
		from hrms.hr.doctype.attendance_request.attendance_request_miyano import set_default_approver

		mgr, mgr_user, emp = self._mgr_emp()
		frappe.db.set_value("Employee", emp, "reports_to", mgr)
		doc = frappe._dict(doctype="Attendance Request", employee=emp, custom_approver="Administrator")
		set_default_approver(doc)
		self.assertEqual(doc.get("custom_approver"), "Administrator")  # chọn tay được giữ

	# --- quyền duyệt ---
	def test_authorized_admin_and_approver(self):
		from hrms.hr.doctype.attendance_request.attendance_request_miyano import is_authorized_approver

		_, mgr_user, _ = self._mgr_emp()
		doc = frappe._dict(custom_approver=mgr_user)
		self.assertTrue(is_authorized_approver(doc))  # Administrator (session mặc định)
		frappe.set_user(mgr_user)
		try:
			self.assertTrue(is_authorized_approver(doc))  # đúng người duyệt
		finally:
			frappe.set_user("Administrator")

	def test_unauthorized_non_approver(self):
		from hrms.hr.doctype.attendance_request.attendance_request_miyano import is_authorized_approver

		_, mgr_user, _ = self._mgr_emp()
		other = self._no_role_user()
		frappe.set_user(other)
		try:
			self.assertFalse(is_authorized_approver(frappe._dict(custom_approver=mgr_user)))
		finally:
			frappe.set_user("Administrator")

	def test_guard_blocks_non_approver_outside_tests(self):
		from hrms.hr.doctype.attendance_request.attendance_request_miyano import guard_submit

		_, mgr_user, _ = self._mgr_emp()
		other = self._no_role_user()
		frappe.flags.in_test = False
		frappe.set_user(other)
		try:
			with self.assertRaises(frappe.ValidationError):
				guard_submit(frappe._dict(custom_approver=mgr_user))
		finally:
			frappe.set_user("Administrator")
			frappe.flags.in_test = True

	def test_guard_allows_approver_outside_tests(self):
		from hrms.hr.doctype.attendance_request.attendance_request_miyano import guard_submit

		_, mgr_user, _ = self._mgr_emp()
		frappe.flags.in_test = False
		frappe.set_user(mgr_user)
		try:
			self.assertIsNone(guard_submit(frappe._dict(custom_approver=mgr_user)))
		finally:
			frappe.set_user("Administrator")
			frappe.flags.in_test = True

	def test_guard_skips_during_tests(self):
		# tha khi in_test → không phá 10 test upstream của Attendance Request.
		from hrms.hr.doctype.attendance_request.attendance_request_miyano import guard_submit

		other = self._no_role_user()
		frappe.set_user(other)
		try:
			self.assertIsNone(guard_submit(frappe._dict(custom_approver="x@y")))
		finally:
			frappe.set_user("Administrator")

	# --- giao ToDo + wiring ---
	def test_assign_creates_todo_for_approver(self):
		mgr, mgr_user, emp = self._mgr_emp()
		frappe.db.set_value("Employee", emp, "reports_to", mgr)
		ar = frappe.get_doc(
			{
				"doctype": "Attendance Request",
				"employee": emp,
				"company": frappe.db.get_value("Employee", emp, "company"),
				"from_date": "2098-06-01",
				"to_date": "2098-06-01",
				"reason": "On Duty",
			}
		)
		ar.insert(ignore_permissions=True)  # bản nháp (chưa submit)
		self.assertEqual(ar.get("custom_approver"), mgr_user)  # tự điền người duyệt
		todo = frappe.get_all(
			"ToDo",
			filters={
				"reference_type": "Attendance Request",
				"reference_name": ar.name,
				"allocated_to": mgr_user,
			},
		)
		self.assertTrue(todo, "phải giao ToDo cho người duyệt")

	def test_hooks_wired(self):
		events = frappe.get_hooks("doc_events").get("Attendance Request", {})
		base = "hrms.hr.doctype.attendance_request.attendance_request_miyano."
		self.assertIn(base + "set_default_approver", _flatten(events.get("before_insert")))
		self.assertIn(base + "guard_submit", _flatten(events.get("before_submit")))
		self.assertIn(base + "set_attendance_request_code", _flatten(events.get("on_submit")))


class TestAttendanceRequestCode(PerTestRollback, FrappeTestCase):
	"""T4 — mã công theo reason (payroll-neutral). WFH→W, On Duty→CT, quên/muộn→X."""

	def setUp(self):
		self.emp = test_employee()
		self.company = frappe.db.get_value("Employee", self.emp, "company")

	def _att(self, status, date, half=False, half_status="Absent"):
		d = {
			"doctype": "Attendance",
			"employee": self.emp,
			"attendance_date": date,
			"company": self.company,
			"status": status,
		}
		if half:
			d["status"] = "Half Day"
			d["half_day_status"] = half_status
		att = frappe.get_doc(d)
		att.insert(ignore_permissions=True)
		att.submit()
		return att.name

	def _apply(self, att_name, reason, half=False, half_date=None):
		from hrms.hr.doctype.attendance_request.attendance_request_miyano import set_attendance_request_code

		ar_name = "FAKE-AR-" + att_name  # bỏ qua link validation bằng db.set_value
		frappe.db.set_value("Attendance", att_name, "attendance_request", ar_name, update_modified=False)
		doc = frappe._dict(
			name=ar_name,
			reason=reason,
			half_day=1 if half else 0,
			half_day_date=half_date,
		)
		set_attendance_request_code(doc)

	def _code(self, name):
		return frappe.db.get_value(
			"Attendance",
			name,
			[
				"custom_attendance_code",
				"custom_morning_code",
				"custom_afternoon_code",
				"status",
				"half_day_status",
			],
			as_dict=True,
		)

	def test_wfh_sets_W(self):
		n = self._att("Work From Home", "2098-08-01")
		self._apply(n, "Work From Home")
		self.assertEqual(self._code(n).custom_attendance_code, "W")  # ghi đè CT mặc định

	def test_on_duty_sets_CT(self):
		n = self._att("Present", "2098-08-02")
		self._apply(n, "On Duty")
		self.assertEqual(self._code(n).custom_attendance_code, "CT")  # công tác/on-duty → CT

	def test_missed_punch_sets_X(self):
		n = self._att("Present", "2098-08-03")
		self._apply(n, "Quên chấm công")
		self.assertEqual(self._code(n).custom_attendance_code, "X")

	def test_late_early_sets_X(self):
		n = self._att("Present", "2098-08-04")
		self._apply(n, "Đi muộn/về sớm")
		self.assertEqual(self._code(n).custom_attendance_code, "X")

	def test_code_is_payroll_neutral(self):
		# hook chỉ đổi field hiển thị; status/half_day_status giữ nguyên như native đặt.
		n = self._att("Work From Home", "2098-08-05")
		before = self._code(n)
		self._apply(n, "Work From Home")
		after = self._code(n)
		self.assertEqual((before.status, before.half_day_status), (after.status, after.half_day_status))

	def test_half_day_only_worked_half_is_W_over_K(self):
		# chỉ làm nửa ngày WFH (nửa kia native half_day_status=Absent, trừ 0.5) → W/K (không lương)
		n = self._att("Half Day", "2098-08-06", half=True, half_status="Absent")
		self._apply(n, "Work From Home", half=True, half_date="2098-08-06")
		c = self._code(n)
		self.assertEqual(c.status, "Half Day")  # payroll giữ nguyên
		self.assertEqual(c.custom_morning_code, "W")  # buổi làm tại nhà
		self.assertEqual(c.custom_afternoon_code, "K")  # buổi còn lại không lương (không phải vắng)

	def test_half_day_full_attendance_is_W_over_X(self):
		# WFH nửa buổi nhưng buổi kia vẫn đi làm → native half_day_status=Present (payroll KHÔNG trừ 0.5).
		# (check_leave_record ép Absent khi không có đơn nghỉ, nên set thẳng để mô phỏng buổi kia có mặt.)
		n = self._att("Half Day", "2098-08-07", half=True)
		frappe.db.set_value("Attendance", n, "half_day_status", "Present", update_modified=False)
		self._apply(n, "Work From Home", half=True, half_date="2098-08-07")
		c = self._code(n)
		self.assertEqual(c.status, "Half Day")
		self.assertEqual(c.half_day_status, "Present")  # hook không đụng → payroll trả đủ ngày
		self.assertEqual(c.custom_morning_code, "W")
		self.assertEqual(c.custom_afternoon_code, "X")  # đi làm đủ → W/X

	def test_full_flow_wfh_end_to_end(self):
		# tạo + submit Attendance Request thật (reason native) → native sinh Attendance + hook ghi W.
		date = "2098-09-07"
		ar = frappe.get_doc(
			{
				"doctype": "Attendance Request",
				"employee": self.emp,
				"company": self.company,
				"from_date": date,
				"to_date": date,
				"reason": "Work From Home",
			}
		)
		ar.insert(ignore_permissions=True)
		ar.submit()  # guard tha khi in_test
		att = frappe.db.get_value(
			"Attendance",
			{"attendance_request": ar.name},
			["status", "custom_attendance_code"],
			as_dict=True,
		)
		self.assertIsNotNone(att, "submit phải sinh Attendance")
		self.assertEqual(att.status, "Work From Home")
		self.assertEqual(att.custom_attendance_code, "W")


class TestAttendanceRequestPayrollInvariance(PerTestRollback, FrappeTestCase):
	"""T5 — GATE: ngày tạo qua Yêu cầu chấm công (WFH/On Duty/quên/muộn) KHÔNG làm đổi lương so với
	một ngày Present thường. Payroll chỉ đọc Attendance qua ``get_employee_attendance`` (lọc
	status ∈ Absent/Half Day/On Leave) → mọi ngày làm việc (Present/Work From Home) đều vô hình
	với khấu trừ = trả đủ công."""

	def setUp(self):
		self.emp = test_employee()
		self.company = frappe.db.get_value("Employee", self.emp, "company")

	def _att(self, status, date):
		att = frappe.get_doc(
			{
				"doctype": "Attendance",
				"employee": self.emp,
				"attendance_date": date,
				"company": self.company,
				"status": status,
			}
		)
		att.insert(ignore_permissions=True)
		att.submit()
		return att.name

	def _apply(self, att_name, reason):
		from hrms.hr.doctype.attendance_request.attendance_request_miyano import set_attendance_request_code

		frappe.db.set_value(
			"Attendance", att_name, "attendance_request", "FAKE-AR-" + att_name, update_modified=False
		)
		set_attendance_request_code(frappe._dict(name="FAKE-AR-" + att_name, reason=reason))

	def test_attendance_request_days_are_payroll_invisible(self):
		wfh = self._att("Work From Home", "2098-10-01")
		self._apply(wfh, "Work From Home")  # W
		onduty = self._att("Present", "2098-10-02")
		self._apply(onduty, "On Duty")  # CT
		missed = self._att("Present", "2098-10-03")
		self._apply(missed, "Quên chấm công")  # X
		self._att("Present", "2098-10-04")  # ngày Present thường (đối chứng)
		self._att("Absent", "2098-10-06")  # ngày vắng (đối chứng "query có hoạt động")

		ss = frappe.new_doc("Salary Slip")
		ss.employee = self.emp
		rows = ss.get_employee_attendance("2098-10-01", "2098-10-31")
		dates = {str(r["attendance_date"]) for r in rows}

		# các ngày qua yêu cầu chấm công + ngày Present thường: không xuất hiện trong khấu trừ lương
		for working_day in ("2098-10-01", "2098-10-02", "2098-10-03", "2098-10-04"):
			self.assertNotIn(working_day, dates, f"{working_day} không được ảnh hưởng lương")
		self.assertIn("2098-10-06", dates, "ngày Absent phải vào khấu trừ (đối chứng)")

	def test_lwp_and_absent_counts_unchanged(self):
		# một tháng chỉ có ngày làm việc qua yêu cầu chấm công + 1 ngày vắng → absent=1, lwp=0.
		self._apply(self._att("Work From Home", "2098-11-02"), "Work From Home")
		self._apply(self._att("Present", "2098-11-03"), "On Duty")
		self._apply(self._att("Present", "2098-11-04"), "Đi muộn/về sớm")
		self._att("Absent", "2098-11-05")

		ss = frappe.new_doc("Salary Slip")
		ss.employee = self.emp
		ss.start_date = "2098-11-01"
		ss.end_date = "2098-11-30"  # actual_end_date suy từ end_date
		lwp, absent = ss.calculate_lwp_ppl_and_absent_days_based_on_attendance(
			holidays=[], daily_wages_fraction_for_half_day=0.5, consider_marked_attendance_on_holidays=False
		)
		self.assertEqual(absent, 1)  # chỉ ngày Absent
		self.assertEqual(lwp, 0)  # WFH/On Duty/muộn-sớm không tạo LWP


class TestApprovedRequestSurvivesRebuild(PerTestRollback, FrappeTestCase):
	"""Yêu cầu chấm công đã duyệt phải THẮNG auto-attendance, không chỉ lúc submit.

	Yêu cầu chỉ ghi ra Attendance đúng một lần (`create_or_update_attendance` trong `on_submit`).
	Sau đó bất kỳ lần nào ngày công được dựng lại — chạy công cụ rebuild, HR huỷ rồi chấm lại, hoặc
	bản ghi bị xoá — auto-attendance thấy ngày trống là chấm **Vắng**, vì `get_dates_for_attendance`
	chỉ trừ ngày lễ và ngày đã có bản ghi, không hề hỏi Yêu cầu chấm công.

	Hệ quả người dùng thấy: "tôi có yêu cầu WFH đã duyệt mà ngày đó vẫn bị ghi vắng mặt".
	"""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.shift = "VN AR Rebuild Shift (test)"
		if not frappe.db.exists("Shift Type", cls.shift):
			frappe.get_doc(
				{
					"doctype": "Shift Type",
					"__newname": cls.shift,
					"start_time": "08:00:00",
					"end_time": "17:30:00",
					"enable_auto_attendance": 1,
				}
			).insert()

	def setUp(self):
		from erpnext.setup.doctype.employee.test_employee import make_employee

		from hrms.tests.vn_test_utils import default_company

		self.company = default_company()
		self.emp = make_employee("ar_rebuild@wfh.test", company=self.company, date_of_joining="2098-01-01")
		frappe.db.set_value("Employee", self.emp, "default_shift", self.shift)
		self.day = "2098-05-06"  # thứ Hai

	def approve_wfh(self):
		ar = frappe.get_doc(
			{
				"doctype": "Attendance Request",
				"employee": self.emp,
				"from_date": self.day,
				"to_date": self.day,
				"reason": "Work From Home",
				"company": self.company,
				"custom_approver": frappe.session.user,
			}
		)
		ar.insert()
		ar.submit()
		return ar

	def attendance(self):
		return frappe.db.get_value(
			"Attendance",
			{"employee": self.emp, "attendance_date": self.day, "docstatus": ["<", 2]},
			["status", "attendance_request", "custom_attendance_code"],
			as_dict=True,
		)

	def wipe_attendance(self):
		"""Mô phỏng ngày công bị dựng lại: xoá bản ghi rồi để auto-attendance chạy lại."""
		att = frappe.db.get_value(
			"Attendance", {"employee": self.emp, "attendance_date": self.day, "docstatus": ["<", 2]}
		)
		doc = frappe.get_doc("Attendance", att)
		if doc.docstatus == 1:
			doc.cancel()
		frappe.delete_doc("Attendance", att, force=1, ignore_permissions=True)

	def run_auto_attendance(self):
		shift = frappe.get_doc("Shift Type", self.shift)
		shift.process_attendance_after = "2098-05-01"
		shift.last_sync_of_checkin = "2098-05-31 23:59:59"
		shift.save()
		shift.reload()
		shift.process_auto_attendance()

	def test_the_request_marks_the_day_on_submit(self):
		self.approve_wfh()
		self.assertEqual(self.attendance().status, "Work From Home")

	def test_the_day_is_not_marked_absent_after_a_rebuild(self):
		self.approve_wfh()
		self.wipe_attendance()
		self.run_auto_attendance()
		self.assertNotEqual(
			(self.attendance() or frappe._dict()).status,
			"Absent",
			"có yêu cầu WFH đã duyệt mà vẫn bị chấm vắng",
		)

	def test_the_day_goes_back_to_work_from_home_after_a_rebuild(self):
		self.approve_wfh()
		self.wipe_attendance()
		self.run_auto_attendance()
		att = self.attendance()
		self.assertIsNotNone(att, "ngày có yêu cầu đã duyệt không được để trống")
		self.assertEqual(att.status, "Work From Home")
		self.assertTrue(att.attendance_request, "bản ghi dựng lại phải gắn về đúng yêu cầu")


class TestRequestAlwaysLinksItsDay(PerTestRollback, FrappeTestCase):
	"""Dựng lại ngày công phải GẮN LẠI đơn đã duyệt, kể cả khi status trùng nhau.

	`create_or_update_attendance` chỉ ghi khi `old_status != status`. Đơn on-duty / quên chấm công
	đều quy ra `Present`; ngày công dựng lại từ lượt chấm cũng ra `Present`. Status trùng nên đơn
	KHÔNG được gắn lại: `attendance_request` để trống và mã hiển thị (CT) không bao giờ được ghi.
	Nhìn vào ngày công không biết nó có đơn đã duyệt hay không.

	(Nộp đơn mới cho ngày đã cùng status thì upstream chặn ngay từ `validate`, nên tình huống này
	chỉ xuất hiện sau khi dữ liệu bị dựng lại — đúng ca `HR-ARQ-26-07-00004` trên site.)
	"""

	def setUp(self):
		from erpnext.setup.doctype.employee.test_employee import make_employee

		from hrms.tests.vn_test_utils import default_company

		self.company = default_company()
		self.emp = make_employee("ar_link@onduty.test", company=self.company, date_of_joining="2098-01-01")
		self.day = "2098-05-07"

	def approved_on_duty(self):
		ar = frappe.get_doc(
			{
				"doctype": "Attendance Request",
				"employee": self.emp,
				"from_date": self.day,
				"to_date": self.day,
				"reason": "On Duty",
				"company": self.company,
				"custom_approver": frappe.session.user,
			}
		)
		ar.insert()
		ar.submit()
		return ar

	def attendance(self):
		return frappe.db.get_value(
			"Attendance",
			{"employee": self.emp, "attendance_date": self.day, "docstatus": ["<", 2]},
			["name", "status", "attendance_request", "custom_attendance_code"],
			as_dict=True,
		)

	def test_reapplying_relinks_the_day_even_when_the_status_already_matches(self):
		from hrms.hr.doctype.attendance_request.attendance_request_miyano import (
			reapply_attendance_request,
		)

		ar = self.approved_on_duty()
		att = self.attendance()
		self.assertEqual(att.status, "Present")

		# mô phỏng ngày công được dựng lại: cùng status nhưng mất liên kết và mất mã
		frappe.db.set_value(
			"Attendance",
			att.name,
			{"attendance_request": None, "custom_attendance_code": "X"},
			update_modified=False,
		)

		reapply_attendance_request(self.emp, self.day)

		lai = self.attendance()
		self.assertEqual(lai.attendance_request, ar.name, "phải gắn lại về đơn đã duyệt")
		self.assertEqual(lai.custom_attendance_code, "CT", "on-duty phải mang lại mã hiển thị CT")
