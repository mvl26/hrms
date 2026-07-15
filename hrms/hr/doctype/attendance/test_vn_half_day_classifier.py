# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# See license.txt
"""VN auto morning/afternoon classifier + its Shift Type config fields."""
import frappe
from frappe.tests.utils import FrappeTestCase

SHIFT_FIELDS = (
	"custom_split_half_day",
	"custom_lunch_start",
	"custom_lunch_end",
	"custom_half_day_min_fraction",
	"custom_half_day_grace_minutes",
)


class TestVNHalfDayClassifier(FrappeTestCase):
	def test_shift_type_config_fields_exist(self):
		for fn in SHIFT_FIELDS:
			self.assertTrue(
				frappe.db.exists("Custom Field", f"Shift Type-{fn}"), f"missing Custom Field Shift Type-{fn}"
			)
