# Copyright (c) 2026, Miyano Việt Nam.
"""Miyano — nhân viên miễn chấm công: ngày làm việc tự sinh đủ công (mã X).

Chạy qua harness rollback (KHÔNG `bench --site miyano run-tests`). Test chỉ ĐỌC custom field,
không bao giờ insert Custom Field trong test (DDL → implicit commit → rò rỉ vào site thật).
"""

import json
import os

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, getdate

from hrms.tests.isolation import PerTestRollback
from hrms.tests.vn_test_utils import test_employee

_CF = os.path.join(frappe.get_app_path("hrms"), "fixtures", "custom_field.json")

EXEMPT_FIELDS = {
	"Employee-custom_exempt_from_checkin": ("Employee", "Check"),
	"Employee-custom_exempt_from_checkin_from": ("Employee", "Date"),
	"Attendance-custom_auto_filled": ("Attendance", "Check"),
}


def custom_fields():
	with open(_CF, encoding="utf-8") as f:
		return {c["name"]: c for c in json.load(f)}


class TestExemptFixtures(PerTestRollback, FrappeTestCase):
	"""E1 — ba custom field của tính năng có trong fixtures VÀ trong bộ lọc hooks."""

	def test_fields_defined_in_fixtures(self):
		defined = custom_fields()
		for name, (dt, fieldtype) in EXEMPT_FIELDS.items():
			with self.subTest(name=name):
				cf = defined.get(name)
				self.assertIsNotNone(cf, f"thiếu Custom Field {name} trong fixtures")
				self.assertEqual(cf["dt"], dt)
				self.assertEqual(cf["fieldtype"], fieldtype)

	def test_auto_filled_is_read_only(self):
		# cờ nguồn gốc do máy ghi — người dùng sửa tay là mở đường cho Công Tác đè nhầm dữ liệu thật
		self.assertEqual(custom_fields()["Attendance-custom_auto_filled"]["read_only"], 1)

	def test_fields_in_hooks_fixture_filter(self):
		import hrms.hooks as hooks

		names = set()
		for entry in hooks.fixtures:
			if isinstance(entry, dict) and entry.get("dt") == "Custom Field":
				nf = (entry.get("filters") or {}).get("name")
				if isinstance(nf, list | tuple) and nf and nf[0] == "in":
					names |= set(nf[1])
		for name in EXEMPT_FIELDS:
			self.assertIn(name, names, f"{name} chưa có trong bộ lọc fixtures của hooks.py")


# --- E2: ai được miễn, ngày nào ------------------------------------------------------------

# Neo ở 2099: không nằm trong Holiday List nào của site → mọi ngày là ngày làm việc, và không đụng
# dữ liệu thật. Cùng quy ước với các test VN khác.
ANCHOR = getdate("2099-06-15")


def make_exempt_employee(email="exempt@miyano.test", from_date=None):
	emp = test_employee(email)
	frappe.db.set_value(
		"Employee",
		emp,
		{
			"custom_exempt_from_checkin": 1,
			"custom_exempt_from_checkin_from": from_date,
			"relieving_date": None,
			"status": "Active",
		},
	)
	return emp


def make_plain_employee(email):
	emp = test_employee(email)
	frappe.db.set_value(
		"Employee", emp, {"custom_exempt_from_checkin": 0, "relieving_date": None, "status": "Active"}
	)
	return emp


