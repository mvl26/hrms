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


class TestEnsureFullDay(PerTestRollback, FrappeTestCase):
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
		from hrms.hr.attendance_exempt import ensure_full_day

		self.assertIsNotNone(ensure_full_day(self.emp, ANCHOR))
		att = self.attendance_on(ANCHOR)
		self.assertEqual(att.custom_attendance_code, "X")
		self.assertEqual(att.status, "Present")
		self.assertEqual(att.custom_work_credit, 1.0)
		self.assertEqual(att.custom_auto_filled, 1)
		self.assertEqual(frappe.db.get_value("Attendance", att.name, "docstatus"), 1)

	def test_is_idempotent(self):
		from hrms.hr.attendance_exempt import ensure_full_day

		ensure_full_day(self.emp, ANCHOR)
		self.assertIsNone(ensure_full_day(self.emp, ANCHOR))
		self.assertEqual(
			frappe.db.count("Attendance", {"employee": self.emp, "attendance_date": ANCHOR}), 1
		)

	def test_skips_holiday(self):
		from hrms.hr.attendance_exempt import ensure_full_day

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
		self.assertIsNone(ensure_full_day(self.emp, ANCHOR))
		self.assertIsNone(self.attendance_on(ANCHOR))

	def test_repairs_a_bare_absent_day(self):
		"""ĐỔI LUẬT 2026-08-18 (theo yêu cầu chủ site): ngày V trơ (không đơn từ gì) là ngày SAI do
		lượt chấm, phải sửa về đủ công. Muốn ghi vắng thật cho người miễn chấm công thì dùng đơn
		nghỉ (P / K) — ngày có `leave_type` được bảo vệ, xem TestRepairsWrongDays."""
		from hrms.hr.attendance_exempt import ensure_full_day

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
		self.assertIsNotNone(ensure_full_day(self.emp, ANCHOR))
		self.assertEqual(self.attendance_on(ANCHOR).custom_attendance_code, "X")

	def test_skips_when_not_exempt(self):
		from hrms.hr.attendance_exempt import ensure_full_day

		self.assertIsNone(ensure_full_day(make_plain_employee("plain3@miyano.test"), ANCHOR))

	def test_skips_locked_period(self):
		"""Kỳ đã chốt là ĐÓNG BĂNG. Mock `is_period_locked` — luật khoá kỳ đã có test riêng ở
		`hrms/hr/tests/test_period_lock.py`; ở đây chỉ chứng minh `ensure_full_day` có hỏi nó."""
		from unittest.mock import patch

		from hrms.hr.attendance_exempt import ensure_full_day

		with patch("hrms.hr.period_lock.is_period_locked", return_value=True):
			self.assertIsNone(ensure_full_day(self.emp, ANCHOR))
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
		from hrms.hr.attendance_exempt import ensure_full_day

		ensure_full_day(self.emp, ANCHOR)
		self.apply_leave()
		att = self.attendance()
		self.assertEqual(att.status, "On Leave")
		self.assertEqual(att.leave_type, "Nghỉ phép năm")
		self.assertEqual(att.custom_attendance_code, "P")

	def test_half_day_leave_keeps_other_half_present(self):
		from hrms.hr.attendance_exempt import ensure_full_day

		ensure_full_day(self.emp, ANCHOR)
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
		from hrms.hr.attendance_exempt import ensure_full_day

		emp = make_exempt_employee(email="trip@miyano.test")
		ensure_full_day(emp, ANCHOR)
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


