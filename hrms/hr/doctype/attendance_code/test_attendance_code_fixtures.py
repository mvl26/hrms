# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# See license.txt
"""Integrity tests for the seeded VN timekeeping master data (Leave Type anchors +
Attendance Codes). These assert the fixtures shipped by the app resolve correctly."""

import frappe
from frappe.tests.utils import FrappeTestCase

# VN Leave Type anchors (Phase 0) — name -> expected flags.
VN_LEAVE_TYPES = {
	"Nghỉ phép năm": {"is_lwp": 0, "is_compensatory": 0},
	"Nghỉ ốm": {"is_lwp": 0, "is_compensatory": 0},
	"Nghỉ chăm con ốm": {"is_lwp": 0, "is_compensatory": 0},
	"Nghỉ thai sản": {"is_lwp": 0, "is_compensatory": 0},
	"Nghỉ bù": {"is_lwp": 0, "is_compensatory": 1},
	"Nghỉ không lương": {"is_lwp": 1, "is_compensatory": 0},
}

# Attendance Codes (Phase 1b) — code -> (category, work_fraction, is_paid, maps_to_status, leave_type)
VN_ATTENDANCE_CODES = {
	"X": ("Công", 1.0, 1, "Present", None),
	"P": ("Phép", 1.0, 1, "On Leave", "Nghỉ phép năm"),
	"Ô": ("Ốm", 1.0, 1, "On Leave", "Nghỉ ốm"),
	"Cô": ("Ốm", 1.0, 1, "On Leave", "Nghỉ chăm con ốm"),
	"TS": ("Thai sản", 1.0, 1, "On Leave", "Nghỉ thai sản"),
	"NB": ("Nghỉ bù", 1.0, 1, "On Leave", "Nghỉ bù"),
	"KL": ("Không lương", 0.0, 0, "On Leave", "Nghỉ không lương"),
}


class TestAttendanceCodeFixtures(FrappeTestCase):
	def test_vn_leave_type_anchors_exist(self):
		for name, flags in VN_LEAVE_TYPES.items():
			self.assertTrue(frappe.db.exists("Leave Type", name), f"Missing Leave Type: {name}")
			row = frappe.db.get_value("Leave Type", name, ["is_lwp", "is_compensatory"], as_dict=True)
			self.assertEqual(int(row.is_lwp), flags["is_lwp"], f"{name}.is_lwp")
			self.assertEqual(int(row.is_compensatory), flags["is_compensatory"], f"{name}.is_compensatory")