class TestIsExempt(PerTestRollback, FrappeTestCase):
	"""E2 — ai được miễn, ngày nào."""

	def test_flagged_employee_is_exempt(self):
		from hrms.hr.attendance_exempt import is_exempt

		self.assertTrue(is_exempt(make_exempt_employee(), ANCHOR))

	def test_unflagged_employee_is_not_exempt(self):
		from hrms.hr.attendance_exempt import is_exempt

		self.assertFalse(is_exempt(make_plain_employee("plain@miyano.test"), ANCHOR))

	def test_date_before_effective_date_is_not_exempt(self):
		from hrms.hr.attendance_exempt import is_exempt

		emp = make_exempt_employee(from_date=ANCHOR)
		self.assertFalse(is_exempt(emp, add_days(ANCHOR, -1)))
		self.assertTrue(is_exempt(emp, ANCHOR))

	def test_date_before_joining_is_not_exempt(self):
		from hrms.hr.attendance_exempt import is_exempt

		emp = make_exempt_employee()
		doj = frappe.db.get_value("Employee", emp, "date_of_joining")
		self.assertFalse(is_exempt(emp, add_days(getdate(doj), -1)))

	def test_date_after_relieving_is_not_exempt(self):
		from hrms.hr.attendance_exempt import is_exempt

		emp = make_exempt_employee()
		frappe.db.set_value("Employee", emp, "relieving_date", ANCHOR)
		self.assertTrue(is_exempt(emp, ANCHOR))
		self.assertFalse(is_exempt(emp, add_days(ANCHOR, 1)))

	def test_exempt_employees_lists_only_flagged_active(self):
		from hrms.hr.attendance_exempt import exempt_employees

		emp = make_exempt_employee()
		other = make_plain_employee("plain2@miyano.test")
		names = {r.name for r in exempt_employees()}
		self.assertIn(emp, names)
		self.assertNotIn(other, names)

	def test_everything_off_when_fields_not_migrated(self):
		"""Site chưa `migrate` (chưa có cột) → tính năng im lặng, hành vi cũ y nguyên."""
		from unittest.mock import patch

		import hrms.hr.attendance_exempt as ax

		emp = make_exempt_employee()
		with patch.object(ax, "exempt_fields_installed", return_value=False):
			self.assertFalse(ax.is_exempt(emp, ANCHOR))
			self.assertEqual(ax.exempt_employees(), [])


class TestFillFullDay(PerTestRollback, FrappeTestCase):
	"""E3 — sinh một ngày công và các lá chắn."""

	def setUp(self):
		self.emp = make_exempt_employee()

	def attendance_on(self, date):
		return frappe.db.get_value(
			"Attendance",
			{"employee": self.emp, "attendance_date": getdate(date), "docstatus": ["<", 2]},
			["name", "status", "custom_attendance_code", "custom_work_credit", "custom_auto_filled"],
			as_dict=True,
		)

	def test_creates_full_day_present(self):
		from hrms.hr.attendance_exempt import fill_full_day

		self.assertIsNotNone(fill_full_day(self.emp, ANCHOR))
		att = self.attendance_on(ANCHOR)
		self.assertEqual(att.custom_attendance_code, "X")
		self.assertEqual(att.status, "Present")
		self.assertEqual(att.custom_work_credit, 1.0)
		self.assertEqual(att.custom_auto_filled, 1)
		self.assertEqual(frappe.db.get_value("Attendance", att.name, "docstatus"), 1)

	def test_is_idempotent(self):
		from hrms.hr.attendance_exempt import fill_full_day

		fill_full_day(self.emp, ANCHOR)
		self.assertIsNone(fill_full_day(self.emp, ANCHOR))
		self.assertEqual(
			frappe.db.count("Attendance", {"employee": self.emp, "attendance_date": ANCHOR}), 1
		)

	def test_skips_holiday(self):
		from hrms.hr.attendance_exempt import fill_full_day

		hl = frappe.get_doc(
			{
				"doctype": "Holiday List",
				"holiday_list_name": "Miyano Exempt Test 2099",
				"from_date": "2099-01-01",
				"to_date": "2099-12-31",
				"holidays": [{"holiday_date": ANCHOR, "description": "Ngày nghỉ test"}],
			}
		).insert()
		frappe.db.set_value("Employee", self.emp, "holiday_list", hl.name)
		self.assertIsNone(fill_full_day(self.emp, ANCHOR))
		self.assertIsNone(self.attendance_on(ANCHOR))

	def test_does_not_overwrite_existing_record(self):
		from hrms.hr.attendance_exempt import fill_full_day

		# HR cố ý chấm vắng — người thật thắng máy
		att = frappe.get_doc(
			{
				"doctype": "Attendance",
				"employee": self.emp,
				"attendance_date": ANCHOR,
				"custom_attendance_code": "V",
			}
		)
		att.insert()
		att.submit()
		self.assertIsNone(fill_full_day(self.emp, ANCHOR))
		self.assertEqual(self.attendance_on(ANCHOR).custom_attendance_code, "V")

	def test_skips_when_not_exempt(self):
		from hrms.hr.attendance_exempt import fill_full_day

		self.assertIsNone(fill_full_day(make_plain_employee("plain3@miyano.test"), ANCHOR))

	def test_skips_locked_period(self):
		"""Kỳ đã chốt là ĐÓNG BĂNG. Mock `is_period_locked` — luật khoá kỳ đã có test riêng ở
		`hrms/hr/tests/test_period_lock.py`; ở đây chỉ chứng minh `fill_full_day` có hỏi nó."""
		from unittest.mock import patch

		from hrms.hr.attendance_exempt import fill_full_day

		with patch("hrms.hr.period_lock.is_period_locked", return_value=True):
			self.assertIsNone(fill_full_day(self.emp, ANCHOR))
		self.assertIsNone(self.attendance_on(ANCHOR))


