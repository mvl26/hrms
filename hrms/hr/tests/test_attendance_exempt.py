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
