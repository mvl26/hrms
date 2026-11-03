# Copyright (c) 2026, Miyano Việt Nam.
import frappe
from frappe.tests.utils import FrappeTestCase

from hrms.tests.isolation import PerTestRollback
from hrms.vn_payroll.settings import config_from_settings
from hrms.vn_payroll.setup_mvl import ensure_mvl_defaults


class TestMVLSettings(PerTestRollback, FrappeTestCase):
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
		# field mới của Single: nạp meta trong transaction của test (Single không có bảng riêng → DML)
		frappe.reload_doc("hr", "doctype", "mvl_payroll_settings")

	def test_union_fee_rate_read_from_settings(self):
		ensure_mvl_defaults()
		frappe.db.set_single_value("MVL Payroll Settings", "union_fee_rate", 0.02)
		self.assertAlmostEqual(config_from_settings().union_fee_rate, 0.02)

	def test_seed_when_missing_keeps_hr_zero(self):
		frappe.db.delete("Singles", {"doctype": "MVL Payroll Settings", "field": "union_fee_rate"})
		ensure_mvl_defaults()
		self.assertAlmostEqual(frappe.db.get_single_value("MVL Payroll Settings", "union_fee_rate"), 0.02)
		# HR cố ý đặt 0 (không thu KPCĐ) → migrate sau không được ghi đè
		frappe.db.set_single_value("MVL Payroll Settings", "union_fee_rate", 0)
		ensure_mvl_defaults()
		self.assertEqual(frappe.db.get_single_value("MVL Payroll Settings", "union_fee_rate"), 0)
		self.assertEqual(config_from_settings().union_fee_rate, 0)

	def test_rates_must_be_fractions(self):
		# nhãn ghi "(%)" nhưng giá trị là tỷ lệ (0,02): HR gõ 2 sẽ thành KPCĐ = 200% lương đóng BHXH
		s = frappe.get_single("MVL Payroll Settings")
		for field in ("union_fee_rate", "insurance_company_rate", "insurance_employee_rate"):
			s.reload()
			s.set(field, 2)
			with self.assertRaises(frappe.ValidationError, msg=field):
				s.save()