class TestGenerateForMonth(PerTestRollback, FrappeTestCase):
	"""E9 — chạy bù theo tháng (dùng khi bật cờ giữa chừng hoặc sau khi huỷ chốt kỳ)."""

	def last_month(self):
		from frappe.utils import get_first_day

		return get_first_day(add_days(get_first_day(getdate()), -1))

	def test_generates_past_month_and_returns_count(self):
		from frappe.utils import get_last_day

		from hrms.hr.attendance_exempt import generate_for_month

		start = self.last_month()
		emp = make_exempt_employee(email="backfill@miyano.test", from_date=start)
		count = generate_for_month(start.month, start.year, employee=emp)
		self.assertGreater(count, 0)
		self.assertEqual(
			count,
			frappe.db.count(
				"Attendance",
				{
					"employee": emp,
					"attendance_date": ["between", [start, get_last_day(start)]],
					"custom_auto_filled": 1,
				},
			),
		)

	def test_second_run_generates_nothing(self):
		from hrms.hr.attendance_exempt import generate_for_month

		start = self.last_month()
		emp = make_exempt_employee(email="backfill2@miyano.test", from_date=start)
		generate_for_month(start.month, start.year, employee=emp)
		self.assertEqual(generate_for_month(start.month, start.year, employee=emp), 0)

	def test_does_not_generate_future_days(self):
		from hrms.hr.attendance_exempt import generate_for_month

		today = getdate()
		emp = make_exempt_employee(email="backfill3@miyano.test", from_date=today)
		generate_for_month(today.month, today.year, employee=emp)
		self.assertFalse(
			frappe.db.exists("Attendance", {"employee": emp, "attendance_date": [">=", today]}),
			"không sinh công cho hôm nay và tương lai",
		)


class TestAttendanceRequestWins(PerTestRollback, FrappeTestCase):
	"""E10 — Yêu cầu chấm công đã duyệt thắng ngày X tự sinh (bảng luật §3.7 của spec).

	Nhánh `reapply_attendance_request` trong `ensure_full_day` trước đây không có test nào."""

	def setUp(self):
		self.emp = make_exempt_employee(email="req@miyano.test")

	def approve_request(self, reason="Work From Home"):
		req = frappe.get_doc(
			{
				"doctype": "Attendance Request",
				"employee": self.emp,
				"from_date": ANCHOR,
				"to_date": ANCHOR,
				"reason": reason,
				"company": frappe.db.get_value("Employee", self.emp, "company"),
			}
		)
		req.insert()
		req.submit()
		return req

	def attendance(self):
		return frappe.db.get_value(
			"Attendance",
			{"employee": self.emp, "attendance_date": ANCHOR, "docstatus": ["<", 2]},
			["name", "status", "custom_attendance_code", "attendance_request"],
			as_dict=True,
		)

	def test_request_code_wins_when_day_generated_after(self):
		"""Đơn duyệt TRƯỚC, lượt quét chạy SAU: không được đè mã của đơn, không đẻ bản ghi thứ hai."""
		from hrms.hr.attendance_exempt import ensure_full_day

		req = self.approve_request()
		self.assertIsNone(ensure_full_day(self.emp, ANCHOR), "đã có đơn duyệt thì không sinh thêm")
		att = self.attendance()
		self.assertEqual(att.custom_attendance_code, "W", "mã WFH của đơn bị mất")
		self.assertEqual(att.attendance_request, req.name)
		self.assertEqual(frappe.db.count("Attendance", {"employee": self.emp, "attendance_date": ANCHOR}), 1)

	def test_request_overwrites_generated_day(self):
		"""Ngày đã tự sinh X rồi mới có đơn duyệt: đơn phải ghi đè được."""
		from hrms.hr.attendance_exempt import ensure_full_day

		ensure_full_day(self.emp, ANCHOR)
		self.approve_request(reason="On Duty")
		att = self.attendance()
		self.assertEqual(att.custom_attendance_code, "CT", "đơn on-duty phải ghi đè ngày X tự sinh")
		self.assertEqual(frappe.db.count("Attendance", {"employee": self.emp, "attendance_date": ANCHOR}), 1)


