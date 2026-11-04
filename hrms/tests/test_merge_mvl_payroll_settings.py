# Copyright (c) 2026, Miyano Việt Nam.
"""Patch gộp `MVL Payroll Settings` vào `Payroll Settings` (2026-11-04).

Patch chép tham số HR đang dùng (giảm trừ, ăn trưa, tỷ lệ BH/KPCĐ, hai biểu bậc) sang tab
"Lương Miyano (VN)" của Payroll Settings rồi xoá doctype cũ. Không `git revert` được nên test dựng
lại đúng trạng thái trước migrate bằng SQL thô (dòng `tabSingles` + dòng bậc có parent cũ) rồi chạy
patch thật — không phụ thuộc doctype cũ còn hay mất trên site.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from hrms.patches.v15_0.merge_mvl_payroll_settings import OLD, SCALAR_FIELDS, TABLES, execute
from hrms.tests.isolation import PerTestRollback

TARGET = "Payroll Settings"

# số cố ý KHÁC mặc định của engine — để biết giá trị đến từ bản cũ chứ không phải từ seed
OLD_VALUES = {
	"personal_deduction": 16_000_000,
	"dependent_deduction": 6_400_000,
	"lunch_rate_per_day": 40_000,
	"probation_coefficient": 0.8,
	"insurance_company_rate": 0.2,
	"insurance_employee_rate": 0.1,
	"union_fee_rate": 0.015,
}
OLD_TAX = [(10_000_000, 5, 0), (0, 35, 14_500_000)]
OLD_GROSSUP = [(9_500_000, 0, 0.95), (0, 14_500_000, 0.65)]


def stage_old_settings(values=OLD_VALUES, tax=OLD_TAX, grossup=OLD_GROSSUP):
	"""Đưa DB về hình dạng trước migrate: tham số nằm dưới doctype cũ, Payroll Settings chưa có gì."""
	frappe.db.delete("Singles", {"doctype": OLD})
	frappe.db.delete("Singles", {"doctype": TARGET, "field": ["in", list(SCALAR_FIELDS)]})
	for child, fieldname in TABLES:
		frappe.db.delete(child, {"parenttype": ["in", [OLD, TARGET]], "parentfield": fieldname})
	for field, value in values.items():
		frappe.db.sql(
			"insert into `tabSingles` (doctype, field, value) values (%s, %s, %s)", (OLD, field, value)
		)
	for (child, fieldname), rows in zip(TABLES, (tax, grossup), strict=True):
		keys = (
			("threshold_upto", "rate", "subtract")
			if fieldname == "tax_brackets"
			else (
				"threshold_upto",
				"subtract",
				"divisor",
			)
		)
		for idx, row in enumerate(rows, start=1):
			doc = frappe.new_doc(child, parent_doc=None, parentfield=fieldname)
			doc.update(dict(zip(keys, row, strict=True)))
			doc.update({"parent": OLD, "parenttype": OLD, "parentfield": fieldname, "idx": idx})
			doc.db_insert()
	frappe.clear_document_cache(TARGET, TARGET)


class TestMergeMVLPayrollSettings(PerTestRollback, FrappeTestCase):
	def setUp(self):
		super().setUp()
		# meta mới của Single nạp trong transaction (Single không có bảng riêng → chỉ DML)
		frappe.reload_doc("payroll", "doctype", "payroll_settings")

	def tearDown(self):
		super().tearDown()
		frappe.clear_cache(doctype=TARGET)

	def test_values_move_to_payroll_settings(self):
		stage_old_settings()
		execute()
		for field, value in OLD_VALUES.items():
			self.assertAlmostEqual(frappe.db.get_single_value(TARGET, field), value, msg=field)

		s = frappe.get_single(TARGET)
		self.assertEqual([(b.threshold_upto, b.rate, b.subtract) for b in s.tax_brackets], OLD_TAX)
		self.assertEqual([(b.threshold_upto, b.subtract, b.divisor) for b in s.grossup_brackets], OLD_GROSSUP)

	def test_old_settings_are_removed(self):
		stage_old_settings()
		execute()
		self.assertFalse(frappe.db.exists("DocType", OLD))
		self.assertFalse(frappe.db.count("Singles", {"doctype": OLD}))
		for child, _f in TABLES:
			self.assertFalse(frappe.db.count(child, {"parenttype": OLD}), child)

	def test_payroll_engine_reads_the_moved_values(self):
		from hrms.vn_payroll.settings import config_from_settings

		stage_old_settings()
		execute()
		cfg = config_from_settings()
		self.assertEqual(cfg.lunch_rate, 40_000)
		self.assertAlmostEqual(cfg.union_fee_rate, 0.015)
		self.assertEqual(cfg.tax_brackets[-1], (float("inf"), 0.35, 14_500_000))

	def test_missing_union_fee_keeps_the_rate_the_engine_was_using(self):
		# Trên miyano KPCĐ của bản cũ CHƯA TỪNG được lưu → engine dùng mặc định 2%. Sang Payroll
		# Settings thì trường đã có trong meta (Float) nên ô trống đọc thành 0.0 = âm thầm không thu
		# KPCĐ. Patch phải ghi rõ đúng tỷ lệ engine đang dùng.
		from hrms.vn_payroll.mvl import default_config
		from hrms.vn_payroll.settings import config_from_settings

		values = {k: v for k, v in OLD_VALUES.items() if k != "union_fee_rate"}
		stage_old_settings(values=values)
		execute()
		expected = default_config().union_fee_rate
		self.assertAlmostEqual(frappe.db.get_single_value(TARGET, "union_fee_rate"), expected)
		self.assertAlmostEqual(config_from_settings().union_fee_rate, expected)

	def test_old_values_replace_seeded_defaults(self):
		# after_migrate từng seed mặc định vào Payroll Settings (vd. chạy ensure trước patch): số HR
		# đang dùng ở bản cũ phải thắng, và bậc không bị nhân đôi
		from hrms.vn_payroll.setup_mvl import ensure_settings

		stage_old_settings()
		ensure_settings()
		execute()
		self.assertEqual(frappe.db.get_single_value(TARGET, "lunch_rate_per_day"), 40_000)
		self.assertEqual(len(frappe.get_single(TARGET).tax_brackets), len(OLD_TAX))

	def test_no_old_settings_is_a_no_op(self):
		stage_old_settings(values={}, tax=[], grossup=[])
		frappe.db.set_single_value(TARGET, "lunch_rate_per_day", 35_000)
		execute()
		self.assertEqual(frappe.db.get_single_value(TARGET, "lunch_rate_per_day"), 35_000)