def exempt_test_shift(split=False):
	"""Ca dùng chung cho test — tạo một lần, các test sau dùng lại (DML, không phải DDL)."""
	name = "Miyano Exempt Test Shift"
	if not frappe.db.exists("Shift Type", name):
		frappe.get_doc(
			{
				"doctype": "Shift Type",
				"__newname": name,
				"start_time": "08:00:00",
				"end_time": "17:30:00",
				"custom_lunch_start": "12:00:00",
				"custom_lunch_end": "13:30:00",
			}
		).insert()
	frappe.db.set_value("Shift Type", name, "custom_split_half_day", 1 if split else 0)
	return name


def assign_shift(employee, shift, start, end):
	doc = frappe.get_doc(
		{
			"doctype": "Shift Assignment",
			"employee": employee,
			"shift_type": shift,
			"start_date": getdate(start),
			"end_date": getdate(end),
			"status": "Active",
			"company": frappe.db.get_value("Employee", employee, "company"),
		}
	)
	doc.insert()
	doc.submit()
	return doc.name


class TestAbsentBranch(PerTestRollback, FrappeTestCase):
	"""E4 — nhánh chấm vắng THẬT của Shift Type: người có cờ ra X, người thường vẫn V."""

	MONTH_START = getdate("2099-06-01")
	SYNC = "2099-06-06 23:00:00"

	def run_absent_marking(self, employee):
		shift = frappe.get_doc("Shift Type", exempt_test_shift())
		shift.db_set("process_attendance_after", self.MONTH_START)
		shift.db_set("last_sync_of_checkin", self.SYNC)
		assign_shift(employee, shift.name, self.MONTH_START, "2099-06-30")
		shift.mark_absent_for_dates_with_no_attendance(employee)

	def codes_for(self, employee):
		return {
			r.attendance_date: (r.status, r.custom_attendance_code)
			for r in frappe.get_all(
				"Attendance",
				filters={"employee": employee, "attendance_date": [">=", self.MONTH_START]},
				fields=["attendance_date", "status", "custom_attendance_code"],
			)
		}

	def test_exempt_gets_full_day_instead_of_absent(self):
		emp = make_exempt_employee(email="absent_exempt@miyano.test", from_date=self.MONTH_START)
		self.run_absent_marking(emp)
		marked = self.codes_for(emp)
		self.assertTrue(marked, "không ngày nào được chấm — test không chứng minh được gì")
		self.assertTrue(
			all(v == ("Present", "X") for v in marked.values()),
			f"người miễn chấm công phải đủ công mọi ngày, nhận: {sorted(set(marked.values()))}",
		)

	def test_plain_employee_still_marked_absent(self):
		# BẤT BIẾN: người không có cờ vẫn đi đúng đường cũ
		emp = make_plain_employee("absent_plain@miyano.test")
		self.run_absent_marking(emp)
		marked = self.codes_for(emp)
		self.assertTrue(marked)
		self.assertTrue(
			all(v == ("Absent", "V") for v in marked.values()),
			f"người thường phải vẫn bị chấm vắng, nhận: {sorted(set(marked.values()))}",
		)


