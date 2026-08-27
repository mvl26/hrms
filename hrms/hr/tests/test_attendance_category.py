# Copyright (c) 2026, Miyano Việt Nam.
"""Tập NHÓM (category) của mã công phải khớp ở MỌI nơi tiêu thụ.

Category quyết định ngày đó rơi vào cột nào của bảng công và có vào "Tổng công" hay không. Trước
đây tập giá trị hợp lệ bị chép cứng ở năm chỗ, không chỗ nào biết chỗ nào — gõ sai một ký tự là
ngày đó lặng lẽ rơi khỏi mọi cột tổng. Test này khiến "thêm một nhóm" thành việc không thể làm
nửa vời.

Chạy qua harness rollback (KHÔNG bench run-tests trên miyano).
"""

import json

import frappe
from frappe.tests.utils import FrappeTestCase

from hrms.hr.attendance_category import CATEGORIES, CATEGORY_WITHOUT_SHEET_COLUMN, select_options
from hrms.tests.isolation import PerTestRollback


class TestAttendanceCategory(PerTestRollback, FrappeTestCase):
	def test_doctype_select_options_match_the_canon(self):
		"""Tuỳ chọn của field `category` trong JSON == CATEGORIES, đúng thứ tự."""
		path = frappe.get_app_path("hrms", "hr", "doctype", "attendance_code", "attendance_code.json")
		with open(path) as f:
			schema = json.load(f)
		field = next(f for f in schema["fields"] if f["fieldname"] == "category")
		self.assertEqual(field["fieldtype"], "Select")
		self.assertEqual(field.get("reqd"), 1, "thiếu nhóm thì mã lặng lẽ được tính là nghỉ có lương")
		self.assertEqual(field["options"], select_options())

	def test_every_category_has_a_colour_state(self):
		"""Thiếu trong CATEGORY_STATE thì ô của mã đó không được tô màu."""
		from hrms.hr.report.monthly_attendance_report.monthly_attendance_report import CATEGORY_STATE

		missing = [c for c in CATEGORIES if c not in CATEGORY_STATE]
		self.assertEqual(missing, [], f"nhóm chưa có màu: {missing}")

	def test_every_category_has_a_sheet_column(self):
		"""Thiếu cột trên Bảng Công Tháng thì số ngày của nhóm đó rơi khỏi bản in đã chốt."""
		from hrms.hr.doctype.monthly_attendance_sheet.monthly_attendance_sheet import CATEGORY_FIELD

		missing = [
			c for c in CATEGORIES if c not in CATEGORY_FIELD and c not in CATEGORY_WITHOUT_SHEET_COLUMN
		]
		self.assertEqual(missing, [], f"nhóm chưa có cột: {missing}")

	def test_report_constants_only_name_known_categories(self):
		"""REPORT_CATEGORIES / NON_PAID_LEAVE_CATEGORIES không được nhắc tới nhóm không tồn tại."""
		from hrms.hr.report.monthly_attendance_report.monthly_attendance_report import (
			BUCKET_MARRIAGE,
			NON_PAID_LEAVE_CATEGORIES,
			REPORT_CATEGORIES,
		)

		known = set(CATEGORIES) | {BUCKET_MARRIAGE}
		for cat, _label in REPORT_CATEGORIES:
			self.assertIn(cat, known, f"cột báo cáo trỏ tới nhóm lạ: {cat}")
		for cat in NON_PAID_LEAVE_CATEGORIES:
			self.assertIn(cat, CATEGORIES, f"luật Tổng công trỏ tới nhóm lạ: {cat}")

	def test_legend_order_is_the_canon(self):
		"""Chú thích sắp theo đúng tập chuẩn, không giữ bản chép riêng."""
		from hrms.hr.attendance_legend import CATEGORY_ORDER

		self.assertEqual(tuple(CATEGORY_ORDER), CATEGORIES)

	def test_every_code_on_this_site_uses_a_known_category(self):
		"""Dữ liệu thật phải nằm trong tập chuẩn — nếu không, đổi sang Select sẽ chặn lần lưu sau."""
		rows = frappe.get_all("Attendance Code", fields=["name", "category"])
		bad = [r.name for r in rows if r.category not in CATEGORIES]
		self.assertEqual(bad, [], f"mã có nhóm ngoài tập chuẩn: {bad}")
