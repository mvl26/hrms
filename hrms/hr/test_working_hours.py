# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

import frappe
from frappe import _
from frappe.tests.utils import FrappeTestCase
from frappe.utils import getdate

from erpnext.setup.doctype.employee.test_employee import make_employee

from hrms.hr.doctype.attendance.attendance import mark_attendance
from hrms.hr.working_hours import (
	compute_net_hours,
	get_hours_by_department,
	get_hours_by_week,
	get_net_hours_map,
	get_week_buckets,
)


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


class TestGetWeekBuckets(FrappeTestCase):
	def test_march_2026_buckets(self):
		# 1/3/2026 là Chủ nhật -> nằm riêng ở tuần đầu (phần đuôi của tuần ISO trước)
		buckets = get_week_buckets(2026, 3)
		self.assertEqual(buckets[0]["days"], [1])
		self.assertIn(2, buckets[1]["days"])

	def test_all_days_covered_once_in_order(self):
		buckets = get_week_buckets(2026, 3)
		all_days = [d for b in buckets for d in b["days"]]
		self.assertEqual(all_days, list(range(1, 32)))  # tháng 3 có 31 ngày, đủ và đúng thứ tự

	def test_labels_are_sequential(self):
		buckets = get_week_buckets(2026, 3)
		labels = [b["label"] for b in buckets]
		self.assertEqual(labels, [f"{_('Week')} {i}" for i in range(1, len(buckets) + 1)])


class TestGetNetHoursMap(FrappeTestCase):
	def setUp(self):
		self.company = "_Test Company"
		self.employee = make_employee("wh_map_test@example.com", company=self.company)
		frappe.db.delete("Attendance", {"employee": self.employee})

	def test_present_day_net_hours_in_map(self):
		date = getdate("2026-03-02")  # ngày 2
		name = mark_attendance(self.employee, date, "Present")
		frappe.db.set_value(
			"Attendance",
			name,
			{"in_time": "2026-03-02 08:00:00", "out_time": "2026-03-02 17:30:00"},
		)
		filters = frappe._dict(company=self.company, companies=[self.company], month=3, year=2026)
		hours_map = get_net_hours_map(filters)
		self.assertEqual(hours_map[self.employee][""][2], 8.0)  # 9.5 - 1.5

	def test_fallback_working_hours_when_no_in_out(self):
		date = getdate("2026-03-03")  # ngày 3
		name = mark_attendance(self.employee, date, "Present")
		frappe.db.set_value("Attendance", name, "working_hours", 9.0)
		filters = frappe._dict(company=self.company, companies=[self.company], month=3, year=2026)
		hours_map = get_net_hours_map(filters)
		self.assertEqual(hours_map[self.employee][""][3], 7.5)  # 9.0 - 1.5


class TestHoursAggregation(FrappeTestCase):
	def setUp(self):
		self.company = "_Test Company"
		self.employee = make_employee("wh_agg_test@example.com", company=self.company)
		frappe.db.delete("Attendance", {"employee": self.employee})
		name = mark_attendance(self.employee, getdate("2026-03-02"), "Present")
		frappe.db.set_value(
			"Attendance",
			name,
			{"in_time": "2026-03-02 08:00:00", "out_time": "2026-03-02 17:30:00"},
		)
		self.filters = frappe._dict(
			company=self.company, companies=[self.company], month=3, year=2026
		)

	def test_by_week_total_matches(self):
		data = get_hours_by_week(self.filters)
		self.assertEqual(len(data["labels"]), len(data["values"]))
		self.assertEqual(round(sum(data["values"]), 2), 8.0)

	def test_by_department_total_matches(self):
		data = get_hours_by_department(self.filters)
		self.assertEqual(len(data["labels"]), len(data["values"]))
		self.assertEqual(round(sum(data["values"]), 2), 8.0)