class TestSweep(PerTestRollback, FrappeTestCase):
	"""E5 — lượt quét không lệ thuộc phân ca (8/2026 trên site chưa có Shift Assignment nào)."""

	def test_sweep_fills_recent_working_days_without_shift_assignment(self):
		from hrms.hr.attendance_exempt import process_exempt_employees

		yesterday = add_days(getdate(), -1)
		emp = make_exempt_employee(email="sweep@miyano.test", from_date=add_days(yesterday, -2))
		self.assertFalse(
			frappe.db.exists("Shift Assignment", {"employee": emp, "docstatus": 1}),
			"test này phải chạy với nhân viên KHÔNG có phân ca",
		)
		process_exempt_employees()
		created = frappe.get_all(
			"Attendance",
			filters={"employee": emp, "attendance_date": [">=", add_days(yesterday, -2)]},
			fields=["attendance_date", "custom_attendance_code"],
		)
		self.assertTrue(created, "lượt quét không sinh ngày công nào")
		self.assertTrue(all(r.custom_attendance_code == "X" for r in created))

	def test_sweep_does_not_touch_today(self):
		from hrms.hr.attendance_exempt import process_exempt_employees

		emp = make_exempt_employee(email="sweep2@miyano.test", from_date=add_days(getdate(), -2))
		process_exempt_employees()
		# ngày hôm nay CHƯA HẾT → chưa kết luận được
		self.assertFalse(frappe.db.exists("Attendance", {"employee": emp, "attendance_date": getdate()}))

	def test_sweep_is_idempotent(self):
		from hrms.hr.attendance_exempt import process_exempt_employees

		emp = make_exempt_employee(email="sweep3@miyano.test", from_date=add_days(getdate(), -3))
		process_exempt_employees()
		before = frappe.db.count("Attendance", {"employee": emp})
		process_exempt_employees()
		self.assertEqual(frappe.db.count("Attendance", {"employee": emp}), before)

	def test_sweep_respects_backfill_window(self):
		from hrms.hr.attendance_exempt import BACKFILL_DAYS, process_exempt_employees

		old = add_days(getdate(), -(BACKFILL_DAYS + 10))
		emp = make_exempt_employee(email="sweep4@miyano.test", from_date=old)
		process_exempt_employees()
		self.assertFalse(
			frappe.db.exists("Attendance", {"employee": emp, "attendance_date": old}),
			"lượt quét tự động không được cày quá cửa sổ BACKFILL_DAYS",
		)

	def test_scheduler_hook_registered_after_auto_attendance(self):
		import hrms.hooks as hooks

		jobs = hooks.scheduler_events["hourly_long"]
		self.assertIn("hrms.hr.attendance_exempt.process_exempt_employees", jobs)
		self.assertGreater(
			jobs.index("hrms.hr.attendance_exempt.process_exempt_employees"),
			jobs.index("hrms.hr.doctype.shift_type.shift_type.process_auto_attendance_for_all_shifts"),
			"lượt quét phải chạy SAU auto-attendance",
		)