class TestLateCheckinAfterGeneratedDay(PerTestRollback, FrappeTestCase):
	"""E11 — lượt chấm về SAU khi ngày đã tự sinh (spec không nhắc; đây là thứ tự có thật vì
	`last_sync_of_checkin` có thể trễ). Không được ném lỗi và không được đẻ bản ghi trùng —
	`process_auto_attendance` chạy cho TOÀN BỘ nhân viên, vỡ ở đây là chết cả lượt."""

	def test_checkin_arriving_after_autofill_does_not_break(self):
		from hrms.hr.attendance_exempt import ensure_full_day

		emp = make_exempt_employee(email="late@miyano.test")
		shift = frappe.get_doc("Shift Type", exempt_test_shift())
		shift.db_set("enable_auto_attendance", 1)
		shift.db_set("process_attendance_after", "2099-06-01")
		shift.db_set("last_sync_of_checkin", "2099-06-20 23:00:00")
		assign_shift(emp, shift.name, "2099-06-01", "2099-06-30")

		self.assertIsNotNone(ensure_full_day(emp, ANCHOR))

		for t in ("08:05:00", "17:35:00"):
			frappe.get_doc(
				{
					"doctype": "Employee Checkin",
					"employee": emp,
					"time": f"{ANCHOR} {t}",
					"shift": shift.name,
				}
			).insert()

		shift.process_auto_attendance()  # không được ném lỗi

		self.assertEqual(
			frappe.db.count("Attendance", {"employee": emp, "attendance_date": ANCHOR, "docstatus": ["<", 2]}),
			1,
			"lượt chấm về sau đẻ ra bản ghi ngày công thứ hai",
		)
		self.assertEqual(
			frappe.db.get_value(
				"Attendance",
				{"employee": emp, "attendance_date": ANCHOR, "docstatus": ["<", 2]},
				"custom_attendance_code",
			),
			"X",
		)


class TestHolidayIsNotAWorkingDay(PerTestRollback, FrappeTestCase):
	"""E12 — luật miễn chấm công CHỈ áp cho ngày làm việc.

	Ngày nghỉ cả công ty đều nghỉ; ép X ở đó thì chấm 10 phút ngày lễ cũng thành đủ công (và trên
	cấu hình trả lương ngày lễ là cộng dư). Ngày nghỉ phải đi đúng luật chung như mọi người."""

	def setUp(self):
		self.emp = make_exempt_employee(email="holiday@miyano.test")
		hl = frappe.get_doc(
			{
				"doctype": "Holiday List",
				"holiday_list_name": "Miyano Exempt Holiday 2099",
				"from_date": "2099-01-01",
				"to_date": "2099-12-31",
				"holidays": [{"holiday_date": ANCHOR, "description": "Lễ test"}],
			}
		).insert()
		frappe.db.set_value("Employee", self.emp, "holiday_list", hl.name)

	def test_exempt_rule_does_not_apply_on_a_holiday(self):
		from hrms.hr.attendance_exempt import is_exempt, is_exempt_working_day

		self.assertTrue(is_exempt(self.emp, ANCHOR), "cờ vẫn bật")
		self.assertFalse(is_exempt_working_day(self.emp, ANCHOR), "nhưng ngày lễ không phải ngày công")

	def test_short_stint_on_marked_holiday_is_not_a_full_day(self):
		shift = exempt_test_shift(split=True)
		frappe.db.set_value("Shift Type", shift, "mark_auto_attendance_on_holidays", 1)
		att = frappe.get_doc(
			{
				"doctype": "Attendance",
				"employee": self.emp,
				"attendance_date": ANCHOR,
				"shift": shift,
				"in_time": f"{ANCHOR} 09:00:00",
				"out_time": f"{ANCHOR} 09:10:00",
				"status": "Present",
			}
		)
		att.insert()
		self.assertNotEqual(att.custom_attendance_code, "X", "10 phút ngày lễ không được thành đủ công")


