# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

from frappe.tests.utils import FrappeTestCase

from hrms.hr.working_hours import compute_net_hours


class TestComputeNetHours(FrappeTestCase):
	def test_present_full_day_deducts_lunch(self):
		# 08:00 -> 17:30 = 9.5h gross, trừ 1.5h = 8.0h
		net = compute_net_hours("Present", "2026-03-02 08:00:00", "2026-03-02 17:30:00", 9.5)
		self.assertEqual(net, 8.0)

	def test_work_from_home_deducts_lunch(self):
		net = compute_net_hours("Work From Home", "2026-03-02 08:00:00", "2026-03-02 16:00:00", 8.0)
		self.assertEqual(net, 6.5)

	def test_half_day_no_deduction(self):
		# 08:00 -> 12:00 = 4.0h, Half Day không trừ
		net = compute_net_hours("Half Day", "2026-03-02 08:00:00", "2026-03-02 12:00:00", 4.0)
		self.assertEqual(net, 4.0)

	def test_fallback_to_working_hours_when_no_in_out(self):
		# thiếu in/out -> dùng working_hours rồi trừ 1.5h
		net = compute_net_hours("Present", None, None, 9.0)
		self.assertEqual(net, 7.5)

	def test_floor_at_zero(self):
		# gross 1.0h, trừ 1.5h -> sàn 0
		net = compute_net_hours("Present", "2026-03-02 08:00:00", "2026-03-02 09:00:00", 1.0)
		self.assertEqual(net, 0.0)

	def test_absent_and_leave_are_zero(self):
		self.assertEqual(compute_net_hours("Absent", None, None, 0), 0.0)
		self.assertEqual(compute_net_hours("On Leave", None, None, 0), 0.0)