class TestNoDowngradeOnCheckin(PerTestRollback, FrappeTestCase):
	"""E6 — giám đốc ghé một tiếng vẫn đủ công; giờ vào/ra vẫn ghi thật cho báo cáo."""

	def mark(self, employee):
		att = frappe.get_doc(
			{
				"doctype": "Attendance",
				"employee": employee,
				"attendance_date": ANCHOR,
				"shift": exempt_test_shift(split=True),
				"in_time": f"{ANCHOR} 10:00:00",
				"out_time": f"{ANCHOR} 11:00:00",
				"status": "Present",
			}
		)
		att.insert()
		return att

	def test_short_attendance_stays_full_day_for_exempt(self):
		att = self.mark(make_exempt_employee(email="short@miyano.test"))
		self.assertEqual(att.custom_attendance_code, "X")
		self.assertEqual(att.status, "Present")
		self.assertGreater(att.working_hours, 0, "giờ có mặt vẫn phải ghi thật cho báo cáo")

	def test_short_attendance_still_downgrades_for_plain_employee(self):
		# BẤT BIẾN: người không có cờ vẫn đi đúng luật cũ (1/2X / V tuỳ giờ)
		att = self.mark(make_plain_employee("short2@miyano.test"))
		self.assertNotEqual(att.custom_attendance_code, "X")


class TestLeaveOverridesGeneratedDay(PerTestRollback, FrappeTestCase):
	"""E7 — đơn nghỉ luôn thắng ngày X tự sinh; nửa ngày phép chỉ trừ 0,5."""

	def setUp(self):
		self.emp = make_exempt_employee(email="leave@miyano.test")

	def apply_leave(self, half_day=False):
		from hrms.hr.doctype.leave_application.test_leave_application import make_allocation_record

		# BẮT BUỘC truyền from_date/to_date: mặc định của helper là 2013-01-01..2019-12-31, không
		# phủ mốc 2099 → đơn nghỉ vỡ vì "không đủ phép" chứ không phải vì code của mình.
		make_allocation_record(
			employee=self.emp,
			leave_type="Nghỉ phép năm",
			from_date="2099-01-01",
			to_date="2099-12-31",
		)
		leave = frappe.get_doc(
			{
				"doctype": "Leave Application",
				"employee": self.emp,
				"leave_type": "Nghỉ phép năm",
				"from_date": ANCHOR,
				"to_date": ANCHOR,
				"half_day": 1 if half_day else 0,
				"half_day_date": ANCHOR if half_day else None,
				# quy ước Miyano "gộp một quỹ phép năm": đơn rút quỹ bắt buộc chọn Loại nghỉ, nghỉ
				# nửa ngày bắt buộc chọn buổi (`leave_single_pool.validate_pool_code`)
				"custom_leave_reason": "Nghỉ phép năm",
				"custom_half_day_period": "Sáng" if half_day else None,
				"status": "Approved",
				"company": frappe.db.get_value("Employee", self.emp, "company"),
			}
		)
		leave.insert()
		leave.submit()
		return leave

	def attendance(self):
		return frappe.db.get_value(
			"Attendance",
			{"employee": self.emp, "attendance_date": ANCHOR, "docstatus": ["<", 2]},
			["status", "leave_type", "half_day_status", "custom_attendance_code"],
			as_dict=True,
		)

	def test_full_day_leave_replaces_generated_day(self):
		from hrms.hr.attendance_exempt import fill_full_day

		fill_full_day(self.emp, ANCHOR)
		self.apply_leave()
		att = self.attendance()
		self.assertEqual(att.status, "On Leave")
		self.assertEqual(att.leave_type, "Nghỉ phép năm")
		self.assertEqual(att.custom_attendance_code, "P")

	def test_half_day_leave_keeps_other_half_present(self):
		from hrms.hr.attendance_exempt import fill_full_day

		fill_full_day(self.emp, ANCHOR)
		self.apply_leave(half_day=True)
		att = self.attendance()
		self.assertEqual(att.status, "Half Day")
		self.assertEqual(att.half_day_status, "Present", "nửa còn lại của người miễn chấm công LÀ công")
		self.assertEqual(att.custom_attendance_code, "1/2P")

	def test_other_half_not_flipped_absent_after_manual_v(self):
		"""Kịch bản duy nhất chạm nhánh `mark_absent_for_half_day_dates`: ngày đang là V (HR chấm
		tay) rồi xin nghỉ nửa ngày → upstream bật `modify_half_day_status` và sau đó ép nửa còn lại
		thành Absent vì "thiếu lượt chấm". Với người miễn chấm công, nửa đó LÀ công."""
		att = frappe.get_doc(
			{
				"doctype": "Attendance",
				"employee": self.emp,
				"attendance_date": ANCHOR,
				"custom_attendance_code": "V",
			}
		)
		att.insert()
		att.submit()
		self.apply_leave(half_day=True)
		self.assertEqual(
			frappe.db.get_value("Attendance", att.name, "modify_half_day_status"),
			1,
			"kịch bản không dựng đúng: upstream chưa bật cờ modify_half_day_status",
		)

		shift = frappe.get_doc("Shift Type", exempt_test_shift())
		assign_shift(self.emp, shift.name, "2099-06-01", "2099-06-30")
		shift.mark_absent_for_half_day_dates(self.emp)

		self.assertEqual(
			frappe.db.get_value("Attendance", att.name, "half_day_status"),
			"Present",
			"nửa còn lại của người miễn chấm công bị ép thành Absent → trừ oan 0,5 công",
		)