class TestRepairsWrongDays(PerTestRollback, FrappeTestCase):
	"""E13 — sinh công cho người miễn chấm công phải SỬA ĐƯỢC ngày cũ sai.

	Auto-attendance chạy trước (hoặc dữ liệu cũ trước khi bật cờ) đã ghi V / 1/2X từ lượt chấm lỗi.
	Bỏ qua ngày "đã có bản ghi" nghĩa là không bao giờ sửa được. Nhưng ngày do NGƯỜI hoặc kênh có
	chủ ý ghi — nghỉ phép, công tác, WFH/từ xa, yêu cầu chấm công — phải giữ nguyên."""

	def setUp(self):
		self.emp = make_exempt_employee(email="repair@miyano.test")

	def existing(self, code, **kwargs):
		att = frappe.get_doc(
			{
				"doctype": "Attendance",
				"employee": self.emp,
				"attendance_date": ANCHOR,
				"custom_attendance_code": code,
				**kwargs,
			}
		)
		att.insert()
		att.submit()
		return att

	def day(self):
		return frappe.db.get_value(
			"Attendance",
			{"employee": self.emp, "attendance_date": ANCHOR, "docstatus": ["<", 2]},
			["name", "status", "custom_attendance_code", "custom_work_credit", "leave_type", "in_time"],
			as_dict=True,
		)

	def test_repairs_absent_day(self):
		from hrms.hr.attendance_exempt import ensure_full_day

		self.existing("V")
		self.assertIsNotNone(ensure_full_day(self.emp, ANCHOR))
		d = self.day()
		self.assertEqual(d.custom_attendance_code, "X")
		self.assertEqual(d.status, "Present")
		self.assertEqual(d.custom_work_credit, 1.0)

	def test_repairs_short_hours_half_day_and_keeps_punches(self):
		from hrms.hr.attendance_exempt import ensure_full_day

		self.existing("1/2X", in_time=f"{ANCHOR} 09:00:00", out_time=f"{ANCHOR} 12:00:00")
		ensure_full_day(self.emp, ANCHOR)
		d = self.day()
		self.assertEqual(d.custom_attendance_code, "X")
		self.assertIsNotNone(d.in_time, "giờ vào/ra thật phải giữ cho báo cáo giờ làm")

	def test_keeps_leave_day(self):
		from hrms.hr.attendance_exempt import ensure_full_day

		self.existing("P")
		self.assertIsNone(ensure_full_day(self.emp, ANCHOR))
		self.assertEqual(self.day().custom_attendance_code, "P")

	def test_keeps_unpaid_leave_day(self):
		from hrms.hr.attendance_exempt import ensure_full_day

		self.existing("K")
		self.assertIsNone(ensure_full_day(self.emp, ANCHOR))
		self.assertEqual(self.day().custom_attendance_code, "K")

	def test_keeps_business_trip_day(self):
		from hrms.hr.attendance_exempt import ensure_full_day

		self.existing("CT")
		self.assertIsNone(ensure_full_day(self.emp, ANCHOR))
		self.assertEqual(self.day().custom_attendance_code, "CT")

	def test_keeps_work_from_home_day(self):
		from hrms.hr.attendance_exempt import ensure_full_day

		self.existing("W")
		self.assertIsNone(ensure_full_day(self.emp, ANCHOR))
		self.assertEqual(self.day().custom_attendance_code, "W")

	def test_repair_is_idempotent(self):
		from hrms.hr.attendance_exempt import ensure_full_day

		self.existing("V")
		ensure_full_day(self.emp, ANCHOR)
		self.assertIsNone(ensure_full_day(self.emp, ANCHOR), "ngày đã đúng thì không sửa nữa")
		self.assertEqual(frappe.db.count("Attendance", {"employee": self.emp, "attendance_date": ANCHOR}), 1)

	def test_does_not_repair_locked_period(self):
		from unittest.mock import patch

		from hrms.hr.attendance_exempt import ensure_full_day

		self.existing("V")
		with patch("hrms.hr.period_lock.is_period_locked", return_value=True):
			self.assertIsNone(ensure_full_day(self.emp, ANCHOR))
		self.assertEqual(self.day().custom_attendance_code, "V")

	def test_does_not_repair_plain_employee(self):
		from hrms.hr.attendance_exempt import ensure_full_day

		plain = make_plain_employee("repair_plain@miyano.test")
		att = frappe.get_doc(
			{"doctype": "Attendance", "employee": plain, "attendance_date": ANCHOR, "custom_attendance_code": "V"}
		)
		att.insert()
		att.submit()
		self.assertIsNone(ensure_full_day(plain, ANCHOR))
		self.assertEqual(frappe.db.get_value("Attendance", att.name, "custom_attendance_code"), "V")

	def test_generate_for_month_repairs_wrong_days(self):
		"""Đúng tình huống anh nêu: auto chạy trước, sinh công tháng phải sửa được."""
		from frappe.utils import get_first_day

		from hrms.hr.attendance_exempt import generate_for_month

		start = get_first_day(add_days(get_first_day(getdate()), -1))
		emp = make_exempt_employee(email="repair2@miyano.test", from_date=start)
		att = frappe.get_doc(
			{"doctype": "Attendance", "employee": emp, "attendance_date": start, "custom_attendance_code": "V"}
		)
		att.insert()
		att.submit()
		generate_for_month(start.month, start.year, employee=emp)
		self.assertEqual(frappe.db.get_value("Attendance", att.name, "custom_attendance_code"), "X")


