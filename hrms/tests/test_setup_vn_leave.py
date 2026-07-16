# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# See license.txt
"""Tests for the VN annual-leave entitlement layer (spec/leave-entitlement-vn.md).
Runs via the rollback harness — writes are rolled back, never committed."""

import json
import os

import frappe
from frappe.tests.utils import FrappeTestCase

ANNUAL_LEAVE = "Nghỉ phép năm"
FIXTURE_PATH = os.path.join(os.path.dirname(__file__), "..", "fixtures", "leave_type.json")


def load_fixture_types():
	with open(FIXTURE_PATH) as f:
		return {row["name"]: row for row in json.load(f)}


class TestAnnualLeaveEarnedFixture(FrappeTestCase):
	"""T1 — 'Nghỉ phép năm' becomes a monthly earned leave; the other 7 types stay untouched."""

	def test_fixture_json_flags(self):
		types = load_fixture_types()
		annual = types[ANNUAL_LEAVE]
		self.assertEqual(annual["is_earned_leave"], 1)
		self.assertEqual(annual["earned_leave_frequency"], "Monthly")
		self.assertEqual(annual["rounding"], "0.5")
		self.assertEqual(annual["allocate_on_day"], "Last Day")
		# payroll-relevant flags stay untouched
		self.assertEqual(annual["is_lwp"], 0)
		self.assertEqual(annual["is_carry_forward"], 0)
		# every other type keeps is_earned_leave = 0
		for name, row in types.items():
			if name != ANNUAL_LEAVE:
				self.assertEqual(row["is_earned_leave"], 0, f"{name} must not become earned leave")

	def test_fixture_matches_leave_type_meta(self):
		# the fixture keys must be real Leave Type fields so `bench migrate` can apply them
		# (applying to the live site is the deploy step — sign-off gated, run manually)
		meta = frappe.get_meta("Leave Type")
		for key in ("is_earned_leave", "earned_leave_frequency", "rounding", "allocate_on_day"):
			self.assertTrue(meta.has_field(key), f"Leave Type has no field {key}")


class TestEntitlementAndLeavePeriod(FrappeTestCase):
	"""T2 — entitlement tiers (Điều 113/114) + idempotent Leave Period helper."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		import erpnext

		cls.company = erpnext.get_default_company() or frappe.get_all("Company", limit=1)[0].name

	def _emp(self, doj):
		from erpnext.setup.doctype.employee.test_employee import make_employee

		return make_employee(
			f"vn_leave_{doj}@example.com", company=self.company, date_of_joining=doj
		)

	def test_entitlement_tiers(self):
		from hrms.setup_vn_leave import entitlement_for

		on_date = "2026-01-01"
		# < 5 năm thâm niên -> 12 ngày
		self.assertEqual(entitlement_for(self._emp("2023-03-15"), on_date), 12)
		# đủ 5 năm -> 13
		self.assertEqual(entitlement_for(self._emp("2021-01-01"), on_date), 13)
		# 5 năm chưa đủ (thiếu 1 ngày) -> 12
		self.assertEqual(entitlement_for(self._emp("2021-01-02"), on_date), 12)
		# đủ 10 năm -> 14
		self.assertEqual(entitlement_for(self._emp("2015-12-31"), on_date), 14)

	def test_create_leave_period_idempotent(self):
		from hrms.setup_vn_leave import create_leave_period

		name1 = create_leave_period(2027, self.company)
		period = frappe.get_doc("Leave Period", name1)
		self.assertEqual(str(period.from_date), "2027-01-01")
		self.assertEqual(str(period.to_date), "2027-12-31")
		self.assertEqual(period.is_active, 1)
		self.assertEqual(period.company, self.company)
		# chạy lại -> cùng bản ghi, không nhân đôi
		name2 = create_leave_period(2027, self.company)
		self.assertEqual(name1, name2)
		self.assertEqual(
			len(frappe.get_all("Leave Period", {"company": self.company, "from_date": "2027-01-01"})), 1
		)


def enable_earned_leave_flags():
	"""Apply the fixture's earned-leave flags inside the current (rolled-back) transaction,
	so tests exercise the post-migrate behaviour without touching the live site."""
	frappe.db.set_value(
		"Leave Type",
		ANNUAL_LEAVE,
		{
			"is_earned_leave": 1,
			"earned_leave_frequency": "Monthly",
			"rounding": "0.5",
			"allocate_on_day": "Last Day",
		},
		update_modified=False,
	)
	frappe.clear_document_cache("Leave Type", ANNUAL_LEAVE)
