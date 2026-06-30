# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

import frappe
from frappe import _
from frappe.utils import cint, flt, getdate, time_diff_in_hours

LUNCH_BREAK_HOURS = 1.5
FULL_DAY_STATUSES = ("Present", "Work From Home")


def compute_net_hours(status, in_time, out_time, working_hours):
	"""Giờ làm net của một ngày: gross (out-in hoặc working_hours) trừ nghỉ trưa theo status."""
	if in_time and out_time:
		gross = flt(time_diff_in_hours(out_time, in_time))
	else:
		gross = flt(working_hours)

	if gross <= 0:
		return 0.0

	if status in FULL_DAY_STATUSES:
		return max(round(gross - LUNCH_BREAK_HOURS, 2), 0.0)
	if status == "Half Day":
		return round(gross, 2)
	return 0.0