class TestBusinessTripOverridesGeneratedDay(PerTestRollback, FrappeTestCase):
	"""E8 — CT phải thắng ngày X tự sinh, nhưng KHÔNG được đè ngày có quẹt thẻ thật."""

	def make_trip(self, employee, date):
		# `destination` là field BẮT BUỘC của Business Trip; gọi thẳng `create_travel_attendance()`
		# để test đúng một hàm, không đi qua Workflow duyệt.
		trip = frappe.get_doc(
			{
				"doctype": "Business Trip",
				"company": frappe.db.get_value("Employee", employee, "company"),
				"destination": "Hà Nội",
				"purpose": "Test công tác",
				"from_date": ANCHOR,
				"to_date": ANCHOR,
				"travelers": [{"employee": employee}],
			}
		)
		trip.insert()
		return trip

	def test_generated_day_becomes_ct(self):
		from hrms.hr.attendance_exempt import fill_full_day

		emp = make_exempt_employee(email="trip@miyano.test")
		fill_full_day(emp, ANCHOR)
		self.make_trip(emp, ANCHOR).create_travel_attendance()
		att = frappe.db.get_value(
			"Attendance",
			{"employee": emp, "attendance_date": ANCHOR, "docstatus": ["<", 2]},
			["custom_attendance_code", "status", "custom_auto_filled"],
			as_dict=True,
		)
		self.assertEqual(att.custom_attendance_code, "CT")
		self.assertEqual(att.status, "Work From Home")
		self.assertEqual(att.custom_auto_filled, 0, "đã thành ngày công tác thật, không còn là ngày tự sinh")
		self.assertEqual(frappe.db.count("Attendance", {"employee": emp, "attendance_date": ANCHOR}), 1)

	def test_real_checkin_day_is_not_overwritten(self):
		emp = make_exempt_employee(email="trip2@miyano.test")
		att = frappe.get_doc(
			{
				"doctype": "Attendance",
				"employee": emp,
				"attendance_date": ANCHOR,
				"in_time": f"{ANCHOR} 08:00:00",
				"out_time": f"{ANCHOR} 17:30:00",
				"custom_attendance_code": "X",
			}
		)
		att.insert()
		att.submit()
		self.make_trip(emp, ANCHOR).create_travel_attendance()
		self.assertEqual(
			frappe.db.get_value("Attendance", att.name, "custom_attendance_code"),
			"X",
			"ngày có giờ vào/ra thật là dữ liệu thật — Công Tác không được đè",
		)