class TestAutoAttendanceRepairsExemptDays(PerTestRollback, FrappeTestCase):
	"""E14 — chính hàm auto-attendance phải hỏi "người này có miễn chấm công không" và sửa ngày sai."""

	def test_process_auto_attendance_fixes_absent_days_of_exempt_employee(self):
		emp = make_exempt_employee(email="autofix@miyano.test", from_date="2099-06-01")
		shift = frappe.get_doc("Shift Type", exempt_test_shift())
		shift.db_set("enable_auto_attendance", 1)
		shift.db_set("process_attendance_after", "2099-06-01")
		shift.db_set("last_sync_of_checkin", "2099-06-10 23:00:00")
		assign_shift(emp, shift.name, "2099-06-01", "2099-06-30")

		# ngày công SAI có sẵn (do lượt chấm lỗi / do chạy trước khi bật cờ)
		att = frappe.get_doc(
			{
				"doctype": "Attendance",
				"employee": emp,
				"attendance_date": "2099-06-02",
				"custom_attendance_code": "V",
				"shift": shift.name,
			}
		)
		att.insert()
		att.submit()

		shift.process_auto_attendance()

		self.assertEqual(
			frappe.db.get_value("Attendance", att.name, "custom_attendance_code"),
			"X",
			"auto-attendance phải sửa ngày vắng sai của người miễn chấm công",
		)


class TestLateCheckinsGetAttached(PerTestRollback, FrappeTestCase):
	"""E15 — lượt chấm về SAU khi ngày đã tự sinh phải được GẮN vào ngày đó.

	`mark_attendance_and_link_log` thấy ngày đã có bản ghi thì bỏ qua, nên giờ vào/ra không bao giờ
	được ghi và báo cáo giờ làm hiện 0 cho ngày người ta thật sự có mặt. Mã công vẫn là X (đủ công),
	nhưng dữ liệu giờ phải thật."""

	def test_checkins_are_attached_to_generated_day(self):
		from hrms.hr.attendance_exempt import ensure_full_day

		emp = make_exempt_employee(email="attach@miyano.test")
		frappe.db.set_value("Employee", emp, "default_shift", exempt_test_shift(split=True))
		name = ensure_full_day(emp, ANCHOR)
		self.assertIsNone(frappe.db.get_value("Attendance", name, "in_time"))

		logs = [
			frappe.get_doc(
				{"doctype": "Employee Checkin", "employee": emp, "time": f"{ANCHOR} {t}", "log_type": lt}
			).insert()
			for t, lt in (("10:05:00", "IN"), ("11:40:00", "OUT"))
		]

		ensure_full_day(emp, ANCHOR)

		att = frappe.db.get_value(
			"Attendance", name, ["custom_attendance_code", "in_time", "out_time", "working_hours"], as_dict=True
		)
		self.assertEqual(att.custom_attendance_code, "X", "vẫn đủ công")
		self.assertIsNotNone(att.in_time, "giờ vào phải được ghi")
		self.assertIsNotNone(att.out_time)
		self.assertGreater(att.working_hours, 0)
		for log in logs:
			self.assertEqual(
				frappe.db.get_value("Employee Checkin", log.name, "attendance"),
				name,
				"lượt chấm phải được gắn vào ngày công, nếu không nó bị xử lý lại mãi",
			)
