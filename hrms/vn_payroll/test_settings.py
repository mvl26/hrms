# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase

from hrms.vn_payroll.settings import config_from_settings
from hrms.vn_payroll.setup_mvl import ensure_mvl_defaults


class TestMVLSettings(FrappeTestCase):
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
