# Copyright (c) 2026, Miyano Việt Nam.
"""Patch di trú: gỡ dòng nghỉ cuối tuần khỏi Holiday List.

Patch này KHÔNG `git revert` được, nên nó phải tự chặn và tự đối soát. Bộ test chứng minh cả hai:
chưa khai lịch tuần thì abort, và số ngày công của mọi phiếu lương phải giống hệt trước/sau.

Chạy qua harness rollback — mọi thay đổi đều được rollback.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from hrms.patches.v15_0.remove_weekly_off_from_holiday_list import (
	execute,
	guard_work_schedule_is_configured,
	live_holiday_lists,
	payroll_numbers,
	strip_html_from_descriptions,
)
from hrms.tests.isolation import PerTestRollback
from hrms.tests.vn_test_utils import default_company

MON_TO_FRI = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]


class TestHolidaySeparationMigration(PerTestRollback, FrappeTestCase):
	def setUp(self):
		self.company = default_company()

	def set_company_weekdays(self, days):
		frappe.db.delete(
			"Assignment Rule Day",
			{
				"parent": "Work Calendar Settings",
				"parenttype": "Work Calendar Settings",
				"parentfield": "default_working_days",
			},
		)
		for idx, day in enumerate(days, start=1):
			frappe.get_doc(
				{
					"doctype": "Assignment Rule Day",
					"parent": "Work Calendar Settings",
					"parenttype": "Work Calendar Settings",
					"parentfield": "default_working_days",
					"day": day,
					"idx": idx,
				}
			).insert(ignore_permissions=True)

	def test_guard_blocks_when_nothing_declares_a_weekly_schedule(self):
		"""CHẶN TRƯỚC: gỡ dòng cuối tuần khi chưa khai lịch tuần là phá mẫu số cả công ty."""
		self.set_company_weekdays([])
		# Table field không có cột trên bảng cha — xoá dòng con mới là cách gỡ lịch tuần của ca.
		shifts = frappe.get_all("Shift Type", filters={"enable_auto_attendance": 1}, pluck="name")
		frappe.db.delete(
			"Assignment Rule Day",
			{"parent": ("in", shifts), "parentfield": "custom_working_days"},
		)
		frappe.clear_cache()
		if not shifts:
			self.skipTest("site không có ca nào bật chấm công tự động")
		with self.assertRaises(frappe.ValidationError):
			guard_work_schedule_is_configured(live_holiday_lists())

	def test_guard_passes_with_a_company_default(self):
		self.set_company_weekdays(MON_TO_FRI)
		guard_work_schedule_is_configured(live_holiday_lists())  # không throw

	def test_the_test_holiday_list_is_left_alone(self):
		"""Danh sách rác của test không nằm trên đường chạy thật — đụng vào chỉ làm nhiễu."""
		self.assertNotIn("Salary Slip Test Holiday List", live_holiday_lists())

	def test_payroll_numbers_are_identical_after_the_migration(self):
		"""Đối soát TOÀN BỘ phiếu lương đang có, trước và sau khi gỡ."""
		self.set_company_weekdays(MON_TO_FRI)
		slips = frappe.get_all("Salary Slip", pluck="name")
		if not slips:
			self.skipTest("site chưa có phiếu lương nào để đối soát")
		before = {name: payroll_numbers(name) for name in slips}
		execute()
		for name in slips:
			self.assertEqual(payroll_numbers(name), before[name], f"phiếu {name} lệch sau di trú")

	def test_weekly_off_rows_are_gone_and_public_holidays_stay(self):
		self.set_company_weekdays(MON_TO_FRI)
		lists = live_holiday_lists()
		if not lists:
			self.skipTest("site chưa có Holiday List nào đang dùng")
		holidays_before = frappe.db.count("Holiday", {"parent": ("in", lists), "weekly_off": 0})
		execute()
		self.assertEqual(frappe.db.count("Holiday", {"parent": ("in", lists), "weekly_off": 1}), 0)
		self.assertEqual(
			frappe.db.count("Holiday", {"parent": ("in", lists), "weekly_off": 0}), holidays_before
		)

	def test_employee_holiday_list_is_unpinned(self):
		"""Mỗi năm một list -> chỉ nên còn MỘT chỗ phải trỏ lại (Company default)."""
		self.set_company_weekdays(MON_TO_FRI)
		execute()
		self.assertEqual(frappe.db.count("Employee", {"holiday_list": ["is", "set"]}), 0)

	def test_is_idempotent(self):
		self.set_company_weekdays(MON_TO_FRI)
		execute()
		lists = live_holiday_lists()
		count = frappe.db.count("Holiday", {"parent": ("in", lists)}) if lists else 0
		execute()
		after = frappe.db.count("Holiday", {"parent": ("in", lists)}) if lists else 0
		self.assertEqual(after, count)

	def test_html_is_stripped_from_descriptions(self):
		"""Dòng lễ nhập tay dính nguyên HTML ql-editor, hiện thô trên báo cáo/bản in/PWA."""
		name = "_Test HTML Holiday List"
		if frappe.db.exists("Holiday List", name):
			frappe.delete_doc("Holiday List", name, force=True, ignore_permissions=True)
		doc = frappe.get_doc(
			{
				"doctype": "Holiday List",
				"holiday_list_name": name,
				"from_date": "2026-01-01",
				"to_date": "2026-12-31",
				"holidays": [
					{
						"holiday_date": "2026-07-17",
						"description": '<div class="ql-editor read-mode"><p>Nghỉ lễ công ty</p></div>',
						"weekly_off": 0,
					}
				],
			}
		).insert(ignore_permissions=True)
		strip_html_from_descriptions([doc.name])
		row = frappe.get_all("Holiday", filters={"parent": doc.name}, pluck="description")[0]
		self.assertEqual(row, "Nghỉ lễ công ty")
