# Copyright (c) 2026, Miyano Việt Nam.
import frappe
from frappe.tests.utils import FrappeTestCase

from hrms.tests.isolation import PerTestRollback
from hrms.vn_payroll.settings import config_from_settings
from hrms.vn_payroll.setup_mvl import ensure_mvl_defaults


class TestMVLSettings(PerTestRollback, FrappeTestCase):
	def setUp(self):
		super().setUp()
		# tham số MVL nằm ở tab "Lương Miyano (VN)" của Payroll Settings (gộp 2026-11-04): nạp meta
		# trong transaction của test (Single không có bảng riêng → chỉ DML)
		frappe.reload_doc("payroll", "doctype", "payroll_settings")

	def tearDown(self):
		super().tearDown()
		frappe.clear_cache(doctype="Payroll Settings")

	def test_mvl_parameters_live_in_payroll_settings(self):
		# MỘT trang cài đặt lương: không còn doctype riêng cho tham số MVL
		meta = frappe.get_meta("Payroll Settings")
		for field in (
			"personal_deduction",
			"dependent_deduction",
			"lunch_rate_per_day",
			"probation_coefficient",
			"insurance_company_rate",
			"insurance_employee_rate",
			"union_fee_rate",
			"tax_brackets",
			"grossup_brackets",
		):
			self.assertTrue(meta.has_field(field), field)

	def test_hr_manager_can_edit_payroll_settings(self):
		# bản MVL cũ cho HR Manager sửa tham số; gộp vào không được tước quyền đó
		roles = {p.role for p in frappe.get_meta("Payroll Settings").permissions if p.write}
		self.assertIn("HR Manager", roles)

	def test_config_from_settings_matches_defaults(self):
		ensure_mvl_defaults()
		cfg = config_from_settings()
		self.assertEqual(cfg.personal_deduction, 15_500_000)
		self.assertEqual(cfg.dependent_deduction, 6_200_000)
		self.assertEqual(cfg.lunch_rate, 35_000)
		self.assertAlmostEqual(cfg.ins_company, 0.215)
		self.assertAlmostEqual(cfg.ins_employee, 0.105)
		self.assertEqual(len(cfg.tax_brackets), 5)
		self.assertEqual(len(cfg.grossup_brackets), 5)
		self.assertEqual(cfg.tax_brackets[-1][0], float("inf"))  # bậc cuối = vô cực
		self.assertEqual(cfg.grossup_brackets[-1][0], float("inf"))

	def test_config_drives_the_same_engine_numbers(self):
		# đọc settings → chạy engine → khớp đúng oracle Tạ Trường Xuân của doc
		from hrms.vn_payroll.mvl import MVLInput, compute_mvl

		ensure_mvl_defaults()
		cfg = config_from_settings()
		r = compute_mvl(MVLInput("Chính thức", 25_000_000, 25_000_000, 1, True, 21, 22, 22), cfg)
		self.assertEqual(r.Q, 173_684)
		self.assertEqual(r.T, 25_735_000)


class TestUnionFeeRate(PerTestRollback, FrappeTestCase):
	def setUp(self):
		super().setUp()
		frappe.reload_doc("payroll", "doctype", "payroll_settings")

	def tearDown(self):
		super().tearDown()
		frappe.clear_cache(doctype="Payroll Settings")

	def test_union_fee_rate_read_from_settings(self):
		ensure_mvl_defaults()
		frappe.db.set_single_value("Payroll Settings", "union_fee_rate", 0.02)
		self.assertAlmostEqual(config_from_settings().union_fee_rate, 0.02)

	def test_seed_when_missing_keeps_hr_zero(self):
		frappe.db.delete("Singles", {"doctype": "Payroll Settings", "field": "union_fee_rate"})
		ensure_mvl_defaults()
		self.assertAlmostEqual(frappe.db.get_single_value("Payroll Settings", "union_fee_rate"), 0.02)
		# HR cố ý đặt 0 (không thu KPCĐ) → migrate sau không được ghi đè
		frappe.db.set_single_value("Payroll Settings", "union_fee_rate", 0)
		ensure_mvl_defaults()
		self.assertEqual(frappe.db.get_single_value("Payroll Settings", "union_fee_rate"), 0)
		self.assertEqual(config_from_settings().union_fee_rate, 0)

	def test_rates_must_be_fractions(self):
		# nhãn ghi "(%)" nhưng giá trị là tỷ lệ (0,02): HR gõ 2 sẽ thành KPCĐ = 200% lương đóng BHXH
		s = frappe.get_single("Payroll Settings")
		for field in ("union_fee_rate", "insurance_company_rate", "insurance_employee_rate"):
			s.reload()
			s.set(field, 2)
			with self.assertRaises(frappe.ValidationError, msg=field):
				s.save()
