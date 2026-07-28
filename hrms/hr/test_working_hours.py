# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

import json

import frappe
from frappe import _
from frappe.tests.utils import FrappeTestCase
from frappe.utils import getdate

from erpnext.setup.doctype.employee.test_employee import make_employee

from hrms.hr.doctype.attendance.attendance import mark_attendance
from hrms.hr.working_hours import (
	compute_net_hours,
	get_active_employee_count,
	get_avg_working_hours_card,
	get_effective_days_in_month,
	get_hours_by_department,
	get_hours_by_week,
	get_net_hours_map,
	get_standard_hours,
	get_total_working_hours_card,
	get_under_target_count_card,
	get_week_buckets,
	prepare_filters,
)
from hrms.tests.test_utils import create_company


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

	def test_split_shift_uses_stored_net(self):
		# split shift already stored net working_hours (lunch excluded) -> use as-is, no further -1.5
		net = compute_net_hours("Present", "2026-03-02 08:00:00", "2026-03-02 17:30:00", 8.0, is_split=True)
		self.assertEqual(net, 8.0)

	def test_split_shift_half_day_uses_stored_net(self):
		net = compute_net_hours("Half Day", "2026-03-02 08:00:00", "2026-03-02 12:00:00", 4.0, is_split=True)
		self.assertEqual(net, 4.0)


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

	def test_empty_companies_returns_empty_without_sql_error(self):
		# không có company -> không dựng `company IN ()` -> trả rỗng, không lỗi SQL
		filters = frappe._dict(companies=[], month=3, year=2026)
		self.assertEqual(get_net_hours_map(filters), {})


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
		self.filters = frappe._dict(company=self.company, companies=[self.company], month=3, year=2026)

	def test_by_week_total_matches(self):
		data = get_hours_by_week(self.filters)
		self.assertEqual(len(data["labels"]), len(data["values"]))
		self.assertEqual(round(sum(data["values"]), 2), 8.0)

	def test_by_department_total_matches(self):
		data = get_hours_by_department(self.filters)
		self.assertEqual(len(data["labels"]), len(data["values"]))
		self.assertEqual(round(sum(data["values"]), 2), 8.0)


class TestStandardHours(FrappeTestCase):
	def test_standard_hours_excludes_holidays(self):
		# tháng 31 ngày, 5 ngày nghỉ -> 26 ngày công x 8h = 208
		self.assertEqual(get_standard_hours(31, 5), 208.0)

	def test_standard_hours_no_holidays(self):
		self.assertEqual(get_standard_hours(30, 0), 240.0)

	def test_standard_hours_floor_non_negative(self):
		self.assertEqual(get_standard_hours(5, 10), 0.0)


class TestEffectiveDays(FrappeTestCase):
	def test_past_month_uses_full_month(self):
		# tháng 1/2020 đã qua -> đủ 31 ngày
		self.assertEqual(get_effective_days_in_month(2020, 1), 31)

	def test_current_month_clamped_to_today(self):
		today = getdate()
		eff = get_effective_days_in_month(today.year, today.month)
		self.assertEqual(eff, today.day)


class TestWorkingHoursCards(FrappeTestCase):
	def setUp(self):
		self.company = "_Test Company"
		self.employee = make_employee("wh_card_test@example.com", company=self.company)
		frappe.db.delete("Attendance", {"employee": self.employee})
		name = mark_attendance(self.employee, getdate("2026-03-02"), "Present")
		frappe.db.set_value(
			"Attendance",
			name,
			{"in_time": "2026-03-02 08:00:00", "out_time": "2026-03-02 17:30:00"},
		)  # net 8.0
		self.filters = json.dumps({"company": self.company, "month": 3, "year": 2026})

	def _count_filters(self):
		return frappe._dict(company=self.company, month=3, year=2026)

	def test_total_card(self):
		# chỉ nhân sự có chấm công đóng góp -> đúng 8.0 bất kể mẫu số
		res = get_total_working_hours_card(self.filters)
		self.assertEqual(res["fieldtype"], "Float")
		self.assertEqual(res["value"], 8.0)

	def test_avg_card(self):
		# TB = tổng giờ (8.0) / số nhân sự Active
		headcount = get_active_employee_count(self._count_filters())
		res = get_avg_working_hours_card(self.filters)
		self.assertEqual(res["value"], round(8.0 / headcount, 2))

	def test_under_target_card(self):
		# tháng test: mọi nhân sự Active đều dưới định mức (max 8h << định mức tháng)
		headcount = get_active_employee_count(self._count_filters())
		res = get_under_target_count_card(self.filters)
		self.assertEqual(res["value"], headcount)

	def test_cards_count_all_active_employees(self):
		# thêm nhân sự Active KHÔNG chấm công -> tăng mẫu số, và bị tính là thiếu giờ
		before = get_active_employee_count(self._count_filters())
		make_employee("wh_card_test2@example.com", company=self.company)
		after = get_active_employee_count(self._count_filters())
		self.assertEqual(after, before + 1)
		self.assertEqual(get_under_target_count_card(self.filters)["value"], after)
		self.assertEqual(get_avg_working_hours_card(self.filters)["value"], round(8.0 / after, 2))


class TestPrepareFilters(FrappeTestCase):
	def test_includes_company_descendants(self):
		parent = create_company("_WH Parent Co", is_group=1)
		child = create_company("_WH Child Co", parent_company=parent.name)
		f = prepare_filters({"company": parent.name, "month": 3, "year": 2026})
		self.assertIn(parent.name, f.companies)
		self.assertIn(child.name, f.companies)
